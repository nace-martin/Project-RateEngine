from __future__ import annotations

import logging
import re
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from django.db.models import Case, IntegerField, Q, Value, When
from django.utils.timezone import now

from ..dataclasses import CalcLine, CalcResult, Money, Piece, ShipmentInput
from core.models import (
    FeeTypes as FeeType,
    Stations as Station,
)
from organizations.models import Organizations
from pricing.models import (
    Lanes as Lane,
    LaneBreaks as LaneBreak,
    PricingPolicy,
    RatecardConfig,
    RatecardFees as RatecardFee,
    Ratecards as Ratecard,
    RouteLegs,
    Routes,
    SellCostLinksSimple as SellCostLink,
    ServiceItems as ServiceItem,
)
from .fx_service import FxConverter
from .utils import (
    FOURPLACES,
    TWOPLACES,
    ZERO,
    d,
    round_up_nearest_0_05,
    round_up_to_next_whole,
)

# --------------------- Core engine functions ---------------------

def compute_chargeable(weight_kg: Decimal, volume_m3: Decimal, dim_factor_kg_per_m3: Decimal) -> Decimal:
    vol_weight = (volume_m3 * dim_factor_kg_per_m3).quantize(FOURPLACES)
    return max(weight_kg, vol_weight)


def calculate_chargeable_weight_per_piece(pieces: List[Piece], dim_factor_kg_per_m3: Decimal) -> Decimal:
    """
    Calculates chargeable weight by summing the greater of actual vs. volumetric
    weight for each piece. The final result is rounded up to the next whole kg.
    """
    total_chargeable = ZERO
    if not pieces:
        return ZERO

    for p in pieces:
        actual_weight = p.weight_kg
        # volume_m3() is a method on the Piece dataclass
        volume_m3 = p.volume_m3()
        volumetric_weight = (volume_m3 * dim_factor_kg_per_m3).quantize(FOURPLACES)

        # Add the greater of the two for this piece to the total
        total_chargeable += max(actual_weight, volumetric_weight)

    # Round the final chargeable weight up to the next whole kilogram.
    # Example: 150.1 kg -> 151 kg; 150.0 kg -> 150 kg
    return round_up_to_next_whole(total_chargeable)


def pick_best_break(lane: Lane, chargeable_kg: Decimal) -> Tuple[LaneBreak, Money]:
    """Return chosen LaneBreak and base freight in lane currency (ratecard.currency)."""
    breaks = list(LaneBreak.objects.filter(lane_id=lane.id))
    by_code = {b.break_code: b for b in breaks}

    rc = Ratecard.objects.get(id=lane.ratecard_id)
    ccy = rc.currency

    # Per-kg rows
    best_cost = None
    best_break = None

    for b in breaks:
        if b.break_code == "MIN":
            continue
        per_kg = d(b.per_kg)
        if b.break_code == "N":
            # treat as base per-kg for <45 when agents give only N
            cost = (per_kg * chargeable_kg).quantize(TWOPLACES)
            chosen = b
        else:
            # numeric break threshold
            try:
                threshold = Decimal(b.break_code)
            except Exception:
                continue
            if chargeable_kg >= threshold:
                cost = (per_kg * chargeable_kg).quantize(TWOPLACES)
                chosen = b
            else:
                continue
        if best_cost is None or cost < best_cost:
            best_cost = cost
            best_break = chosen

    # Enforce MIN if present
    if "MIN" in by_code:
        min_row = by_code["MIN"]
        min_charge = d(min_row.min_charge)
        if best_cost is None:
            best_cost = min_charge
            best_break = min_row
        elif min_charge > best_cost:
            best_cost = min_charge
            best_break = min_row

    if best_break is None:
        raise ValueError("No lane breaks available for pricing")

    return best_break, Money(best_cost, ccy)


def select_route_legs_for_payload(
    legs: List[RouteLegs], origin_iata: str, dest_iata: str
) -> List[RouteLegs]:
    """Return legs that form a contiguous path between the requested stations."""

    if not legs:
        return []

    origin = (origin_iata or "").upper()
    destination = (dest_iata or "").upper()

    path: List[RouteLegs] = []
    expected_origin = origin

    for leg in legs:
        leg_origin = (getattr(leg.origin, "iata", "") or "").upper()
        leg_dest = (getattr(leg.dest, "iata", "") or "").upper()

        if not path:
            if leg_origin != expected_origin:
                continue
            path.append(leg)
            expected_origin = leg_dest
            if leg_dest == destination:
                return path
            continue

        if leg_origin != expected_origin:
            continue

        path.append(leg)
        expected_origin = leg_dest
        if leg_dest == destination:
            return path

    # Fallback: any direct leg covering origin -> destination
    for leg in legs:
        leg_origin = (getattr(leg.origin, "iata", "") or "").upper()
        leg_dest = (getattr(leg.dest, "iata", "") or "").upper()
        if leg_origin == origin and leg_dest == destination:
            return [leg]

    if path and (getattr(path[-1].dest, "iata", "") or "").upper() == destination:
        return path

    return []


