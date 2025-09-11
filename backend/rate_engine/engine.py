"""
RateEngine MVP – Compute Service (Django/DRF skeleton)

This module implements the minimal pricing engine we designed. It relies on the
SQL schema shipped in `mvp_migration.sql`. You can drop this file into your Django
project (e.g., app `pricing/engine.py`) and wire the DRF view to `/api/quote/compute`.

Scope (MVP):
- BUY pricing for International/Domestic lanes (PX, Maersk, EFM-BNE, Ad-hoc agents)
- Origin/tranship fees (min/per-kg/% with caps, simple conditions)
- SELL menus (PGK Import & Export), with SELL↔BUY link types:
  PASS_THROUGH | FIXED_OVERRIDE | COST_PLUS_PCT | COST_PLUS_ABS
- Currency conversion with CAF-on-FX
- Quote breakdown with per-line buy/sell and snapshot metadata

Assumptions:
- Django models map 1:1 to DDL in `mvp_migration.sql`. Only the fields used
  below are referenced at runtime.
- You already seed `fee_types` and `services` from the migration.

Author: Nas + GPT-5 Thinking (MVP build)
"""
from __future__ import annotations
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP, ROUND_CEILING
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timezone
import logging

from django.db import transaction
from django.db.models import Q, F
from django.shortcuts import get_object_or_404
import re
from django.utils.timezone import now

# ---- Import your ORM models (names match the migration) ----
from .models import (
    Providers as Provider, Stations as Station,
    Ratecards as Ratecard, RatecardConfig, Lanes as Lane, LaneBreaks as LaneBreak,
    FeeTypes as FeeType, RatecardFees as RatecardFee, CartageLadders as CartageLadder,
    Services as Service, ServiceItems as ServiceItem, SellCostLinksSimple as SellCostLink,
    CurrencyRates as CurrencyRate, PricingPolicy, Organizations, Quotes, QuoteLines,
    Routes, RouteLegs,
)

# --------------------------- Datatypes ---------------------------

TWOPLACES = Decimal("0.01")
FOURPLACES = Decimal("0.0001")
ZERO = Decimal("0")


def d(val) -> Decimal:
    """Coerce to Decimal safely."""
    if isinstance(val, Decimal):
        return val
    return Decimal(str(val))


def round_up_nearest_0_05(amount: Decimal) -> Decimal:
    """Round up to the nearest 0.05 (e.g., 12.01 -> 12.05, 12.05 -> 12.05)."""
    step = Decimal("0.05")
    # Use ceiling on the step multiple to ensure we round up
    multiples = (d(amount) / step).to_integral_value(rounding=ROUND_CEILING)
    return (multiples * step).quantize(TWOPLACES)


def round_up_to_next_whole(amount: Decimal) -> Decimal:
    """Rounds a decimal amount up to the next whole number (e.g., 315.79 -> 316.00)."""
    return amount.to_integral_value(rounding=ROUND_CEILING)


@dataclass
class Piece:
    weight_kg: Decimal
    length_cm: Optional[Decimal] = None
    width_cm: Optional[Decimal] = None
    height_cm: Optional[Decimal] = None

    def volume_m3(self) -> Decimal:
        if self.length_cm is None or self.width_cm is None or self.height_cm is None:
            return ZERO
        return (self.length_cm * self.width_cm * self.height_cm) / Decimal(1_000_000)


@dataclass
class ShipmentInput:
    org_id: int  # Payer/Client organization id
    origin_iata: str
    dest_iata: str
    shipment_type: str
    service_scope: str
    # New optional inputs
    commodity_code: str = "GCR"  # e.g., GCR, DGR, LAR, PER
    is_urgent: bool = False
    airline_hint: Optional[str] = None
    via_hint: Optional[str] = None
    pieces: List[Piece] = field(default_factory=list)
    # flags/conditions used by fees & SELL services
    flags: Dict[str, bool] = field(default_factory=dict)  # e.g., {"secondary_screening": True}
    duties_value_sell_ccy: Decimal = ZERO  # used by disbursement % SELL service
    pallets: int = 0

    @property
    def actual_weight(self) -> Decimal:
        return sum((p.weight_kg for p in self.pieces), ZERO)

    @property
    def volume_m3(self) -> Decimal:
        return sum((p.volume_m3() for p in self.pieces), ZERO)


