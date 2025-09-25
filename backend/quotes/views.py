# quotes/views.py
from decimal import Decimal, ROUND_HALF_UP
from django.db import transaction
from django.utils import timezone
from django.shortcuts import get_object_or_404

from rest_framework import viewsets, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from .models import Quotation, QuoteVersion, ShipmentPiece, Charge
from .serializers import QuotationSerializer, QuoteVersionSerializer
from .tax_policy import apply_gst_policy

# ---- Money helpers (use your quotes/money.py if you already created it) ----
try:
    from .money import q4 as _q4, extended as _extended
    def q4(v): return _q4(v)
    def extended(basis, qty, unit): return _extended(basis, qty, unit)
except Exception:
    MONEY_2DP = Decimal('0.01')
    UNIT_4DP  = Decimal('0.0001')
    def _quant(x, q): return Decimal(x).quantize(q, rounding=ROUND_HALF_UP)
    def q4(x): return _quant(x, UNIT_4DP)
    def q2(x): return _quant(x, MONEY_2DP)
    def extended(basis, qty, unit_price):
        qty = Decimal(qty)
        unit = Decimal(unit_price)
        if basis == 'PERCENT':
            return q2(qty * (unit / Decimal(100)))
        # For FLAT and PER_KG, treat as qty * unit
        return q2(qty * unit)

# ---- ViewSet for the envelope ----
class QuotationViewSet(viewsets.ModelViewSet):
    queryset = (Quotation.objects
                .all().order_by('-created_at')
                .prefetch_related('versions', 'versions__pieces', 'versions__charges'))
    serializer_class = QuotationSerializer


# ---- Create a new QuoteVersion (idempotent, nested write, GST policy applied) ----
class QuoteVersionCreateView(APIView):
    def post(self, request, id):
        quotation = get_object_or_404(Quotation, pk=id)
        idempotency_key = request.headers.get('Idempotency-Key')

        # Return prior result if same idempotency key was used
        if idempotency_key:
            existing = QuoteVersion.objects.filter(idempotency_key=idempotency_key).first()
            if existing:
                data = QuoteVersionSerializer(existing).data
                return Response(data, status=status.HTTP_200_OK)

        payload = request.data.copy()
        pieces_data  = payload.pop('pieces', [])
        charges_data = payload.pop('charges', [])

        # Validate top-level fields only (no nested writes via serializer)
        ser = QuoteVersionSerializer(data=payload, context={'request': request})
        ser.is_valid(raise_exception=True)

        with transaction.atomic():
            # Lock parent to assign the next version number safely
            last = quotation.versions.select_for_update().order_by('-version_no').first()
            next_no = 1 if not last else last.version_no + 1

            version = QuoteVersion.objects.create(
                quotation=quotation,
                version_no=next_no,
                created_by=request.user if request.user.is_authenticated else None,
                idempotency_key=idempotency_key,
                **ser.validated_data
            )

            # Pieces
            for p in pieces_data:
                ShipmentPiece.objects.create(version=version, **p)

            # Charges (compute money, enforce currency, apply GST)
            for ch in charges_data:
                basis = ch.get('basis', 'FLAT')
                qty   = ch.get('qty', 1)
                unit  = ch.get('unit_price', 0)

                ch['unit_price']     = q4(unit)
                ch['extended_price'] = extended(basis, qty, ch['unit_price'])

                # SELL currency must match the version's sell_currency
                if ch.get('side') == 'SELL':
                    if ch.get('currency') and ch['currency'] != version.sell_currency:
                        return Response(
                            {"error": f"SELL line currency must equal version.sell_currency ({version.sell_currency})"},
                            status=status.HTTP_400_BAD_REQUEST
                        )
                    ch['currency'] = version.sell_currency

                # Apply GST policy
                class _C: pass
                _c = _C()
                for k, v in ch.items(): setattr(_c, k, v)
                _c.stage = ch.get('stage')
                _c.code  = (ch.get('code') or '')
                _c.is_taxable = bool(ch.get('is_taxable', False))
                _c.gst_percentage = ch.get('gst_percentage', 0)
                apply_gst_policy(version, _c)
                ch['is_taxable'] = _c.is_taxable
                ch['gst_percentage'] = _c.gst_percentage

                Charge.objects.create(version=version, **ch)

        return Response(QuoteVersionSerializer(version).data, status=status.HTTP_201_CREATED)


# ---- Lock a version (immutability + status flip) ----
class QuoteVersionLockView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, id):
        version = get_object_or_404(QuoteVersion.objects.select_related('quotation'), pk=id)

        # Only staff or the creator can lock
        user = request.user
        if not (user.is_staff or (version.created_by_id and version.created_by_id == user.id)):
            return Response({"error": "Not allowed"}, status=status.HTTP_403_FORBIDDEN)

        if version.locked_at:
            return Response({"status": "already_locked", "locked_at": version.locked_at}, status=status.HTTP_200_OK)

        # Must have at least one SELL line
        if not version.charges.filter(side='SELL').exists():
            return Response({"error": "Cannot lock a version with no SELL lines"}, status=status.HTTP_400_BAD_REQUEST)

        version.locked_at = timezone.now()
        version.save(update_fields=['locked_at'])

        # If this is latest, mark the envelope quoted
        latest = version.quotation.versions.order_by('-version_no').first()
        if latest and latest.id == version.id:
            version.quotation.status = 'QUOTED'
            version.quotation.save(update_fields=['status'])

        return Response({"status": "locked", "locked_at": version.locked_at}, status=status.HTTP_200_OK)