def _normalize_basis(basis_raw: Optional[str]) -> str:
    """Normalize fee basis strings to canonical tokens.

    Handles common variants like "PER KG", "per-kg", "KG", etc., which otherwise
    would cause PER_KG fees to be treated as flat (returning just the per-kg rate).
    """
    b = (basis_raw or "").strip().upper()
    b = re.sub(r"[\s\-]+", "_", b)  # collapse spaces/dashes to underscore
    b = re.sub(r"_+", "_", b)
    # Canonical groups
    if b in {"PER_KG", "KG", "PER_KILO", "PER_KILOGRAM", "PER_KGS", "PER_KILOGRAMS"}:
        return "PER_KG"
    if b in {"PER_SHIPMENT", "SHIPMENT"}:
        return "PER_SHIPMENT"
    if b in {"PER_AWB", "AWB", "AIR_WAYBILL"}:
        return "PER_AWB"
    if b in {"PER_SET", "SET"}:
        return "PER_SET"
    if b in {"PER_TRANSFER", "TRANSFER"}:
        return "PER_TRANSFER"
    if b in {"PERCENT_OF", "PCT_OF", "PERCENTAGE_OF"}:
        return "PERCENT_OF"
    return b


def compute_fee_amount(fee: RatecardFee, kg: Decimal, context: Dict[str, Money]) -> Money:
    """Compute a BUY fee line in its native currency.
    context: map of code->Money already computed (for PERCENT_OF).
    """
    ft = FeeType.objects.get(id=fee.fee_type_id)
    code = ft.code
    # Normalize basis to handle stray casing/whitespace/symbol variants from data seeds
    basis = _normalize_basis(ft.basis)
    ccy = fee.currency
    amt = d(fee.amount)
    min_amt = d(fee.min_amount) if fee.min_amount is not None else None
    max_amt = d(fee.max_amount) if fee.max_amount is not None else None
    applies_if = fee.applies_if or {}

    # Conditional gates
    if applies_if.get("secondary_screening") and not context.get("secondary_screening_flag"):
        return Money(ZERO, ccy)
    if applies_if.get("included_in_base"):
        return Money(ZERO, ccy)
    if fee.per_kg_threshold and kg <= d(fee.per_kg_threshold):
        return Money(ZERO, ccy)

    total = ZERO
    # BUY-Side: for PER_KG fees, multiply the per-kg rate by chargeable kg
    if basis == "PER_KG":
        kg_dec = d(kg)
        # Business rule corrections for specific surcharges
        if code in {"SEC", "SECURITY"}:
            # Security surcharge: PGK 0.20/kg with PGK 5.00 minimum (whichever is higher)
            security_rate = Decimal("0.20")
            security_min = Decimal("5.00")
            total = max(security_rate * kg_dec, security_min)
        elif code in {"FUEL", "FUEL_SURCHARGE"}:
            # Fuel surcharge: PGK 0.35/kg
            fuel_rate = Decimal("0.35")
            total = fuel_rate * kg_dec
        else:
            # Standard per-kg fee logic
            total = (amt * kg_dec)
            if min_amt is not None:
                total = max(total, min_amt)
    elif basis in ("PER_SHIPMENT", "PER_AWB", "PER_SET", "PER_TRANSFER"):
        total = amt
    elif basis == "PERCENT_OF":
        ref_code = fee.percent_of_code
        if not ref_code or ref_code not in context:
            return Money(ZERO, ccy)
        total = (d(context[ref_code].amount) * amt).quantize(TWOPLACES)  # here `amount` holds percent as 0.10 for 10%
    else:
        # Other bases could be extended
        total = amt

    if max_amt is not None:
        total = min(total, max_amt)
    # Ensure final amount is quantized; for PER_KG this remains the extended (rate * kg)
    return Money(total.quantize(TWOPLACES), ccy)


def sum_money(items: List[Money], to_ccy: str, fx: FxConverter) -> Money:
    total = ZERO
    for m in items:
        total += fx.convert(m, to_ccy).amount
    return Money(total.quantize(TWOPLACES), to_ccy)


# ---------------------- Leg cost computation --------------------