@dataclass
class Money:
    amount: Decimal
    currency: str


@dataclass
class CalcLine:
    code: str
    description: str
    qty: Decimal
    unit: str
    unit_price: Money
    extended: Money
    is_buy: bool
    is_sell: bool
    tax_pct: Decimal = ZERO
    source_ratecard_id: Optional[int] = None
    meta: Dict = field(default_factory=dict)


@dataclass
class CalcResult:
    buy_lines: List[CalcLine]
    sell_lines: List[CalcLine]
    totals: Dict[str, Money]
    snapshot: Dict


# ------------------------ FX & helpers ---------------------------

class FxConverter:
    def __init__(self, caf_on_fx: bool = True, caf_pct: Decimal = Decimal("0.00")):
        self.caf_on_fx = caf_on_fx
        self.caf_pct = caf_pct

    def rate(self, base_ccy: str, quote_ccy: str, at: Optional[datetime] = None) -> Decimal:
        """
        Fetch latest FX rate base->quote with direction-aware logic for TT Buy/Sell rates and CAF.
        """
        at = at or now()

        # Direction-aware logic for PNG Kina contexts
        if quote_ccy == 'PGK':
            # Converting FCY -> PGK uses bank BUY rate
            rate_type_to_fetch = 'BUY'
            is_to_pgk = True
        else:
            # Converting PGK -> FCY uses bank SELL rate
            rate_type_to_fetch = 'SELL'
            is_to_pgk = False

        row = (
            CurrencyRate.objects
            .filter(
                base_ccy=base_ccy,
                quote_ccy=quote_ccy,
                as_of_ts__lte=at,
                rate_type=rate_type_to_fetch,
            )
            .order_by("-as_of_ts")
            .first()
        )
        if not row:
            raise ValueError(f"No FX rate {base_ccy}->{quote_ccy} (Type: {rate_type_to_fetch}) available")

        r = d(row.rate)

        # Apply CAF directionally if enabled
        if self.caf_on_fx:
            if is_to_pgk:
                # FCY -> PGK: subtract CAF for conservative rate
                return r * (Decimal("1.0") - self.caf_pct)
            else:
                # PGK -> FCY: add CAF
                return r * (Decimal("1.0") + self.caf_pct)
        else:
            return r

    def convert(self, money: Money, to_ccy: str) -> Money:
        if money.currency == to_ccy:
            return money
        fx = self.rate(money.currency, to_ccy)
        return Money((money.amount * fx).quantize(TWOPLACES), to_ccy)


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
    return total_chargeable.to_integral_value(rounding=ROUND_CEILING)


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
        if best_cost is None or min_charge < best_cost:
            best_cost = min_charge
            best_break = min_row

    if best_break is None:
        raise ValueError("No lane breaks available for pricing")

    return best_break, Money(best_cost, ccy)


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

    # SELL-Side: CARTAGE and CARTAGE_FSC apply only to these scopes
    allowed_cartage_scopes = {"DOOR_DOOR", "DOOR_AIRPORT", "AIRPORT_DOOR"}

    for it in items:
        svc = it.service
        code = svc.code
        desc = svc.name
        ccy = it.currency
        tax_pct = d(it.tax_pct)
        basis = _normalize_basis(getattr(svc, "basis", None))
        qty = d(kg) if basis == "PER_KG" else Decimal(1)

        # Enforce service scope for CARTAGE and CARTAGE_FSC (exclude from AIRPORT_AIRPORT)
        if code in {"CARTAGE", "CARTAGE_FSC"} and service_scope not in allowed_cartage_scopes:
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

    # 1) BUY pricing: support multi-leg via Routes/RouteLegs when available
    # Define sell scope for SELL card lookup regardless of routing mode
    scope_for_sell = "INTERNATIONAL" if payload.shipment_type in ["IMPORT", "EXPORT"] else "DOMESTIC"
    buy_direction = None  # for snapshot in single-leg mode
    # Determine route based on origin/dest station countries and shipment type
    route = None
    try:
        st_o = Station.objects.get(iata=payload.origin_iata)
        st_d = Station.objects.get(iata=payload.dest_iata)
        route = Routes.objects.filter(
            origin_country=(st_o.country or "").upper(),
            dest_country=(st_d.country or "").upper(),
            shipment_type=payload.shipment_type,
        ).first()
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
        legs = list(RouteLegs.objects.filter(route_id=route.id).select_related("origin", "dest").order_by("sequence"))
        if not legs:
            raise ValueError("Configured route has no legs defined")

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

    # 3) SELL destination services (PGK/AUD/USD) based on audience & direction
    sell_direction = payload.shipment_type  # SELL follows request direction
    # Prefer SELL card in the requested sell currency; fall back to any currency
    sell_qs_base = Ratecard.objects.filter(
        role="SELL",
        scope=scope_for_sell,
        direction=sell_direction,
        audience=audience,
        effective_date__lte=ts.date(),
    ).filter(Q(expiry_date__isnull=True) | Q(expiry_date__gte=ts.date()))
    sell_card = sell_qs_base.filter(currency=sell_currency).first()
    if not sell_card:
        sell_card = sell_qs_base.first()
    if not sell_card:
        raise ValueError("No SELL ratecard found for audience.")

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


