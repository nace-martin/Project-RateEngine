from __future__ import annotations

import logging
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Optional, Tuple

from django.db.models import Case, IntegerField, Q, Value, When
from django.utils.timezone import now

from ..dataclasses import CalcLine, CalcResult, Money, Piece, ShipmentInput, PricingContext
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
from .business_rules import apply_business_rules, BusinessRulesError
from .fx_service import FxConverter
from .utils import (
    FOURPLACES,
    TWOPLACES,
    ZERO,
    d,
    round_up_nearest_0_05,
    round_up_to_next_whole,
)

COUNTRY_CURRENCY_MAP = {
    "PG": "PGK",
    "AU": "AUD",
    "US": "USD",
}
DEFAULT_FOREIGN_CURRENCY = "USD"


ORIGIN_CATEGORY_MAP = {
    "AIR_FREIGHT": "Transportation Freight Charges",
    "PICKUP": "Origin Handling Charges",
    "PICKUP_FUEL": "Origin Handling Charges",
    "CTO": "Cargo Handling & Security Charges",
    "X_RAY": "Cargo Handling & Security Charges",
    "DOC_FEE": "Documentation & Regulatory Compliance",
    "AGENCY_FEE": "Documentation & Regulatory Compliance",
    "AWB_FEE": "Documentation & Regulatory Compliance",
}
DESTINATION_CATEGORY_MAP = {
    "CUSTOMS_CLEARANCE": "Customs & Regulatory Fees",
    "AGENCY_FEE": "Customs & Regulatory Fees",
    "DOCUMENTATION_FEE": "Customs & Regulatory Fees",
    "HANDLING_GENERAL": "Handling & Terminal Charges",
    "TERMINAL_FEE_INT": "Handling & Terminal Charges",
    "CARTAGE_DELIVERY": "Inland Transportation & Associated Costs",
    "FUEL_SURCHARGE_CARTAGE": "Inland Transportation & Associated Costs",
}
DESTINATION_GST_PCT = Decimal("10.0")


def currency_for_country(code: Optional[str]) -> str:
    if not code:
        return DEFAULT_FOREIGN_CURRENCY
    return COUNTRY_CURRENCY_MAP.get(code.upper(), DEFAULT_FOREIGN_CURRENCY)


def determine_invoice_currency(shipment_type: str, payment_term: str, origin_country: Optional[str], dest_country: Optional[str]) -> str:
    st = (shipment_type or "").upper()
    term = (payment_term or "PREPAID").upper()
    origin_currency = currency_for_country(origin_country)
    dest_currency = currency_for_country(dest_country)

    if st == "IMPORT":
        return "PGK" if term == "COLLECT" else origin_currency
    if st == "EXPORT":
        return dest_currency if term == "COLLECT" else "PGK"
    # DOMESTIC or fallback
    return "PGK"


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