def compute_leg_cost(
    leg: RouteLegs,
    chargeable_kg: Decimal,
    shipment_payload: ShipmentInput,
    fx: FxConverter,
    sell_currency: str,
    ts: datetime,
) -> Tuple[List[CalcLine], Dict[str, Money], bool, str]:  # Add reason string
    """
    Computes the BUY-side cost for a single leg of a journey.
    Returns the buy lines, the context, a flag if manual rating is required, and the reason.
    """
    buy_lines: List[CalcLine] = []
    buy_context: Dict[str, Money] = {}
    is_incomplete = False
    manual_reason = ""

    # 1. --- Consolidated Manual Rate Checks ---
    if shipment_payload.commodity_code != 'GCR':
        is_incomplete = True
        manual_reason = f"Specific Cargo ({shipment_payload.commodity_code})"
    elif shipment_payload.is_urgent:
        is_incomplete = True
        manual_reason = "Urgent/Express Shipment"
    elif getattr(leg.route, "requires_manual_rate", False):
        is_incomplete = True
        manual_reason = "Route flagged for manual rating (e.g., Low Volume / Complex)"

    # Only search for lanes if we don't already need a manual rate
    if not is_incomplete:
        active_cards = Ratecard.objects.filter(
            role="BUY",
            scope=leg.leg_scope,
            commodity_code='GCR',  # We only auto-rate General Cargo
            effective_date__lte=ts.date(),
        ).filter(Q(expiry_date__isnull=True) | Q(expiry_date__gte=ts.date()))

        candidate_lanes = Lane.objects.filter(
            ratecard_id__in=active_cards.values_list("id", flat=True),
            origin=leg.origin,
            dest=leg.dest,
        ).select_related("ratecard")

        # Apply optional hints
        if shipment_payload.airline_hint:
            candidate_lanes = candidate_lanes.filter(airline=shipment_payload.airline_hint)
        if shipment_payload.via_hint:
            candidate_lanes = candidate_lanes.filter(via__iata=shipment_payload.via_hint)

        # Trigger: NO_RATECARD
        if not candidate_lanes.exists():
            is_incomplete = True
            manual_reason = f"No rate card found for leg {leg.origin.iata}->{leg.dest.iata}"

    # 2. --- Handle Manual Rate Case ---
    if is_incomplete:
        placeholder_freight = Money(ZERO, "PGK")  # Use a neutral currency
        buy_lines.append(
            CalcLine(
                code="FREIGHT_MANUAL_RATE",
                description=f"Manual Rate Required: {manual_reason}",
                qty=chargeable_kg,
                unit="KG",
                unit_price=placeholder_freight,
                extended=placeholder_freight,
                is_buy=True,
                is_sell=False,
                source_ratecard_id=None,
                meta={"manual_rate_required": True, "reason": manual_reason, "leg": int(getattr(leg, 'sequence', 0) or 0)},
            )
        )
        return buy_lines, buy_context, is_incomplete, manual_reason

    # 3. --- Proceed with Automatic GCR Rating ---
    # Evaluate options per lane
    lanes = list(candidate_lanes)
    buy_options: List[Tuple[Lane, Decimal, LaneBreak, Money]] = []
    for lane in lanes:
        cfg = RatecardConfig.objects.filter(ratecard_id=lane.ratecard_id).first()
        dim = d(cfg.dim_factor_kg_per_m3 if cfg else Decimal(167))
        lane_chargeable = calculate_chargeable_weight_per_piece(shipment_payload.pieces, dim)

        rc_lane = lane.ratecard if hasattr(lane, "ratecard") else Ratecard.objects.get(id=lane.ratecard_id)
        if getattr(rc_lane, "rate_strategy", None) == "FLAT_PER_KG":
            flat_break = LaneBreak.objects.filter(lane_id=lane.id, break_code="FLAT").first()
            if not flat_break:
                logging.warning(f"Lane {lane.id} marked FLAT_PER_KG but missing FLAT break; skipping.")
                continue
            base = Money((d(flat_break.per_kg) * lane_chargeable).quantize(TWOPLACES), rc_lane.currency)
            brk = flat_break
        else:
            brk, base = pick_best_break(lane, lane_chargeable)
        buy_options.append((lane, lane_chargeable, brk, base))

    # Pick cheapest option for this leg in SELL currency to normalize comparison
    def to_sell_ccy(m: Money) -> Decimal:
        return fx.convert(m, sell_currency).amount

    lane, chosen_chargeable_kg, chosen_break, base_freight = min(buy_options, key=lambda x: to_sell_ccy(x[3]))
    rc_buy = Ratecard.objects.get(id=lane.ratecard_id)

    # BUY freight line per leg
    buy_lines.append(
        CalcLine(
            code="FREIGHT",
            description=f"Leg {getattr(leg, 'sequence', '?')}: {leg.origin.iata}->{leg.dest.iata} ({chosen_break.break_code})",
            qty=chosen_chargeable_kg,
            unit="KG",
            unit_price=Money((base_freight.amount/(chosen_chargeable_kg or Decimal(1))).quantize(FOURPLACES), base_freight.currency),
            extended=base_freight,
            is_buy=True,
            is_sell=False,
            source_ratecard_id=rc_buy.id,
            meta={"leg": int(getattr(leg, 'sequence', 0) or 0), "scope": leg.leg_scope, "service_type": leg.service_type, "break": chosen_break.break_code},
        )
    )
    buy_context["FREIGHT"] = base_freight

    # BUY fees per leg
    fees = RatecardFee.objects.filter(ratecard_id=rc_buy.id).select_related("fee_type")
    leg_ctx: Dict[str, Money] = {"FREIGHT": base_freight, "secondary_screening_flag": shipment_payload.flags.get("secondary_screening", False)}
    for fee in fees:
        fee_type = FeeType.objects.get(id=fee.fee_type_id)
        line_money = compute_fee_amount(fee, chosen_chargeable_kg, leg_ctx)
        if line_money.amount <= 0:
            continue
        leg_ctx[fee_type.code] = line_money
        buy_context[fee_type.code] = line_money
        _basis_buy = _normalize_basis(getattr(fee_type, "basis", None))
        _qty = chosen_chargeable_kg if _basis_buy == "PER_KG" else Decimal(1)
        _unit = "KG" if _basis_buy == "PER_KG" else "EA"
        _unit_price_amt = (line_money.amount/(chosen_chargeable_kg or Decimal(1)) if _basis_buy == "PER_KG" else line_money.amount).quantize(FOURPLACES)
        buy_lines.append(
            CalcLine(
                code=fee_type.code,
                description=fee_type.description,
                qty=_qty,
                unit=_unit,
                unit_price=Money(_unit_price_amt, line_money.currency),
                extended=line_money,
                is_buy=True,
                is_sell=False,
                source_ratecard_id=rc_buy.id,
                meta={"leg": int(getattr(leg, 'sequence', 0) or 0), "scope": leg.leg_scope, "service_type": leg.service_type},
            )
        )

    return buy_lines, buy_context, is_incomplete, manual_reason


