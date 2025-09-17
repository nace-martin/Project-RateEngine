from __future__ import annotations

import logging
import os
from decimal import Decimal
from typing import Dict, List

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils.timezone import now

from rest_framework import status, views
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.models import OrganizationMembership

from .dataclasses import Money, Piece, ShipmentInput
from core.models import CurrencyRates as CurrencyRate
from organizations.models import Organizations
from quotes.models import Quotes, QuoteLines
from .serializers import ComputeRequestSerializer
from .services.pricing_service import compute_quote
from .services.utils import FOURPLACES, TWOPLACES, ZERO, d
from .fx import EnvProvider, compute_tt_buy_sell, upsert_rate
from .fx_providers import load as load_fx_provider


class QuoteStatus:
    COMPLETE = "COMPLETE"
    PENDING_RATE = "PENDING_RATE"


class QuoteComputeView(views.APIView):
    permission_classes = [IsAuthenticated]
    @transaction.atomic
    def post(self, request):
        # Normalize legacy piece keys (weight/length/width/height -> *_kg/_cm)
        incoming = request.data
        if isinstance(incoming, dict) and "pieces" in incoming:
            norm_pieces = []
            for p in incoming.get("pieces", []) or []:
                q = dict(p)
                if "weight" in q and "weight_kg" not in q:
                    q["weight_kg"] = q.pop("weight")
                if "length" in q and "length_cm" not in q:
                    q["length_cm"] = q.pop("length")
                if "width" in q and "width_cm" not in q:
                    q["width_cm"] = q.pop("width")
                if "height" in q and "height_cm" not in q:
                    q["height_cm"] = q.pop("height")
                norm_pieces.append(q)
            payload = {**incoming, "pieces": norm_pieces}
        else:
            payload = incoming

        ser = ComputeRequestSerializer(data=payload)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        # -------- Organization authorization check --------
        org_id = int(data["org_id"])
        user = request.user
        user_role = getattr(user, "role", "")

        def is_authorized_for_org(user, org_id: int) -> bool:
            # Managers and Finance can quote for any organization
            if user_role in ("manager", "finance"):
                return True
            # Check explicit per-organization membership
            return OrganizationMembership.objects.filter(user=user, organization_id=org_id, can_quote=True).exists()

        if not is_authorized_for_org(user, org_id):
            return Response({"detail": "Forbidden for organization"}, status=status.HTTP_403_FORBIDDEN)

        shipment = ShipmentInput(
            org_id=int(data["org_id"]),
            origin_iata=data["origin_iata"],
            dest_iata=data["dest_iata"],
            shipment_type=data["shipment_type"],
            service_scope=data["service_scope"],
            incoterm=(data.get("incoterm") or None),
            commodity_code=data.get("commodity_code", "GCR"),
            is_urgent=bool(data.get("is_urgent", False)),
            airline_hint=data.get("airline_hint") or None,
            via_hint=data.get("via_hint") or None,
            pieces=[Piece(**p) for p in data["pieces"]],
            flags=data.get("flags") or {},
            duties_value_sell_ccy=data.get("duties_value_sell_ccy") or ZERO,
            pallets=data.get("pallets") or 0,
        )

        try:
            # 1. Run the rating engine to get the calculation result
            calc_result = compute_quote(
                shipment,
                provider_hint=data.get("provider_hint"),
                caf_pct=d(data.get("caf_pct") or Decimal("0.065")),
            )

            is_manual = calc_result.snapshot.get("manual_rate_required", False)
            # Allowable statuses: QuoteStatus.PENDING_RATE | QuoteStatus.COMPLETE
            status_str = QuoteStatus.PENDING_RATE if is_manual else QuoteStatus.COMPLETE
            totals = calc_result.totals

            # 2. Create the main Quote record
            new_quote = Quotes.objects.create(
                organization_id=shipment.org_id,
                status=status_str,
                # Store the original incoming payload (JSON-serializable),
                # not the validated data which contains Decimals.
                request_snapshot=payload,
                buy_total=totals.get('buy_total', Money(ZERO, 'USD')).amount,
                sell_total=totals.get('sell_total', Money(ZERO, 'USD')).amount,
                currency=totals.get('sell_total', Money(ZERO, 'USD')).currency,
                incoterm=shipment.incoterm,
            )

            # 3. Create the QuoteLines for the new Quote
            lines_to_create = []
            all_lines = calc_result.buy_lines + calc_result.sell_lines
            for line in all_lines:
                lines_to_create.append(
                    QuoteLines(
                        quote=new_quote,
                        code=line.code,
                        description=line.description,
                        is_buy=line.is_buy,
                        is_sell=line.is_sell,
                        qty=line.qty,
                        unit=line.unit,
                        unit_price=line.unit_price.amount,
                        extended_price=line.extended.amount,
                        currency=line.extended.currency,
                        manual_rate_required=getattr(line, 'meta', {}).get("manual_rate_required", False),
                    )
                )

            QuoteLines.objects.bulk_create(lines_to_create)

            # 4. Return the ID of the new quote with totals wrapped for frontend
            response_data = {
                "quote_id": new_quote.id,
                "status": status_str,
                "totals": {
                    "sell_total": {
                        "amount": str(totals["sell_total"].amount),
                        "currency": totals["sell_total"].currency,
                    },
                    "buy_total": {
                        "amount": str(totals["buy_total"].amount),
                        "currency": totals["buy_total"].currency,
                    },
                    "tax_total": {
                        "amount": str(totals["tax_total"].amount),
                        "currency": totals["tax_total"].currency,
                    },
                    "margin_abs": {
                        "amount": str(totals["margin_abs"].amount),
                        "currency": totals["margin_abs"].currency,
                    },
                    "margin_pct": {
                        "amount": str(totals["margin_pct"].amount),
                        "currency": totals["margin_pct"].currency,
                    },
                },
                "manual_reasons": calc_result.snapshot.get("manual_reasons", []),
            }
            return Response(response_data, status=status.HTTP_201_CREATED)

        except ValueError as e:
            # If the engine fails (e.g., no route found), use DRF 'detail' error shape
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class QuoteDetailView(views.APIView):
    def get(self, request, quote_id: int):
        q = get_object_or_404(Quotes.objects.select_related("organization").prefetch_related("lines"), pk=quote_id)

        def serialize_line(l: QuoteLines) -> Dict:
            return {
                "code": l.code,
                "desc": l.description,
                "qty": str(l.qty),
                "unit": l.unit,
                "unit_price": {"amount": str(l.unit_price), "currency": l.currency},
                "amount": {"amount": str(l.extended_price), "currency": l.currency},
                "is_buy": l.is_buy,
                "is_sell": l.is_sell,
                "manual_rate_required": bool(l.manual_rate_required),
            }

        # Compute projections to match list endpoint and frontend expectations
        snap = q.request_snapshot if isinstance(q.request_snapshot, dict) else {}
        pieces = snap.get("pieces") or []
        actual = ZERO
        volume = ZERO
        for p in pieces:
            try:
                w = d(p.get("weight_kg", 0))
                l = d(p.get("length_cm", 0))
                w_cm = d(p.get("width_cm", 0))
                h = d(p.get("height_cm", 0))
            except Exception:
                w = ZERO; l = ZERO; w_cm = ZERO; h = ZERO
            actual += w
            if l and w_cm and h:
                volume += (l * w_cm * h) / Decimal(1_000_000)
        dim_factor = Decimal(167)
        chargeable = max(actual, (volume * dim_factor).quantize(FOURPLACES))

        org = q.organization
        client_obj = {
            "id": org.id,
            "name": org.name,
            "email": "",
            "phone": "",
            "org_type": org.audience,
            "created_at": q.created_at.isoformat(),
        }

        # Primary detail payload consistent with list items
        detail = {
            "id": q.id,
            "client": client_obj,
            "origin": snap.get("origin_iata") or snap.get("origin") or "",
            "destination": snap.get("dest_iata") or snap.get("destination") or "",
            "mode": snap.get("shipment_type") or "",
            "actual_weight_kg": str(actual.quantize(FOURPLACES)),
            "volume_cbm": str(volume.quantize(FOURPLACES)),
            "chargeable_weight_kg": str(chargeable.quantize(FOURPLACES)),
            "rate_used_per_kg": "",
            "base_cost": str(Decimal(q.buy_total).quantize(TWOPLACES)),
            "margin_pct": str(((d(q.sell_total) - d(q.buy_total)) / (d(q.sell_total) or Decimal(1)) * Decimal(100)).quantize(FOURPLACES)),
            "total_sell": str(Decimal(q.sell_total).quantize(TWOPLACES)),
            "created_at": q.created_at.isoformat(),
        }

        # Include detailed fields for advanced views without breaking the UI
        lines = list(q.lines.all())
        # Precompute margins for totals in detail response
        _buy = d(q.buy_total)
        _sell = d(q.sell_total)
        _margin_abs = (_sell - _buy).quantize(TWOPLACES)
        _margin_pct = ((_sell - _buy) / (_sell or Decimal(1))).quantize(FOURPLACES)

        extra = {
            "status": q.status,
            "currency": q.currency,
            "totals": {
                "buy_total": {"amount": str(q.buy_total), "currency": q.currency},
                "sell_total": {"amount": str(q.sell_total), "currency": q.currency},
                "margin_abs": {"amount": str(_margin_abs), "currency": q.currency},
                "margin_pct": {"amount": str(_margin_pct), "currency": "%"},
            },
            "snapshot": q.request_snapshot,
            "updated_at": q.updated_at.isoformat(),
            "buy_lines": [serialize_line(l) for l in lines if l.is_buy],
            "sell_lines": [serialize_line(l) for l in lines if l.is_sell],
        }

        return Response({**detail, **extra}, status=status.HTTP_200_OK)