def pick_best_break(lane: Lane, chargeable_kg: Decimal, breaks: List[LaneBreak]) -> Tuple[LaneBreak, Money]:
    """Return chosen LaneBreak and base freight in lane currency (ratecard.currency)."""
    by_code = {b.break_code: b for b in breaks}

    try:
        rc = Ratecard.objects.get(id=lane.ratecard_id)
        ccy = rc.currency
    except Ratecard.DoesNotExist:
        raise ValueError(f"Ratecard with ID {lane.ratecard_id} not found for lane {lane.id}")

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
    b = re.sub(r"[\s-]+", "_", b)  # collapse spaces/dashes to underscore
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
    try:
        ft = FeeType.objects.get(id=fee.fee_type_id)
        code = ft.code
    except FeeType.DoesNotExist:
        raise ValueError(f"FeeType with ID {fee.fee_type_id} not found for ratecard fee {fee.id}")
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

        candidate_lanes = (
            Lane.objects.filter(
                ratecard_id__in=active_cards.values_list("id", flat=True),
                origin=leg.origin,
                dest=leg.dest,
            )
            .select_related("ratecard", "ratecard__ratecardconfig")
            .prefetch_related("lanebreaks_set")
        )

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
        # Use prefetched/selected related objects
        cfg = lane.ratecard.ratecardconfig if hasattr(lane.ratecard, "ratecardconfig") else None
        dim = d(cfg.dim_factor_kg_per_m3 if cfg else Decimal(167))
        lane_chargeable = calculate_chargeable_weight_per_piece(shipment_payload.pieces, dim)

        rc_lane = lane.ratecard
        lane_breaks = list(lane.lanebreaks_set.all())

        if getattr(rc_lane, "rate_strategy", None) == "FLAT_PER_KG":
            flat_break = next((b for b in lane_breaks if b.break_code == "FLAT"), None)
            if not flat_break:
                logging.warning(f"Lane {lane.id} marked FLAT_PER_KG but missing FLAT break; skipping.")
                continue
            base = Money((d(flat_break.per_kg) * lane_chargeable).quantize(TWOPLACES), rc_lane.currency)
            brk = flat_break
        else:
            brk, base = pick_best_break(lane, lane_chargeable, lane_breaks)
        buy_options.append((lane, lane_chargeable, brk, base))

    # Pick cheapest option for this leg in SELL currency to normalize comparison
    def to_sell_ccy(m: Money) -> Decimal:
        return fx.convert(m, sell_currency).amount

    lane, chosen_chargeable_kg, chosen_break, base_freight = min(buy_options, key=lambda x: to_sell_ccy(x[3]))
    rc_buy = lane.ratecard

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
            meta={"leg": int(getattr(leg, 'sequence', 0) or 0), "scope": leg.leg_scope, "service_type": leg.service_type},
        )
    )
    buy_context["FREIGHT"] = base_freight

    # BUY fees per leg
    fees = RatecardFee.objects.filter(ratecard_id=rc_buy.id).select_related("fee_type")
    leg_ctx: Dict[str, Money] = {"FREIGHT": base_freight, "secondary_screening_flag": shipment_payload.flags.get("secondary_screening", False)}
    for fee in fees:
        fee_type = fee.fee_type
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


def normalize_scope_value(service_scope: Optional[str]) -> str:
    scope = (service_scope or "AIRPORT_AIRPORT").upper().strip()
    # Fast path for abbreviations
    abbr = {
        "A2A": "AIRPORT_AIRPORT",
        "A2D": "AIRPORT_DOOR",
        "D2A": "DOOR_AIRPORT",
        "D2D": "DOOR_DOOR",
    }
    if scope in abbr:
        return abbr[scope]
    # Phrase cleanup
    scope = re.sub(r"[\s-]+", "_", scope)
    scope = re.sub(r"_+", "_", scope).strip("_")
    canonical = {
        "DOOR_TO_DOOR": "DOOR_DOOR",
        "DOOR_TO_AIRPORT": "DOOR_AIRPORT",
        "AIRPORT_TO_DOOR": "AIRPORT_DOOR",
        "AIRPORT_TO_AIRPORT": "AIRPORT_AIRPORT",
    }
    return canonical.get(scope, scope)