# --------------------------- DRF View ----------------------------

# Example DRF serializer & view; adjust import path to your project.

from rest_framework import serializers, views, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
import os
from .fx import EnvProvider, compute_tt_buy_sell, upsert_rate
from .fx_providers import load as load_fx_provider


class PieceSerializer(serializers.Serializer):
    weight_kg = serializers.DecimalField(max_digits=12, decimal_places=3)
    length_cm = serializers.DecimalField(max_digits=12, decimal_places=1, required=False)
    width_cm = serializers.DecimalField(max_digits=12, decimal_places=1, required=False)
    height_cm = serializers.DecimalField(max_digits=12, decimal_places=1, required=False)


class ComputeRequestSerializer(serializers.Serializer):
    origin_iata = serializers.CharField()
    dest_iata = serializers.CharField()
    shipment_type = serializers.ChoiceField(choices=("IMPORT", "EXPORT", "DOMESTIC"))
    service_scope = serializers.ChoiceField(
        choices=("DOOR_DOOR", "DOOR_AIRPORT", "AIRPORT_DOOR", "AIRPORT_AIRPORT")
    )
    org_id = serializers.IntegerField()
    # New optional inputs
    commodity_code = serializers.CharField(required=False, max_length=8, default='GCR')
    is_urgent = serializers.BooleanField(required=False, default=False)
    airline_hint = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    via_hint = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    pieces = PieceSerializer(many=True)
    flags = serializers.JSONField(required=False)
    duties_value_sell_ccy = serializers.DecimalField(max_digits=14, decimal_places=2, required=False)
    pallets = serializers.IntegerField(required=False)
    provider_hint = serializers.IntegerField(required=False)
    caf_pct = serializers.DecimalField(max_digits=6, decimal_places=4, required=False)

    def validate_org_id(self, value: int):
        """Ensure the payer organization exists before processing."""
        if not Organizations.objects.filter(id=value).exists():
            raise serializers.ValidationError("Invalid Payer/Organization ID.")
        return value

    def validate_commodity_code(self, value: str) -> str:
        """Normalize and validate commodity code against allowed set."""
        if value is None:
            return 'GCR'
        v = (value or '').strip().upper()
        allowed = {"GCR", "DGR", "LAR", "PER"}
        if not v:
            return 'GCR'
        if len(v) > 8:
            raise serializers.ValidationError("commodity_code must be at most 8 characters.")
        if v not in allowed:
            raise serializers.ValidationError(f"Invalid commodity_code. Allowed: {', '.join(sorted(allowed))}.")
        return v


