from __future__ import annotations

from decimal import Decimal
from typing import Dict, List, Optional

import logging
import traceback
from types import SimpleNamespace

from django.conf import settings
from django.db import transaction
from django.shortcuts import get_object_or_404

from rest_framework import status, views
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.models import OrganizationMembership
from pricing.dataclasses import Money, Piece, ShipmentInput
from pricing.services.pricing_service import compute_quote
from pricing.services.utils import FOURPLACES, TWOPLACES, ZERO, d
from .models import QuoteLines, Quotes
from .serializers import ComputeRequestSerializer

logger = logging.getLogger(__name__)


class QuoteStatus:
    COMPLETE = "COMPLETE"
    PENDING_RATE = "PENDING_RATE"


def normalize_scope_for_v2(scope: str) -> str:
    """
    Normalize service scope from serializers to V2-recognized short codes.
    Example: "AIRPORT_DOOR" -> "A2D"
    """
    mapping = {
        "AIRPORT_DOOR": "A2D",
        "DOOR_AIRPORT": "D2A",
        "DOOR_DOOR": "D2D",
        "AIRPORT_AIRPORT": "A2A",
    }
    return mapping.get(scope, scope)


def get_currency_for_iata(iata: Optional[str]) -> str:
    """
    Best-effort mapping of IATA to local currency.
    This is a lightweight heuristic mapping for common locations.
    Falls back to 'USD'.
    """
    if not iata or not isinstance(iata, str) or len(iata) < 3:
        return "USD"
    code = iata.upper()
    # Common mappings (expand as needed)
    mapping = {
        "SYD": "AUD",
        "MEL": "AUD",
        "BNE": "AUD",
        "POM": "PGK",  # Port Moresby -> Papua New Guinea Kina
        "NRT": "JPY",
        "HND": "JPY",
        "LAX": "USD",
        "JFK": "USD",
        "SFO": "USD",
        "SIN": "SGD",
        "KUL": "MYR",
        "BKK": "THB",
        "HKG": "HKD",
        "LHR": "GBP",
        "MAN": "GBP",
        "CDG": "EUR",
        "NCE": "EUR",
        "FRA": "EUR",
        "MAD": "EUR",
        "AMS": "EUR",
        "DXB": "AED",
    }
    # Try exact code then try first letter heuristics
    if code in mapping:
        return mapping[code]
    # Fallback by region (very rough)
    first = code[0]
    if first in ("S", "M", "B"):  # many APAC start with these - fallback to USD is safer
        return "USD"
    return "USD"


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
            return OrganizationMembership.objects.filter(
                user=user, organization_id=org_id, can_quote=True
            ).exists()

        if not is_authorized_for_org(user, org_id):
            return Response({"detail": "Forbidden for organization"}, status=status.HTTP_403_FORBIDDEN)

        shipment = ShipmentInput(
            org_id=int(data["org_id"]),
            origin_iata=data["origin_iata"],
            dest_iata=data["dest_iata"],
            service_scope=data["service_scope"],
            incoterm=(data.get("incoterm") or "EXW").upper(), # Default to EXW and normalize
            payment_term=data.get("payment_term", "PREPAID"),
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
            use_v2 = getattr(settings, "QUOTER_V2_ENABLED", False)

            calc_result = None

            # V2 should only be used for Import Prepaid Airport->Door (A2D) scenarios
            if (
                use_v2
                and shipment.service_scope == "AIRPORT_DOOR"
                and (shipment.payment_term or "").upper() == "PREPAID"
            ):
                try:
                    # Lazy import of V2 pricing pieces
                    from pricing_v2.dataclasses_v2 import QuoteContext as V2QuoteContext
                    from pricing_v2.pricing_service_v2 import compute_quote_v2
                except Exception:
                    # If v2 modules are not present, fall back silently to v1
                    logger.exception("V2 modules unavailable, falling back to V1 compute_quote.")
                    calc_result = compute_quote(
                        shipment,
                        provider_hint=data.get("provider_hint"),
                    )

                if calc_result is None:
                    # Build a QuoteContext for V2 - map fields appropriately
                    v2_scope = normalize_scope_for_v2(shipment.service_scope)
                    v2_mode = "AIR"  # Recipes expect "AIR" for air shipments
                    v2_direction = "IMPORT"  # Airport -> Door is an import direction
                    origin_ccy = get_currency_for_iata(shipment.origin_iata)
                    dest_ccy = get_currency_for_iata(shipment.dest_iata)

                    quote_context = V2QuoteContext(
                        mode=v2_mode,
                        direction=v2_direction,
                        scope=v2_scope,
                        payment_term=(shipment.payment_term or "PREPAID"),
                        origin_iata=shipment.origin_iata,
                        dest_iata=shipment.dest_iata,
                        pieces=[p.__dict__ for p in shipment.pieces],
                        commodity=shipment.commodity_code,
                        margins={},
                        policy={},
                        origin_country_currency=origin_ccy,
                        destination_country_currency=dest_ccy,
                    )

                    try:
                        v2_totals = compute_quote_v2(quote_context)
                        # v2_totals is expected to be dataclass with fields defined in dataclasses_v2.Totals

                        invoice_ccy = getattr(v2_totals, "invoice_ccy", None) or dest_ccy or origin_ccy or "USD"

                        # Build totals dict with Money objects matching V1 shape
                        sell_total_amount = d(getattr(v2_totals, "sell_total", getattr(v2_totals, "sell_subtotal", 0)))
                        buy_total_amount = d(getattr(v2_totals, "buy_total_pgk", 0))  # V2 may report buy_total_pgk
                        buy_total_ccy = "PGK" if getattr(v2_totals, "buy_total_pgk", None) is not None and getattr(v2_totals, "buy_total_pgk", 0) != 0 else "USD"

                        totals = {
                            "sell_total": Money(sell_total_amount, invoice_ccy),
                            "buy_total": Money(buy_total_amount, buy_total_ccy),
                            "tax_total": Money(d(getattr(v2_totals, "sell_tax", 0)), invoice_ccy),
                            "margin_abs": Money(Decimal(0), invoice_ccy),
                            "margin_pct": Money(Decimal(0), "%"),
                        }

                        snapshot = {
                            "manual_rate_required": bool(getattr(v2_totals, "is_incomplete", False)),
                            "manual_reasons": list(getattr(v2_totals, "reasons", []) or []),
                        }

                        # Prepare heuristics for quantity/unit mapping
                        total_pieces = len(shipment.pieces or [])
                        total_weight = ZERO
                        try:
                            for p in shipment.pieces:
                                total_weight += d(getattr(p, "weight_kg", 0))
                        except Exception:
                            total_weight = ZERO

                        # Convert v2 sell_lines (CalcLine) into V1 line objects
                        v2_sell_lines = getattr(v2_totals, "sell_lines", []) or []
                        sell_lines = []
                        buy_lines = []

                        for line in v2_sell_lines:
                            # Each line: code, description, amount, currency
                            code = getattr(line, "code", "") or ""
                            description = getattr(line, "description", "") or ""
                            amount = d(getattr(line, "amount", 0))
                            currency = getattr(line, "currency", None) or invoice_ccy or dest_ccy or "USD"

                            desc_l = description.lower() if isinstance(description, str) else ""
                            # Heuristic unit detection
                            if "kg" in desc_l or "per kg" in desc_l or "kg" in code.lower():
                                unit = "kg"
                                qty = total_weight or Decimal(1)
                            elif any(k in desc_l for k in ("piece", "pcs", "pc", "each")):
                                unit = "piece"
                                qty = total_pieces or 1
                            else:
                                unit = "shipment"
                                qty = 1

                            # Ensure qty is Decimal or int compatible
                            try:
                                qty_decimal = d(qty) if not isinstance(qty, int) else Decimal(qty)
                            except Exception:
                                qty_decimal = Decimal(1)

                            unit_price = Money(amount, currency)
                            extended_amt = (d(amount) * qty_decimal).quantize(FOURPLACES)
                            extended = Money(extended_amt, currency)

                            line_obj = SimpleNamespace(
                                code=code,
                                description=description,
                                is_buy=False,
                                is_sell=True,
                                qty=qty_decimal,
                                unit=unit,
                                unit_price=unit_price,
                                extended=extended,
                                tax_pct=0,
                                meta={"manual_rate_required": snapshot["manual_rate_required"]},
                            )
                            sell_lines.append(line_obj)

                        # Build a calc_result object matching V1 structure (attributes)
                        calc_result = SimpleNamespace(
                            totals=totals,
                            snapshot=snapshot,
                            buy_lines=buy_lines,
                            sell_lines=sell_lines,
                        )

                    except Exception as e:
                        # If V2 compute fails, log full context and fallback to V1
                        logger.exception("V2 compute_quote_v2 failed, falling back to V1. Context: %s", {
                            "quote_context": {
                                "mode": v2_mode,
                                "direction": v2_direction,
                                "scope": v2_scope,
                                "payment_term": shipment.payment_term,
                                "origin_iata": shipment.origin_iata,
                                "dest_iata": shipment.dest_iata,
                                "pieces_count": len(shipment.pieces or []),
                                "origin_ccy": origin_ccy,
                                "dest_ccy": dest_ccy,
                            },
                            "error": str(e),
                            "traceback": traceback.format_exc(),
                        })
                        # Fallback to V1
                        calc_result = compute_quote(
                            shipment,
                            provider_hint=data.get("provider_hint"),
                        )
            else:
                # V1 logic
                calc_result = compute_quote(
                    shipment,
                    provider_hint=data.get("provider_hint"),
                )

            # At this point calc_result should be an object with attributes:
            # .snapshot (dict-like), .totals (dict-like), .buy_lines (list), .sell_lines (list)
            is_manual = False
            try:
                is_manual = bool(getattr(calc_result, "snapshot", {}) .get("manual_rate_required", False))
            except Exception:
                # Try dict access fallback
                try:
                    is_manual = bool(calc_result.get("snapshot", {}).get("manual_rate_required", False))
                except Exception:
                    is_manual = False

            # Allowable statuses: QuoteStatus.PENDING_RATE | QuoteStatus.COMPLETE
            status_str = QuoteStatus.PENDING_RATE if is_manual else QuoteStatus.COMPLETE
            # Totals extraction - support both attribute and dict shapes
            totals_raw = {}
            if hasattr(calc_result, "totals"):
                totals_raw = getattr(calc_result, "totals") or {}
            elif isinstance(calc_result, dict):
                totals_raw = calc_result.get("totals", {})

            # Normalize snapshot for later use
            snapshot_raw = {}
            if hasattr(calc_result, "snapshot"):
                snapshot_raw = getattr(calc_result, "snapshot") or {}
            elif isinstance(calc_result, dict):
                snapshot_raw = calc_result.get("snapshot", {}) or {}

            # Prepare request_snapshot for storage (keep original payload and some computed fields)
            if isinstance(payload, dict):
                request_snapshot = {**payload, "shipment_type": getattr(shipment, "shipment_type", None)}
            else:
                request_snapshot = {"shipment_type": getattr(shipment, "shipment_type", None)}
                if hasattr(ser, 'initial_data') and isinstance(ser.initial_data, dict):
                    request_snapshot.update(ser.initial_data)

            request_snapshot["payment_term"] = shipment.payment_term
            request_snapshot["incoterm"] = shipment.incoterm

            # 2. Create the main Quote record
            new_quote = Quotes.objects.create(
                organization_id=shipment.org_id,
                status=status_str,
                # Store the original incoming payload (JSON-serializable),
                # not the validated data which contains Decimals.
                request_snapshot=request_snapshot,
                payment_term=shipment.payment_term,
                buy_total=totals_raw.get("buy_total", Money(ZERO, "USD")).amount,
                sell_total=totals_raw.get("sell_total", Money(ZERO, "USD")).amount,
                currency=totals_raw.get("sell_total", Money(ZERO, "USD")).currency,
                incoterm=shipment.incoterm,
            )

            # 3. Create the QuoteLines for the new Quote
            lines_to_create = []
            buy_lines = getattr(calc_result, "buy_lines", []) or []
            sell_lines = getattr(calc_result, "sell_lines", []) or []
            all_lines = list(buy_lines) + list(sell_lines)
            for line in all_lines:
                # Line objects created above use Money instances for unit_price and extended
                try:
                    unit_price_amt = getattr(line.unit_price, "amount", line.unit_price) if getattr(line, "unit_price", None) else ZERO
                    unit_price_ccy = getattr(line.unit_price, "currency", totals_raw.get("sell_total", Money(ZERO, "USD")).currency)
                except Exception:
                    unit_price_amt = ZERO
                    unit_price_ccy = totals_raw.get("sell_total", Money(ZERO, "USD")).currency

                try:
                    extended_amt = getattr(line.extended, "amount", line.extended) if getattr(line, "extended", None) else ZERO
                    extended_ccy = getattr(line.extended, "currency", unit_price_ccy)
                except Exception:
                    extended_amt = ZERO
                    extended_ccy = unit_price_ccy

                # Ensure qty is stored in a DB-friendly numeric type (string safe)
                qty_val = getattr(line, "qty", 1)
                # If qty is Decimal, convert to string to avoid precision loss when assigning to model field later
                try:
                    if isinstance(qty_val, Decimal):
                        qty_to_store = str(qty_val)
                    else:
                        qty_to_store = qty_val
                except Exception:
                    qty_to_store = qty_val

                lines_to_create.append(
                    QuoteLines(
                        quote=new_quote,
                        code=getattr(line, "code", ""),
                        description=getattr(line, "description", ""),
                        is_buy=getattr(line, "is_buy", False),
                        is_sell=getattr(line, "is_sell", False),
                        qty=qty_to_store,
                        unit=getattr(line, "unit", "") or "shipment",
                        unit_price=Decimal(str(unit_price_amt)),
                        extended_price=Decimal(str(extended_amt)),
                        currency=extended_ccy,
                        tax_pct=getattr(line, "tax_pct", 0),
                        manual_rate_required=getattr(line, "meta", {}).get("manual_rate_required", False),
                    )
                )

            QuoteLines.objects.bulk_create(lines_to_create)

            # 4. Return the ID of the new quote with totals wrapped for frontend
            # Ensure we can access the totals amounts and currencies safely
            def money_for(key: str):
                m = totals_raw.get(key, Money(ZERO, "USD"))
                # If m is Money-like object
                try:
                    return {"amount": str(m.amount), "currency": m.currency}
                except Exception:
                    # If it's a raw number
                    try:
                        return {"amount": str(m), "currency": "USD"}
                    except Exception:
                        return {"amount": "0", "currency": "USD"}

            response_data = {
                "quote_id": new_quote.id,
                "status": status_str,
                "totals": {
                    "sell_total": money_for("sell_total"),
                    "buy_total": money_for("buy_total"),
                    "tax_total": money_for("tax_total"),
                    "margin_abs": money_for("margin_abs"),
                    "margin_pct": money_for("margin_pct"),
                },
                "manual_reasons": snapshot_raw.get("manual_reasons", []),
            }
            return Response(response_data, status=status.HTTP_201_CREATED)

        except ValueError as e:
            # If the engine fails (e.g., no route found), use DRF 'detail' error shape
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class QuoteDetailView(views.APIView):
    def get(self, request, quote_id: int):
        q = get_object_or_404(
            Quotes.objects.select_related("organization").prefetch_related("lines"),
            pk=quote_id,
        )

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
                "tax_pct": str(l.tax_pct),
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
                w = ZERO
                l = ZERO
                w_cm = ZERO
                h = ZERO
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
            "payment_term": q.payment_term,
            "incoterm": q.incoterm,
            "actual_weight_kg": str(actual.quantize(FOURPLACES)),
            "volume_cbm": str(volume.quantize(FOURPLACES)),
            "chargeable_weight_kg": str(chargeable.quantize(FOURPLACES)),
            "rate_used_per_kg": "",
            "base_cost": str(Decimal(q.buy_total).quantize(TWOPLACES)),
            "margin_pct": str(
                ((d(q.sell_total) - d(q.buy_total)) / (d(q.sell_total) or Decimal(1)) * Decimal(100)).quantize(
                    FOURPLACES
                )
            ),
            "total_sell": str(Decimal(q.sell_total).quantize(TWOPLACES)),
            "created_at": q.created_at.isoformat()
        }

        # Include detailed fields for advanced views without breaking the UI
        lines = list(q.lines.all())
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

        class StandardResultsSetPagination(PageNumberPagination):
            page_size = 25
            page_size_query_param = "page_size"
            max_page_size = 100

        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(qs, request, view=self)

        items = []
        for q in page:
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
                    w = ZERO
                    l = ZERO
                    w_cm = ZERO
                    h = ZERO
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

            items.append({
                "id": q.id,
                "client": client_obj,
                "origin": snap.get("origin_iata") or snap.get("origin") or "",
                "destination": snap.get("dest_iata") or snap.get("destination") or "",
                "mode": snap.get("shipment_type") or "",
                "payment_term": q.payment_term,
                "incoterm": q.incoterm,
                "status": q.status,
                "actual_weight_kg": str(actual.quantize(FOURPLACES)),
                "volume_cbm": str(volume.quantize(FOURPLACES)),
                "chargeable_weight_kg": str(chargeable.quantize(FOURPLACES)),
                "rate_used_per_kg": "",
                "base_cost": str(Decimal(q.buy_total).quantize(TWOPLACES)),
                "margin_pct": str(
                    ((d(q.sell_total) - d(q.buy_total)) / (d(q.sell_total) or Decimal(1)) * Decimal(100)).quantize(
                        FOURPLACES
                    )
                ),
                "total_sell": str(Decimal(q.sell_total).quantize(TWOPLACES)),
                "created_at": q.created_at.isoformat(),
            })

        return paginator.get_paginated_response(items)