# ----------------------- SELL computation ------------------------

def compute_sell_lines(sell_card: Ratecard, buy_context: Dict[str, Money], kg: Decimal, service_scope: str = "AIRPORT_AIRPORT") -> List[CalcLine]:
    lines: List[CalcLine] = []
    items = (
        ServiceItem.objects
        .filter(ratecard_id=sell_card.id)
        .select_related("service")
    )
    links = {l.sell_item_id: l for l in SellCostLink.objects.filter(sell_item_id__in=[i.id for i in items])}

    # Determine which sides require door services (cartage and clearance)
    needs_origin_services = service_scope in {"DOOR_AIRPORT", "DOOR_DOOR"}
    needs_dest_services = service_scope in {"AIRPORT_DOOR", "DOOR_DOOR"}

    # Common service code groups for flexible matching against seeded data
    cartage_origin_codes = {"CARTAGE_PICKUP", "CARTAGE_ORIGIN", "ORIGIN_CARTAGE", "PICKUP", "CARTAGE"}
    cartage_dest_codes = {"CARTAGE_DELIVERY", "CARTAGE_DEST", "DEST_CARTAGE", "DELIVERY", "CARTAGE"}
    clearance_origin_codes = {"CUSTOMS_CLEARANCE_ORIGIN", "CUSTOMS_ORIGIN", "EXPORT_CLEARANCE", "ORIGIN_CLEARANCE"}
    clearance_dest_codes = {"CUSTOMS_CLEARANCE_DEST", "CUSTOMS_CLEARANCE", "CUSTOMS_DEST", "IMPORT_CLEARANCE", "DEST_CLEARANCE"}

    def include_service_by_scope(code: str) -> bool:
        """Return True if a SELL service code should be included for the selected scope."""
        uc = (code or "").upper()
        # Origin cartage/clearance only if door at origin
        if uc in cartage_origin_codes and not needs_origin_services:
            return False
        if uc in clearance_origin_codes and not needs_origin_services:
            return False
        # Destination cartage/clearance only if door at destination
        if uc in cartage_dest_codes and not needs_dest_services:
            return False
        if uc in clearance_dest_codes and not needs_dest_services:
            return False
        # Default include
        return True

    for it in items:
        svc = it.service
        code = svc.code
        desc = svc.name
        ccy = it.currency
        tax_pct = d(it.tax_pct)
        basis = _normalize_basis(getattr(svc, "basis", None))
        qty = d(kg) if basis == "PER_KG" else Decimal(1)

        # Scope gating for door-related services (cartage and customs clearance)
        if not include_service_by_scope(code):
            continue
        # Optional: if a separate FSC for cartage is present, include it only when either side needs cartage
        if code == "CARTAGE_FSC" and not (needs_origin_services or needs_dest_services):
            continue

        # Determine the underlying BUY cost (if linked)
        buy_sum = ZERO
        if it.id in links:
            ln = links[it.id]
            # The FK uses to_field='code'; use the raw id (code string) for lookup
            buy_code = getattr(ln, "buy_fee_code_id", None) or (ln.buy_fee_code.code if ln.buy_fee_code else None)
            if buy_code and buy_code in buy_context:
                buy_sum = d(buy_context[buy_code].amount)

        # Compute the SELL amount
        sell_amt = ZERO
        if basis != "PERCENT_OF":
            if it.amount is not None:
                unit_price = d(it.amount)
                if basis == "PER_KG":
                    sell_amt = unit_price * d(kg)
                else:
                    sell_amt = unit_price

                # Apply min/max
                if it.min_amount is not None:
                    sell_amt = max(sell_amt, d(it.min_amount))
                if it.max_amount is not None:
                    sell_amt = min(sell_amt, d(it.max_amount))

        # Percent-of logic (e.g., Fuel % of Cartage)
        if svc.basis == "PERCENT_OF" and it.percent_of_service_code:
            ref = it.percent_of_service_code
            ref_line = next((l for l in lines if l.code == ref and l.is_sell), None)
            if ref_line:
                pct = d(it.amount or ZERO)  # amount stores fraction e.g. 0.10
                sell_amt = (ref_line.extended.amount * pct).quantize(TWOPLACES)

        # Mapping rule to adjust SELL using BUY cost
        if it.id in links:
            ln = links[it.id]
            if ln.mapping_type == "PASS_THROUGH":
                sell_amt = buy_sum
            elif ln.mapping_type == "FIXED_OVERRIDE":
                pass  # already set from it.amount/min
            elif ln.mapping_type == "COST_PLUS_PCT":
                pct = d(ln.mapping_value or ZERO)
                # Apply margin
                sell_amt = (buy_sum * (Decimal(1) + pct)).quantize(TWOPLACES)
                # For Air Freight, round up to nearest 0.05 after margin
                if svc.code == "AIR_FREIGHT":
                    sell_amt = round_up_nearest_0_05(sell_amt)
            elif ln.mapping_type == "COST_PLUS_ABS":
                inc = d(ln.mapping_value or ZERO)
                sell_amt = (buy_sum + inc).quantize(TWOPLACES)

        # Enforce SELL-side min/max even after mapping (e.g., SEC min K5.00)
        if it.min_amount is not None:
            sell_amt = max(sell_amt, d(it.min_amount))
        if it.max_amount is not None:
            sell_amt = min(sell_amt, d(it.max_amount))

        line = CalcLine(
            code=code,
            description=desc,
            qty=qty,
            unit="KG" if basis == "PER_KG" else "EA",
            unit_price=Money((sell_amt/qty if qty else sell_amt).quantize(FOURPLACES), ccy),
            extended=Money(sell_amt.quantize(TWOPLACES), ccy),
            is_buy=False,
            is_sell=True,
            tax_pct=tax_pct,
            source_ratecard_id=sell_card.id,
        )
        lines.append(line)

    return lines