class QuoteComputeView(views.APIView):
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

        shipment = ShipmentInput(
            org_id=int(data["org_id"]),
            origin_iata=data["origin_iata"],
            dest_iata=data["dest_iata"],
            shipment_type=data["shipment_type"],
            service_scope=data["service_scope"],
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
            status_str = 'PENDING_RATE' if is_manual else 'COMPLETE'
            totals = calc_result.totals

            # 2. Create the main Quote record
            new_quote = Quotes.objects.create(
                organization_id=shipment.org_id,
                status=status_str,
                request_snapshot=data,  # Save the original request
                buy_total=totals.get('buy_total', Money(ZERO, 'USD')).amount,
                sell_total=totals.get('sell_total', Money(ZERO, 'USD')).amount,
                currency=totals.get('sell_total', Money(ZERO, 'USD')).currency,
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

            # 4. Return the ID of the new quote
            response_data = {
                "quote_id": new_quote.id,
                "status": status_str,
                "sell_total": {
                    "amount": str(new_quote.sell_total),
                    "currency": new_quote.currency,
                },
                "manual_reasons": calc_result.snapshot.get("manual_reasons", []),
            }
            return Response(response_data, status=status.HTTP_201_CREATED)

        except ValueError as e:
            # If the engine fails (e.g., no route found), return an error
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


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

        lines = list(q.lines.all())
        body = {
            "quote_id": q.id,
            "status": q.status,
            "currency": q.currency,
            "totals": {
                "buy_total": {"amount": str(q.buy_total), "currency": q.currency},
                "sell_total": {"amount": str(q.sell_total), "currency": q.currency},
            },
            "snapshot": q.request_snapshot,
            "created_at": q.created_at.isoformat(),
            "updated_at": q.updated_at.isoformat(),
            "buy_lines": [serialize_line(l) for l in lines if l.is_buy],
            "sell_lines": [serialize_line(l) for l in lines if l.is_sell],
        }
        return Response(body, status=status.HTTP_200_OK)


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

        # Build array payload matching frontend Quote type
        items = []
        for q in qs[:200]:  # simple cap
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
                "actual_weight_kg": str(actual.quantize(FOURPLACES)),
                "volume_cbm": str(volume.quantize(FOURPLACES)),
                "chargeable_weight_kg": str(chargeable.quantize(FOURPLACES)),
                "rate_used_per_kg": "",
                "base_cost": str(Decimal(q.buy_total).quantize(TWOPLACES)),
                "margin_pct": str(((d(q.sell_total) - d(q.buy_total)) / (d(q.sell_total) or Decimal(1)) * Decimal(100)).quantize(FOURPLACES)),
                "total_sell": str(Decimal(q.sell_total).quantize(TWOPLACES)),
                "created_at": q.created_at.isoformat(),
            })

        return Response(items, status=status.HTTP_200_OK)


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


# -------------------------- Validation --------------------------

def validate_break_monotonic(lane_id: int) -> List[str]:
    """Return a list of warnings if breaks are not monotonic decreasing per-kg."""
    warnings: List[str] = []
    order = ["N","45","100","250","500","1000"]
    rows = {b.break_code: d(b.per_kg or ZERO) for b in LaneBreak.objects.filter(lane_id=lane_id)}
    last = None
    for k in order:
        if k not in rows:
            continue
        if last is not None and rows[k] > last:
            warnings.append(f"Per-kg for {k} ({rows[k]}) exceeds previous break ({last}) – check data.")
        last = rows[k]
    return warnings

def outlier_guard(per_kg: Decimal) -> Optional[str]:
    if per_kg > Decimal(50):
        return f"Per-kg looks unusually high ({per_kg}). Did you mean {per_kg/Decimal(10)}?"
    return None