class QuoteListView(views.APIView):
    def get(self, request):
        qs = Quotes.objects.select_related("organization").order_by("-created_at")
        org_id = request.query_params.get("org_id")
        status_filter = request.query_params.get("status")
        if org_id:
            try:
                qs = qs.filter(organization_id=int(org_id))
            except ValueError:
                pass
        if status_filter:
            qs = qs.filter(status=status_filter)

        # Paginate first to avoid processing entire set
        class StandardResultsSetPagination(PageNumberPagination):
            page_size = 25
            page_size_query_param = 'page_size'
            max_page_size = 100

        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(qs, request, view=self)

        # Build array payload matching frontend Quote type for current page
        items = []
        for q in page:
            snap = q.request_snapshot if isinstance(q.request_snapshot, dict) else {}
            pieces = snap.get("pieces") or []
            # Compute actual and volume
            actual = ZERO
            volume = ZERO
            for p in pieces:
                try:
                    w = d(p.get("weight_kg", 0))
                    l = d(p.get("length_cm", 0))
                    w_cm = d(p.get("width_cm", 0))
                    h = d(p.get("height_cm", 0))
                except Exception:
                    w = ZERO; l = ZERO; w_cm = ZERO; h = ZERO
                actual += w
                if l and w_cm and h:
                    volume += (l * w_cm * h) / Decimal(1_000_000)
            # Chargeable using default 167 if dims provided
            dim_factor = Decimal(167)
            chargeable = max(actual, (volume * dim_factor).quantize(FOURPLACES))

            # Client projection (using Organization)
            org = q.organization
            client_obj = {
                "id": org.id,
                "name": org.name,
                "email": "",
                "phone": "",
                "org_type": org.audience,
                "created_at": q.created_at.isoformat(),
            }

            items.append({
                "id": q.id,
                "client": client_obj,
                "origin": snap.get("origin_iata") or snap.get("origin") or "",
                "destination": snap.get("dest_iata") or snap.get("destination") or "",
                "mode": snap.get("shipment_type") or "",
                "status": q.status,
                "actual_weight_kg": str(actual.quantize(FOURPLACES)),
                "volume_cbm": str(volume.quantize(FOURPLACES)),
                "chargeable_weight_kg": str(chargeable.quantize(FOURPLACES)),
                "rate_used_per_kg": "",
                "base_cost": str(Decimal(q.buy_total).quantize(TWOPLACES)),
                "margin_pct": str(((d(q.sell_total) - d(q.buy_total)) / (d(q.sell_total) or Decimal(1)) * Decimal(100)).quantize(FOURPLACES)),
                "total_sell": str(Decimal(q.sell_total).quantize(TWOPLACES)),
                "created_at": q.created_at.isoformat(),
            })

        return paginator.get_paginated_response(items)