# ------------------------- Orchestrator --------------------------

def compute_quote(payload: ShipmentInput, provider_hint: Optional[int] = None, caf_pct: Decimal = Decimal("0.065")) -> CalcResult:
    """Main entry point. Returns full buy/sell breakdown and snapshot.
    provider_hint: optional provider_id to force PX vs Agent.
    caf_pct: CAF uplift factor applied on FX (e.g., 0.065 = 6.5%).
    """
    ts = now()

    # 1. Resolve payer organization, audience, and sell currency
    try:
        payer_org = Organizations.objects.get(id=payload.org_id)
    except Organizations.DoesNotExist:
        raise ValueError("Invalid Payer/Organization ID.")

    audience = payer_org.audience
    if payer_org.country_code == 'PG':
        sell_currency = 'PGK'
    elif payer_org.country_code == 'AU':
        sell_currency = 'AUD'
    else:
        sell_currency = 'USD'

    # Pricing policy (per audience)
    pol = PricingPolicy.objects.filter(audience=audience).first()
    fx = FxConverter(caf_on_fx=bool(pol.caf_on_fx if pol else True), caf_pct=caf_pct)

    origin_iata = (payload.origin_iata or "").upper()
    dest_iata = (payload.dest_iata or "").upper()

    if not origin_iata or not dest_iata:
        raise ValueError("Both origin_iata and dest_iata are required for quoting.")

    try:
        origin_station = Station.objects.get(iata=origin_iata)
    except Station.DoesNotExist as exc:
        raise ValueError('Unknown origin station {0}.'.format(origin_iata)) from exc

    try:
        dest_station = Station.objects.get(iata=dest_iata)
    except Station.DoesNotExist as exc:
        raise ValueError('Unknown destination station {0}.'.format(dest_iata)) from exc

    payload.origin_iata = origin_iata
    payload.dest_iata = dest_iata

    # Auto-detect shipment type using station country codes
    def infer_shipment_type(origin_station, dest_station):
        origin_country = (origin_station.country or "").upper()
        dest_country = (dest_station.country or "").upper()

        if origin_country and dest_country and origin_country == dest_country:
            return "DOMESTIC"
        if origin_country == "PG" and dest_country != "PG":
            return "EXPORT"
        if origin_country != "PG" and dest_country == "PG":
            return "IMPORT"
        if origin_country != dest_country:
            return "EXPORT"
        return "EXPORT"

    payload.shipment_type = infer_shipment_type(origin_station, dest_station)

    payment_term = (payload.payment_term or "PREPAID").upper()
    if payment_term not in {"PREPAID", "COLLECT"}:
        payment_term = "PREPAID"
    payload.payment_term = payment_term

    # 1) BUY pricing: support multi-leg via Routes/RouteLegs when available

    # TODO: Implement logic for Incoterm-based fee inclusion.
    # Example scaffolding to guide future implementation:
    # if (payload.incoterm or '').upper() == 'DAP':
    #     # Ensure destination-side charges are included regardless of provider defaults
    #     # e.g., enforce DEST cartage/clearance if scope implies door or if DAP mandates it
    #     pass
    # elif (payload.incoterm or '').upper() == 'EXW':
    #     # Typically buyer handles export; may exclude origin services from SELL
    #     pass
    # elif (payload.incoterm or '').upper() == 'FOB':
    #     # Seller covers origin charges to onboard; adjust SELL mapping accordingly
    #     pass
    # Define sell scope for SELL card lookup regardless of routing mode
    scope_for_sell = "INTERNATIONAL" if payload.shipment_type in ["IMPORT", "EXPORT"] else "DOMESTIC"
    buy_direction = None  # for snapshot in single-leg mode
    # Determine route based on origin/dest station countries and shipment type
    route = None
    try:
        route_candidates = (
            Routes.objects.filter(
                origin_country=(origin_station.country or "").upper(),
                dest_country=(dest_station.country or "").upper(),
                shipment_type=payload.shipment_type,
            )
            .annotate(
                origin_match=Case(
                    When(legs__origin__iata=origin_iata, then=Value(0)),
                    default=Value(1),
                    output_field=IntegerField(),
                ),
                dest_match=Case(
                    When(legs__dest__iata=dest_iata, then=Value(0)),
                    default=Value(1),
                    output_field=IntegerField(),
                ),
            )
            .order_by("origin_match", "dest_match", "id")
            .distinct()
        )
        route = route_candidates.first()
    except Exception:
        route = None

    # Helper to build active BUY cards for a given scope/direction
    def active_buy_cards(scope_val: str, direction_val: str):
        qs = Ratecard.objects.filter(
            role="BUY",
            scope=scope_val,
            direction=direction_val,
            effective_date__lte=ts.date(),
        ).filter(Q(expiry_date__isnull=True) | Q(expiry_date__gte=ts.date()))
        if provider_hint:
            qs = qs.filter(provider_id=provider_hint)
        return qs

    # Aggregates across all legs
    buy_lines: List[CalcLine] = []
    # Temporary accumulator of BUY amounts before SELL mapping (code -> list[Money])
    buy_context_lists: Dict[str, List[Money]] = {}
    lane_warnings: List[str] = []
    chosen_breaks: List[Dict] = []
    per_leg_chargeables: List[Decimal] = []
    first_rc_buy_id: Optional[int] = None

    def acc_context(code: str, money: Money):
        if code not in buy_context_lists:
            buy_context_lists[code] = []
        buy_context_lists[code].append(money)

    # Select direction defaulting logic
    def derive_direction(scope_val: str) -> str:
        if scope_val == "DOMESTIC":
            return "DOMESTIC"
        # INTERNATIONAL legs: BUY as EXPORT from the leg origin
        return "EXPORT"

    manual_any = False
    manual_reasons: List[str] = []

    if route:
        legs_qs = RouteLegs.objects.filter(route_id=route.id).select_related("origin", "dest").order_by("sequence", "id")
        legs = select_route_legs_for_payload(list(legs_qs), payload.origin_iata, payload.dest_iata)
        if not legs:
            raise ValueError(
                f"Configured route has no legs defined for {payload.origin_iata}->{payload.dest_iata}"
            )

        for leg in legs:
            # Use default 167 dim factor for placeholder kg in manual line
            placeholder_kg = calculate_chargeable_weight_per_piece(payload.pieces, Decimal(167))
            leg_lines, leg_ctx, is_manual, reason = compute_leg_cost(
                leg=leg,
                chargeable_kg=placeholder_kg,
                shipment_payload=payload,
                fx=fx,
                sell_currency=sell_currency,
                ts=ts,
            )

            if is_manual:
                manual_any = True
                if reason and reason not in manual_reasons:
                    manual_reasons.append(reason)

            # Aggregate results
            buy_lines.extend(leg_lines)
            for code, money in leg_ctx.items():
                acc_context(code, money)

            # Extract freight info for snapshot and kg aggregation
            for cl in leg_lines:
                if cl.code == "FREIGHT":
                    per_leg_chargeables.append(d(cl.qty))
                    # capture chosen break if present in meta
                    br = cl.meta.get("break") if isinstance(cl.meta, dict) else None
                    chosen_breaks.append({
                        "leg": int(cl.meta.get("leg") if isinstance(cl.meta, dict) else int(getattr(leg, 'sequence', 0) or 0)),
                        "lane_id": None,
                        "break": br,
                        "currency": cl.extended.currency,
                        "amount": str(cl.extended.amount),
                    })
                    if first_rc_buy_id is None and cl.source_ratecard_id:
                        first_rc_buy_id = cl.source_ratecard_id
    else:
        # Fallback to single-leg behaviour if no route is defined: use consolidated leg logic
        from types import SimpleNamespace
        if payload.shipment_type in ["IMPORT", "EXPORT"]:
            scope_single = "INTERNATIONAL"
            buy_direction = "EXPORT"
        else:
            scope_single = "DOMESTIC"
            buy_direction = payload.shipment_type

        try:
            st_o = Station.objects.get(iata=payload.origin_iata)
            st_d = Station.objects.get(iata=payload.dest_iata)
        except Exception:
            raise ValueError("Invalid origin or destination IATA code")

        leg = SimpleNamespace(route=None, leg_scope=scope_single, origin=st_o, dest=st_d, service_type="LINEHAUL", sequence=1)
        placeholder_kg = calculate_chargeable_weight_per_piece(payload.pieces, Decimal(167))
        leg_lines, leg_ctx, is_manual, reason = compute_leg_cost(
            leg=leg,
            chargeable_kg=placeholder_kg,
            shipment_payload=payload,
            fx=fx,
            sell_currency=sell_currency,
            ts=ts,
        )

        if is_manual:
            manual_any = True
            if reason and reason not in manual_reasons:
                manual_reasons.append(reason)

        # Aggregate results
        buy_lines.extend(leg_lines)
        for code, money in leg_ctx.items():
            acc_context(code, money)

        # Extract info for snapshot
        for cl in leg_lines:
            if cl.code == "FREIGHT":
                per_leg_chargeables.append(d(cl.qty))
                br = cl.meta.get("break") if isinstance(cl.meta, dict) else None
                chosen_breaks.append({
                    "leg": int(cl.meta.get("leg") if isinstance(cl.meta, dict) else 1),
                    "lane_id": None,
                    "break": br,
                    "currency": cl.extended.currency,
                    "amount": str(cl.extended.amount),
                })
                if first_rc_buy_id is None and cl.source_ratecard_id:
                    first_rc_buy_id = cl.source_ratecard_id


    # 3) Determine the correct SELL audience based on payment term
    sell_direction = payload.shipment_type

    if payload.payment_term == "PREPAID":
        # For prepaid shipments, the payer is the local customer
        target_audience = "PNG_CUSTOMER_PREPAID"
    elif payload.payment_term == "COLLECT":
        # For collect shipments, the payer is the overseas agent/partner
        target_audience = "OVERSEAS_AGENT_COLLECT"
    else:
        # Fallback to the organization's default audience if payment_term is not specified
        target_audience = audience

    # Query for the SELL rate card using the specific target audience

    sell_qs_base = Ratecard.objects.filter(
        role="SELL",
        scope=scope_for_sell,
        direction=sell_direction,
        effective_date__lte=ts.date(),
    ).filter(
        Q(audience__code=target_audience) | Q(audience_old=target_audience),
        Q(expiry_date__isnull=True) | Q(expiry_date__gte=ts.date()),
    )


    sell_card = sell_qs_base.filter(currency=sell_currency).first()
    if not sell_card:
        sell_card = sell_qs_base.first()
    if not sell_card:
        raise ValueError(
            f"No SELL ratecard found for audience '{target_audience}' and payment term '{payload.payment_term}'."
        )

    # Build consolidated BUY context in SELL card currency for downstream SELL mapping
    buy_context: Dict[str, Money] = {}
    for code, monies in buy_context_lists.items():
        total = ZERO
        for m in monies:
            total += fx.convert(m, sell_card.currency).amount
        buy_context[code] = Money(total.quantize(TWOPLACES), sell_card.currency)

    # For SELL KG-basis, use a representative chargeable weight
    if per_leg_chargeables:
        chargeable_kg = max(per_leg_chargeables)
    else:
        # In manual or non-freight scenarios where no per-leg FREIGHT was produced,
        # fall back to computing chargeable weight from the request pieces.
        chargeable_kg = calculate_chargeable_weight_per_piece(payload.pieces, Decimal(167))

    sell_lines = compute_sell_lines(sell_card, buy_context, chargeable_kg, payload.service_scope)

    # 4) Totals & taxes (sell lines)
    # Track FX usage to document CAF-on-FX behavior
    fx_pairs_used = set()

    def convert_track(m: Money) -> Money:
        if m.currency != sell_currency:
            fx_pairs_used.add(f"{m.currency}->{sell_currency}")
        return fx.convert(m, sell_currency)

    # Convert BUY to sell currency for total
    total_buy_amount = ZERO
    for bl in buy_lines:
        total_buy_amount += convert_track(bl.extended).amount
    total_buy = Money(total_buy_amount.quantize(TWOPLACES), sell_currency)

    tax_total = ZERO
    sell_sum = ZERO
    for l in sell_lines:
        sell_amt_money = convert_track(l.extended)
        sell_amt = sell_amt_money.amount
        tax = (sell_amt * (l.tax_pct/Decimal(100))).quantize(TWOPLACES)
        sell_sum += sell_amt + tax
        tax_total += tax

    # Apply margin before final rounding
    sell_sum_before_rounding = sell_sum.quantize(TWOPLACES)

    # Final rounding rule: round up total SELL to next whole
    final_sell_total = round_up_to_next_whole(sell_sum_before_rounding)

    totals = {
        "buy_total": Money(total_buy.amount, sell_currency),
        "sell_total": Money(final_sell_total, sell_currency),
        "tax_total": Money(Decimal(tax_total).quantize(TWOPLACES), sell_currency),
        "margin_abs": Money((final_sell_total - total_buy.amount).quantize(TWOPLACES), sell_currency),
        "margin_pct": Money(((final_sell_total - total_buy.amount) / (final_sell_total or Decimal(1))).quantize(FOURPLACES), "%"),
    }

    # 5) Snapshot
    snapshot = {
        "ts": ts.isoformat(),
        "shipment_type": payload.shipment_type,
        "service_scope": payload.service_scope,
        "payment_term": payload.payment_term,
        "manual_rate_required": bool(manual_any),
        "manual_reasons": manual_reasons,
        # Backward-compat: expose first BUY ratecard id if available
        "buy_ratecard_id": first_rc_buy_id,
        "sell_ratecard_id": sell_card.id,
        # Dim factor reference (first leg if present)
        "dim_factor": float(
            RatecardConfig.objects.filter(ratecard_id=first_rc_buy_id).first().dim_factor_kg_per_m3
            if (first_rc_buy_id and RatecardConfig.objects.filter(ratecard_id=first_rc_buy_id).exists()) else 167
        ),
        # FX & CAF documentation
        "fx_caf_pct": float(caf_pct),
        "caf_on_fx": bool(fx.caf_on_fx),
        "fx_pairs_used": sorted(list(fx_pairs_used)),
        "chargeable_kg": float(chargeable_kg),
        # Backward-compat: chosen_break for single-leg; legs_breaks for multi-leg
        "chosen_break": (chosen_breaks[0]["break"] if chosen_breaks else None),
        "legs_breaks": chosen_breaks,
        # Directional decoupling
        "buy_direction": ("MULTI" if route else buy_direction),
        "sell_direction": sell_direction,
        # Organization context
        "org_id": payer_org.id,
        "audience": audience,
        "sell_currency": sell_currency,
        # Data quality warnings (non-blocking)
        "break_warnings": lane_warnings,
        # Route context (if used)
        "route": ({
            "id": int(route.id),
            "name": route.name,
            "shipment_type": route.shipment_type,
        } if route else None),
    }

    return CalcResult(buy_lines=buy_lines, sell_lines=sell_lines, totals=totals, snapshot=snapshot)


# -------------------------- Validation --------------------------


def validate_break_monotonic(lane_id: int) -> List[str]:
    """Return warnings if lane breaks are not monotonic decreasing per-kg."""
    warnings: List[str] = []
    order = ["N", "45", "100", "250", "500", "1000"]
    rows = {b.break_code: d(b.per_kg or ZERO) for b in LaneBreak.objects.filter(lane_id=lane_id)}
    last = None
    for code in order:
        if code not in rows:
            continue
        if last is not None and rows[code] > last:
            warnings.append(f"Per-kg for {code} ({rows[code]}) exceeds previous break ({last}) - check data.")
        last = rows[code]
    return warnings


def outlier_guard(per_kg: Decimal) -> Optional[str]:
    if per_kg > Decimal(50):
        return f"Per-kg looks unusually high ({per_kg}). Did you mean {per_kg/Decimal(10)}?"
    return None