def compute_sell_lines(
    sell_card: Ratecard,
    buy_context: Dict[str, Money],
    kg: Decimal,
    service_scope: str,
    incoterm: str,
    fx: FxConverter,
    target_currency: str,
    shipment_type: str,
    extra_cards: Optional[List[Ratecard]] = None,
    origin_station: Optional[Station] = None,
    dest_station: Optional[Station] = None,
    pricing_context: Optional[PricingContext] = None,  # Add this parameter
) -> List[CalcLine]:
    cards: List[Ratecard] = [sell_card] + list(extra_cards or [])
    card_segments = {sell_card.id: "primary"}
    if extra_cards:
        for extra in extra_cards:
            card_segments[extra.id] = "origin"

    items = (
        ServiceItem.objects
        .filter(ratecard_id__in=[c.id for c in cards])
        .select_related("service")
    )

    # Apply business rules service filtering
    if pricing_context and pricing_context.applicable_services:
        # Filter ServiceItems to only include those specified by business rules
        applicable_service_codes = set(pricing_context.applicable_services)
        items = items.filter(service__code__in=applicable_service_codes)
        logging.debug(f"Filtered ServiceItems to {len(applicable_service_codes)} applicable services from business rules")
    else:
        logging.debug("No business rules service filtering applied - using all ServiceItems")

    items = list(items)  # Convert to list for processing
    links = {l.sell_item_id: l for l in SellCostLink.objects.filter(sell_item_id__in=[i.id for i in items])}

    scope = normalize_scope_value(service_scope)
    needs_origin_services = scope in {"DOOR_AIRPORT", "DOOR_DOOR"}
    needs_dest_services = scope in {"AIRPORT_DOOR", "DOOR_DOOR"}

    cartage_origin_codes = {"CARTAGE_PICKUP", "CARTAGE_ORIGIN", "ORIGIN_CARTAGE", "PICKUP", "PICKUP_FUEL"}
    cartage_dest_codes = {"CARTAGE_DELIVERY", "CARTAGE_DEST", "DEST_CARTAGE", "DELIVERY"}
    clearance_origin_codes = {"CUSTOMS_CLEARANCE_ORIGIN", "CUSTOMS_ORIGIN", "EXPORT_CLEARANCE"}
    clearance_dest_codes = {"CUSTOMS_CLEARANCE_DEST", "CUSTOMS_CLEARANCE", "CUSTOMS_DEST", "IMPORT_CLEARANCE"}
    excluded_sell_codes = {"CUSTOMS_ENTRY_PAGE", "DISBURSEMENT_FEE"}

    lines: List[CalcLine] = []

    for it in items:
        segment = card_segments.get(it.ratecard_id, "primary")
        svc = it.service
        code = (svc.code or "").upper()
        logging.debug(f"Processing service item: id={it.id}, code={code}, basis={_normalize_basis(getattr(svc, 'basis', None))}, amount={it.amount}")

        if code in excluded_sell_codes:
            logging.debug(f"Skipping {code} due to excluded_sell_codes")
            continue

        if segment == "origin":
            if not needs_origin_services:
                continue
            if code in cartage_dest_codes or code in clearance_dest_codes:
                continue
        else:
            if code in cartage_origin_codes and not needs_origin_services:
                continue
            if code in clearance_origin_codes and not needs_origin_services:
                continue
            if code in cartage_dest_codes and not needs_dest_services:
                continue
            if code in clearance_dest_codes and not needs_dest_services:
                continue

        desc = svc.name
        if segment == "origin":
            desc = f"Origin - {desc}"

        tax_pct = d(it.tax_pct)
        if segment != "origin":
            tax_pct = DESTINATION_GST_PCT

        basis = _normalize_basis(getattr(svc, "basis", None))
        qty = d(kg) if basis == "PER_KG" else Decimal(1)
        unit = "KG" if basis == "PER_KG" else "EA"

        link = links.get(it.id)
        buy_sum_card = ZERO
        if link:
            buy_code = getattr(link, "buy_fee_code_id", None) or (link.buy_fee_code.code if link.buy_fee_code else None)
            native_money = buy_context.get(buy_code) if buy_code else None
            if native_money:
                money_in_card = native_money
                if native_money.currency and native_money.currency != it.currency:
                    money_in_card = fx.convert(native_money, it.currency)
                buy_sum_card = d(money_in_card.amount)

        # --- BEGIN safe amount calc ---
        from decimal import Decimal

        # default: nothing computed yet
        sell_amt_card = ZERO
        # default target ccy for the line: prefer the SELL item currency, fallback to provided target
        tgt_ccy = it.currency or target_currency

        # placeholders for lane-based metadata if used
        chosen_lane_id: Optional[int] = None
        chosen_break_code: Optional[str] = None

        if basis == "PERCENT_OF" and getattr(it, "percent_of_service_code", None):
            ref_code = it.percent_of_service_code
            # look for a prior SELL line with that code
            ref_line = next((l for l in lines if getattr(l, "is_sell", False) and l.code == ref_code), None)
            if not ref_line:
                # we can’t compute the percent-of base -> skip adding this item entirely
                logging.debug(f"Skipping {code} due to missing ref_line for PERCENT_OF")
                continue
            ref_money = Money(d(ref_line.extended.amount), ref_line.extended.currency)
            if ref_money.currency != tgt_ccy:
                ref_money = fx.convert(ref_money, tgt_ccy)
            pct = d(it.amount or ZERO)   # amount field holds fraction, e.g. 0.10 for 10%
            sell_amt_card = (ref_money.amount * pct).quantize(TWOPLACES)

        else:
            # Simple fixed price (per-kg or per-shipment) OR ratecard lane-based when it.amount is None
            logging.debug(f"Before if it.amount is not None: it.amount={it.amount}, basis={basis}")
            if it.amount is not None:
                base = d(it.amount)
                sell_amt_card = (base * d(kg)) if basis == "PER_KG" else base
                logging.debug(f"Inside if it.amount is not None: sell_amt_card={sell_amt_card}")
            else:
                # amount is None -> attempt to price from sell ratecard lanes for this service
                lanes_qs = Lane.objects.filter(ratecard=sell_card, origin=origin_station, dest=dest_station).prefetch_related("lanebreaks_set")

                if not lanes_qs.exists():
                    logging.warning(f"No lanes found for sell ratecard {getattr(sell_card, 'id', None)} and origin/dest {getattr(origin_station, 'iata', None)}/{getattr(dest_station, 'iata', None)}; defaulting to ZERO for service item {it.id}")
                    sell_amt_card = ZERO
                else:
                    best_amt_converted = None
                    best_choice = None  # tuple(lane, break, money)
                    for lane in lanes_qs:
                        lane_breaks = list(lane.lanebreaks_set.all())
                        # determine quantity basis for break selection
                        if basis == "PER_KG":
                            qty_for_break = d(kg)
                        elif basis == "PER_SHIPMENT":
                            qty_for_break = Decimal(1)
                        else:
                            qty_for_break = Decimal(1)
                        try:
                            chosen_break, base_money = pick_best_break(lane, qty_for_break, lane_breaks)
                        except ValueError as exc:
                            # skip lanes with no valid breaks
                            logging.warning(f"Skipping lane {getattr(lane, 'id', None)} for sell item {it.id} due to break selection error: {exc}")
                            continue
                        # Convert base_money (lane currency) to the item's currency for fair comparison
                        compare_money = base_money
                        target_compare_ccy = it.currency or sell_card.currency or target_currency
                        if compare_money.currency != target_compare_ccy:
                            try:
                                compare_money = fx.convert(compare_money, target_compare_ccy)
                            except Exception:
                                # If conversion fails, skip this lane
                                logging.warning(f"FX conversion failed from {compare_money.currency} to {target_compare_ccy} for lane {getattr(lane, 'id', None)}; skipping lane.")
                                continue
                        if best_amt_converted is None or compare_money.amount < best_amt_converted:
                            best_amt_converted = compare_money.amount
                            best_choice = (lane, chosen_break, base_money, compare_money)

                    if best_choice is None:
                        logging.warning(f"No usable lane breaks found for sell ratecard {getattr(sell_card, 'id', None)} for service item {it.id}; defaulting to ZERO")
                        sell_amt_card = ZERO
                    else:
                        lane, chosen_break, base_money_lane_ccy, base_money_in_item_ccy = best_choice
                        # Use the base amount in the lane's/native currency and set tgt_ccy accordingly so downstream FX conversion works
                        sell_amt_card = base_money_lane_ccy.amount
                        tgt_ccy = base_money_lane_ccy.currency
                        chosen_lane_id = int(getattr(lane, "id", 0) or 0)
                        chosen_break_code = getattr(chosen_break, "break_code", None)

            # Apply service-item level min/max which may override lane break min
            if it.min_amount is not None:
                sell_amt_card = max(sell_amt_card, d(it.min_amount))
            if it.max_amount is not None:
                sell_amt_card = min(sell_amt_card, d(it.max_amount))
        # At this point we either 'continue'd (skipped) or computed an amount
        line_money_card = Money(sell_amt_card, tgt_ccy)
        # --- END safe amount calc ---

        if line_money_card.currency != target_currency:
            line_money_target = fx.convert(line_money_card, target_currency)
        else:
            line_money_target = line_money_card

        qty_decimal = qty or Decimal(1)
        unit_price_amount = (line_money_target.amount / qty_decimal).quantize(FOURPLACES) if qty_decimal else line_money_target.amount.quantize(FOURPLACES)

        category_map = ORIGIN_CATEGORY_MAP if segment == "origin" else DESTINATION_CATEGORY_MAP
        meta: Dict[str, object] = {"segment": segment, "row_type": "line"}
        category = category_map.get(code)
        if category:
            meta["category"] = category

        # Attach lane/break metadata when available for debugging/snapshots
        if chosen_break_code:
            meta["break_code"] = chosen_break_code
        if chosen_lane_id is not None:
            meta["lane_id"] = chosen_lane_id

        logging.debug(f"Before append: code={code}, sell_amt_card={sell_amt_card}, line_money_card={line_money_card}, line_money_target={line_money_target}")
        lines.append(
            CalcLine(
                code=svc.code,
                description=desc,
                qty=qty,
                unit=unit,
                unit_price=Money(unit_price_amount, target_currency),
                extended=Money(line_money_target.amount.quantize(TWOPLACES), target_currency),
                is_buy=False,
                is_sell=True,
                tax_pct=tax_pct,
                source_ratecard_id=it.ratecard_id,
                meta=meta,
            )
        )
        logging.debug(f"Appended {code} to lines. Current lines: {[l.code for l in lines]}")

    return lines