class OrganizationsListView(views.APIView):
    def get(self, request):
        rows = Organizations.objects.all().order_by("name").values("id", "name")
        return Response(list(rows), status=status.HTTP_200_OK)


class FxRefreshView(views.APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        role = getattr(user, "role", "")
        if role not in ("manager", "finance"):
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

        pairs_arg = request.data.get("pairs")
        spread_bps = int(request.data.get("spread_bps", 100))
        caf_pct = d(request.data.get("caf_pct", "0.065"))

        if not pairs_arg:
            return Response({"detail": "pairs is required, e.g., ['USD:PGK','PGK:USD']"}, status=status.HTTP_400_BAD_REQUEST)

        if isinstance(pairs_arg, str):
            parts = [p.strip() for p in pairs_arg.split(',') if p.strip()]
        else:
            parts = list(pairs_arg)
        pairs = []
        for p in parts:
            if ":" not in p:
                return Response({"detail": f"Invalid pair '{p}'. Use BASE:QUOTE"}, status=status.HTTP_400_BAD_REQUEST)
            b, q = p.split(":", 1)
            pairs.append((b.strip().upper(), q.strip().upper()))

        provider_name = (request.data.get("provider") or "bsp_html").strip().lower()
        FX_STALE_HOURS = float(os.environ.get("FX_STALE_HOURS", 24))
        FX_ANOM_PCT = float(os.environ.get("FX_ANOMALY_PCT", 0.05))

        def latest_prev_for_pair(base: str, quote: str):
            prev_buy = (CurrencyRate.objects
                        .filter(base_ccy=base, quote_ccy=quote, rate_type='BUY')
                        .order_by('-as_of_ts').first())
            prev_sell = (CurrencyRate.objects
                         .filter(base_ccy=base, quote_ccy=quote, rate_type='SELL')
                         .order_by('-as_of_ts').first())
            latest = None
            if prev_buy and prev_sell:
                latest = prev_buy if prev_buy.as_of_ts >= prev_sell.as_of_ts else prev_sell
            else:
                latest = prev_buy or prev_sell
            return latest, prev_buy, prev_sell

        def maybe_warn_stale(base: str, quote: str, latest_row):
            if not latest_row:
                return None
            age_hours = (now() - latest_row.as_of_ts).total_seconds() / 3600.0
            if age_hours > FX_STALE_HOURS:
                logging.warning("FX staleness: %s->%s latest %.1fh old", base, quote, age_hours)
            return age_hours

        def maybe_warn_anomaly(base: str, quote: str, rate_type: str, prev_rate, new_rate):
            try:
                if prev_rate and d(prev_rate) > 0:
                    pct = float(abs(d(new_rate) - d(prev_rate)) / d(prev_rate))
                    if pct > FX_ANOM_PCT:
                        logging.warning("FX anomaly: %s->%s %s changed by %.2f%% (old=%s new=%s)",
                                        base, quote, rate_type, pct*100.0, prev_rate, new_rate)
            except Exception:
                pass

        summary = []

        if provider_name in {"bsp_html", "bsp", "bank_bsp"}:
            provider = load_fx_provider(provider_name)
            try:
                rows = provider.fetch([f"{b}:{q}" for (b, q) in pairs])
            except Exception as e:
                logging.warning("BSP provider failed, falling back to ENV: %s", e)
                provider_name = "env"
                provider = EnvProvider()
                rows = []  # will be populated in env branch below

            if provider_name != "env":
                # Pre-check staleness per pair (before upsert)
                for (base, quote) in pairs:
                    latest, prev_buy_row, prev_sell_row = latest_prev_for_pair(base, quote)
                    age_hours = maybe_warn_stale(base, quote, latest)
                    # Apply and record rows
                for r in rows:
                    # anomaly checks per rate_type using previous rows
                    prev_row = (CurrencyRate.objects.filter(base_ccy=r.base_ccy, quote_ccy=r.quote_ccy, rate_type=r.rate_type)
                                .order_by('-as_of_ts').first())
                    prev_val = prev_row.rate if prev_row else None
                    maybe_warn_anomaly(r.base_ccy, r.quote_ccy, r.rate_type, prev_val, r.rate)
                    upsert_rate(r.as_of_ts, r.base_ccy, r.quote_ccy, r.rate, r.rate_type, r.source)
                    summary.append({
                        "pair": f"{r.base_ccy}->{r.quote_ccy}",
                        "as_of": r.as_of_ts.isoformat(),
                        "mid": None,
                        "buy": str(r.rate) if r.rate_type == "BUY" else None,
                        "sell": str(r.rate) if r.rate_type == "SELL" else None,
                        "source": r.source,
                    })

        if provider_name == "env":
            env = EnvProvider()
            for (base, quote) in pairs:
                latest, prev_buy_row, prev_sell_row = latest_prev_for_pair(base, quote)
                age_hours = maybe_warn_stale(base, quote, latest)
                try:
                    mr = env.get_mid_rate(base, quote)
                    buy, sell = compute_tt_buy_sell(mr.rate, spread_bps, caf_pct)
                except Exception as e:
                    return Response({"detail": f"ENV provider failed for {base}->{quote}: {e}"}, status=status.HTTP_400_BAD_REQUEST)
                # anomaly vs previous
                maybe_warn_anomaly(base, quote, 'BUY', prev_buy_row.rate if prev_buy_row else None, buy)
                maybe_warn_anomaly(base, quote, 'SELL', prev_sell_row.rate if prev_sell_row else None, sell)
                upsert_rate(mr.as_of, base, quote, buy, 'BUY', 'ENV')
                upsert_rate(mr.as_of, base, quote, sell, 'SELL', 'ENV')
                summary.append({
                    "pair": f"{base}->{quote}",
                    "as_of": mr.as_of.isoformat(),
                    "mid": str(mr.rate),
                    "buy": str(buy),
                    "sell": str(sell),
                    "source": "ENV",
                    **({"fx_age_hours": round(age_hours, 1)} if age_hours is not None else {}),
                })

        return Response({"updated": summary}, status=status.HTTP_200_OK)