def apply_margin_to_origin_lines(lines: List[CalcLine], multiplier: Decimal) -> List[CalcLine]:
    if multiplier == Decimal('1'):
        return lines
    adjusted: List[CalcLine] = []
    for line in lines:
        meta = line.meta if isinstance(line.meta, dict) else {}
        segment = meta.get('segment') if isinstance(meta, dict) else None
        if segment == 'origin':
            qty = d(line.qty) if line.qty is not None else ZERO
            extended_amount = (line.extended.amount * multiplier).quantize(TWOPLACES)
            if qty and qty != ZERO:
                unit_price_amount = (extended_amount / qty).quantize(FOURPLACES)
            else:
                unit_price_amount = extended_amount.quantize(FOURPLACES)
            meta = dict(meta or {})
            meta['margin_multiplier'] = str(multiplier)
            meta['row_type'] = 'line'
            adjusted.append(
                CalcLine(
                    code=line.code,
                    description=line.description,
                    qty=line.qty,
                    unit=line.unit,
                    unit_price=Money(unit_price_amount, line.unit_price.currency),
                    extended=Money(extended_amount, line.extended.currency),
                    is_buy=line.is_buy,
                    is_sell=line.is_sell,
                    tax_pct=line.tax_pct,
                    source_ratecard_id=line.source_ratecard_id,
                    meta=meta,
                )
            )
        else:
            if isinstance(meta, dict):
                meta = dict(meta)
                meta.setdefault('row_type', 'line')
                line.meta = meta
            adjusted.append(line)
    return adjusted



# ------------------------- Orchestrator --------------------------
# ------------------------- Orchestrator --------------------------

def compute_quote(payload: ShipmentInput, provider_hint: Optional[int] = None) -> CalcResult:
    """Main entry point. Returns full buy/sell breakdown and snapshot.
    provider_hint: optional provider_id to force PX vs Agent.
    """
    ts = now()

    # 1. Resolve payer organization, audience, and sell currency
    try:
        payer_org = Organizations.objects.get(id=payload.org_id)
    except Organizations.DoesNotExist:
        raise ValueError("Invalid Payer/Organization ID.")

    audience = payer_org.audience

    # Pricing policy (per audience)
    pol = PricingPolicy.objects.filter(audience=audience).first()
    if not pol:
        # Fallback to default values if no policy is found
        caf_buy = Decimal("0.05")
        caf_sell = Decimal("0.10")
    else:
        caf_buy = d(pol.caf_buy_pct)
        caf_sell = d(pol.caf_sell_pct)

    fx = FxConverter(caf_buy_pct=caf_buy, caf_sell_pct=caf_sell)

    # Initialize manual rating tracking
    manual_any = False
    manual_reasons: List[str] = []

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

    origin_country = (origin_station.country or '').upper()
    dest_country = (dest_station.country or '').upper()
    origin_currency = currency_for_country(origin_country)
    dest_currency = currency_for_country(dest_country)

    payload.origin_iata = origin_iata
    payload.dest_iata = dest_iata


    # Apply business rules to determine pricing context. This is done early
    # to ensure the original payload.shipment_type (which may contain a
    # movement type hint) is used.
    try:
        pricing_context = apply_business_rules(payload)
        logging.info(f"Applied business rules: {pricing_context.rule_path} -> {pricing_context.currency}, {len(pricing_context.applicable_services)} services")
        
        # The currency determined by business rules is the final invoice currency
        invoice_currency = pricing_context.currency
        
        # Validate business rule compliance
        if pricing_context.requires_manual_review:
            logging.warning(f"Business rules require manual review for {pricing_context.rule_path}: {pricing_context.description}")
            manual_any = True
            manual_reasons.append(f"Business rules require manual review: {pricing_context.description}")
        
    except BusinessRulesError as e:
        logging.warning(f"Business rules application failed, falling back to legacy logic: {e}")
        pricing_context = None

    # Auto-detect shipment type (direction) using station country codes.
    # This is used for legacy logic paths and determining buy/sell direction.
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

    inferred_shipment_type = infer_shipment_type(origin_station, dest_station)
    # Preserve the inferred type for downstream logic, but restore original payload value if needed.
    original_shipment_type_hint = payload.shipment_type
    payload.shipment_type = inferred_shipment_type

    payment_term = (payload.payment_term or "PREPAID").upper()
    if payment_term not in {"PREPAID", "COLLECT"}:
        payment_term = "PREPAID"
    payload.payment_term = payment_term

    # If business rules failed, determine currency the old way
    if not pricing_context:
        invoice_currency = determine_invoice_currency(payload.shipment_type, payment_term, origin_country, dest_country)

    # 1) BUY pricing: support multi-leg via Routes/RouteLegs when available

    # Define sell scope for SELL card lookup regardless of routing mode
    scope_for_sell = "INTERNATIONAL" if payload.shipment_type in ["IMPORT", "EXPORT"] else "DOMESTIC"
    normalized_scope = normalize_scope_value(payload.service_scope)
    needs_origin_services = normalized_scope in {"DOOR_AIRPORT", "DOOR_DOOR"}
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
                sell_currency=invoice_currency,
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
            sell_currency=invoice_currency,
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


    # 3) Determine the correct SELL audience and direction using business rules
    sell_direction = payload.shipment_type

    if pricing_context:
        # Use business rules to determine audience
        # Map business rule currency to appropriate audience
        if pricing_context.currency == "PGK":
            if payload.payment_term == "PREPAID":
                target_audience = "PNG_CUSTOMER_PREPAID"
            else:  # COLLECT
                target_audience = "PNG_CUSTOMER_COLLECT"
        else:
            # For non-PGK currencies (AUD, USD), use overseas agent audience
            target_audience = "OVERSEAS_AGENT_COLLECT" if payload.payment_term == "COLLECT" else "OVERSEAS_AGENT_PREPAID"
        
        logging.debug(f"Business rules determined audience: {target_audience} for currency {pricing_context.currency}")
    else:
        # Fallback to legacy logic if business rules not available
        if payload.payment_term == "PREPAID":
            target_audience = "PNG_CUSTOMER_PREPAID"
        elif payload.payment_term == "COLLECT":
            target_audience = "OVERSEAS_AGENT_COLLECT"
        else:
            target_audience = audience
        logging.warning("Using legacy audience determination logic")

    # Query for the SELL rate card using the specific target audience

    sell_qs_base = Ratecard.objects.filter(
        role="SELL",
        scope=scope_for_sell,
        direction=sell_direction,
        effective_date__lte=ts.date(),
    ).filter(
        Q(audience__code=target_audience),
        Q(expiry_date__isnull=True) | Q(expiry_date__gte=ts.date()),
    )


    sell_card = sell_qs_base.filter(currency=invoice_currency).first()
    if not sell_card:
        sell_card = sell_qs_base.first()
    if not sell_card:
        raise ValueError(
            f"No SELL ratecard found for audience '{target_audience}' and payment term '{payload.payment_term}'."
        )

    supplementary_sell_cards: List[Ratecard] = []
    if needs_origin_services:
        origin_country_code = (origin_station.country or "").upper()
        if origin_country_code:
            origin_audience_code = f"{origin_country_code}_AGENT_PREPAID"
            origin_card_qs = Ratecard.objects.filter(
                role="SELL",
                scope=scope_for_sell,
                direction=sell_direction,
                audience__code=origin_audience_code,
                effective_date__lte=ts.date(),
            ).filter(Q(expiry_date__isnull=True) | Q(expiry_date__gte=ts.date()))
            origin_card = origin_card_qs.first()
            if origin_card and origin_card.id != sell_card.id:
                supplementary_sell_cards.append(origin_card)

    # Build consolidated BUY context keyed by code using native currencies for downstream SELL mapping
    buy_context: Dict[str, Money] = {}
    for code, monies in buy_context_lists.items():
        if not monies:
            continue
        base_currency = monies[0].currency
        total_native = ZERO
        for money in monies:
            current = money
            if base_currency is None:
                base_currency = money.currency
            if base_currency and money.currency != base_currency:
                current = fx.convert(money, base_currency)
            total_native += current.amount
        if base_currency is None:
            base_currency = sell_card.currency
        buy_context[code] = Money(total_native.quantize(TWOPLACES), base_currency)

    # For SELL KG-basis, use a representative chargeable weight
    if per_leg_chargeables:
        chargeable_kg = max(per_leg_chargeables)
    else:
        # In manual or non-freight scenarios where no per-leg FREIGHT was produced,
        # fall back to computing chargeable weight from the request pieces.
        chargeable_kg = calculate_chargeable_weight_per_piece(payload.pieces, Decimal(167))

    # Apply business rules filtering to service scope
    effective_service_scope = payload.service_scope
    if pricing_context and pricing_context.applicable_services:
        logging.debug(f"Business rules limit services to: {pricing_context.applicable_services}")
        # The service filtering will be applied within compute_sell_lines using the pricing_context

    sell_lines = compute_sell_lines(
        sell_card,
        buy_context,
        chargeable_kg,
        effective_service_scope,
        payload.incoterm,
        fx,
        sell_card.currency,
        payload.shipment_type,
        extra_cards=supplementary_sell_cards,
        origin_station=origin_station,
        dest_station=dest_station,
        pricing_context=pricing_context,  # Pass business rules context
    )

    margin_multiplier = d(sell_card.meta.get("origin_margin_multiplier", "1.15"))
    sell_lines = apply_margin_to_origin_lines(sell_lines, margin_multiplier)

    # 4) Totals & taxes (sell lines)
    # Track FX usage to document CAF-on-FX behavior
    fx_pairs_used = set()

    def convert_track(m: Money) -> Money:
        if m.currency != invoice_currency:
            fx_pairs_used.add(f"{m.currency}->{invoice_currency}")
        return fx.convert(m, invoice_currency)

    # Convert BUY to sell currency for total
    total_buy_amount = ZERO
    for bl in buy_lines:
        total_buy_amount += convert_track(bl.extended).amount
    total_buy = Money(total_buy_amount.quantize(TWOPLACES), invoice_currency)

    tax_total = ZERO
    sell_sum = ZERO
    for line in sell_lines:
        sell_amt_money = convert_track(line.extended)
        sell_amt = sell_amt_money.amount
        tax = (sell_amt * (line.tax_pct / Decimal(100))).quantize(TWOPLACES)
        sell_sum += sell_amt + tax
        tax_total += tax
        meta = line.meta if isinstance(line.meta, dict) else {}
        if not isinstance(meta, dict):
            meta = {}
        meta.setdefault("row_type", "line")
        if meta.get("segment") == "primary":
            gst_rate = (line.tax_pct or ZERO) / Decimal(100)
            meta["gst_amount"] = str(tax)
            line.extended = Money((sell_amt + tax).quantize(TWOPLACES), invoice_currency)
            unit_base = d(line.unit_price.amount)
            line.unit_price = Money((unit_base * (Decimal(1) + gst_rate)).quantize(FOURPLACES), line.unit_price.currency)
        else:
            line.extended = Money(sell_amt.quantize(TWOPLACES), invoice_currency)
        line.meta = meta

    # Apply margin before final rounding
    sell_sum_before_rounding = sell_sum.quantize(TWOPLACES)

    # Final rounding rule: round up total SELL to next whole
    final_sell_total = round_up_to_next_whole(sell_sum_before_rounding)

    totals = {
        "buy_total": Money(total_buy.amount, invoice_currency),
        "sell_total": Money(final_sell_total, invoice_currency),
        "tax_total": Money(Decimal(tax_total).quantize(TWOPLACES), invoice_currency),
        "margin_abs": Money((final_sell_total - total_buy.amount).quantize(TWOPLACES), invoice_currency),
        "margin_pct": Money(((final_sell_total - total_buy.amount) / (final_sell_total or Decimal(1))).quantize(FOURPLACES), "%"),
    }

    # 5) Snapshot
    snapshot = {
        "ts": ts.isoformat(),
        "shipment_type": payload.shipment_type,
        "service_scope": payload.service_scope,
        "payment_term": payload.payment_term,
        "incoterm": payload.incoterm,
        # Add business rules context
        "business_rules": {
            "applied": pricing_context is not None,
            "rule_path": pricing_context.rule_path if pricing_context else None,
            "currency_source": "business_rules" if pricing_context else "legacy",
            "currency": pricing_context.currency if pricing_context else None,
            "determined_currency": pricing_context.currency if pricing_context else invoice_currency,
            "charge_scope": pricing_context.charge_scope if pricing_context else [],
            "applicable_services": pricing_context.applicable_services if pricing_context else [],
            "applicable_services_count": len(pricing_context.applicable_services) if pricing_context else 0,
            "requires_manual_review": pricing_context.requires_manual_review if pricing_context else False,
            "description": pricing_context.description if pricing_context else "",
            "metadata": pricing_context.metadata if pricing_context else {},
        },
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
        "fx_caf_buy_pct": float(fx.caf_buy_pct),
        "fx_caf_sell_pct": float(fx.caf_sell_pct),
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
        "sell_currency": invoice_currency,
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
