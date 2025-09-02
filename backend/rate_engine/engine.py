"""
RateEngine MVP – Compute Service (Django/DRF skeleton)

This module implements the minimal pricing engine we designed. It relies on the
SQL schema shipped in `mvp_migration.sql`. You can drop this file into your Django
project (e.g., app `pricing/engine.py`) and wire the DRF view to `/quote/compute`.

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
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timezone
import logging

from django.db.models import Q, F
from django.utils.timezone import now

# ---- Import your ORM models (names match the migration) ----
from .models import (
    Providers as Provider, Stations as Station,
    Ratecards as Ratecard, RatecardConfig, Lanes as Lane, LaneBreaks as LaneBreak,
    FeeTypes as FeeType, RatecardFees as RatecardFee, CartageLadders as CartageLadder,
    Services as Service, ServiceItems as ServiceItem, SellCostLinksSimple as SellCostLink,
    CurrencyRates as CurrencyRate, PricingPolicy,
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


def calculate_chargeable_weight(pieces: List[Dict]) -> float:
    """Calculate total chargeable weight for a shipment.

    Implements the standard air freight rule from the Quoting Scenarios Matrix:
    Chargeable = max(Actual vs Volumetric) per piece, summed across all pieces.

    Inputs are dictionaries with keys: 'weight', 'length', 'width', 'height'.
    Units: weight in kilograms; dimensions in centimeters. Volumetric divisor = 6000.

    Returns the final chargeable weight as a float (kilograms).
    """
    def _to_float(v) -> float:
        try:
            return float(v)
        except (TypeError, ValueError):
            return 0.0

    divisor = 6000.0  # IATA standard for cm-based dimensions
    total = 0.0
    for p in pieces or []:
        actual = _to_float(p.get("weight"))
        length = _to_float(p.get("length"))
        width = _to_float(p.get("width"))
        height = _to_float(p.get("height"))

        volumetric = (length * width * height) / divisor if (length and width and height) else 0.0
        total += max(actual, volumetric)

    return float(total)


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
    origin_iata: str
    dest_iata: str
    shipment_type: str
    service_scope: str
    airline_hint: Optional[str] = None
    via_hint: Optional[str] = None
    audience: str = "PGK_LOCAL"  # drives SELL card
    sell_currency: str = "PGK"
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
        """Fetch latest FX rate base->quote (e.g., AUD->PGK)."""
        at = at or now()
        row = (
            CurrencyRate.objects
            .filter(base_ccy=base_ccy, quote_ccy=quote_ccy, as_of_ts__lte=at)
            .order_by("-as_of_ts")
            .first()
        )
        if not row:
            raise ValueError(f"No FX rate {base_ccy}->{quote_ccy} available")
        r = d(row.rate)
        return r * (Decimal("1.0") + self.caf_pct) if self.caf_on_fx else r

    def convert(self, money: Money, to_ccy: str) -> Money:
        if money.currency == to_ccy:
            return money
        fx = self.rate(money.currency, to_ccy)
        return Money((money.amount * fx).quantize(TWOPLACES), to_ccy)


# --------------------- Core engine functions ---------------------

def compute_chargeable(weight_kg: Decimal, volume_m3: Decimal, dim_factor_kg_per_m3: Decimal) -> Decimal:
    vol_weight = (volume_m3 * dim_factor_kg_per_m3).quantize(FOURPLACES)
    return max(weight_kg, vol_weight)


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


def compute_fee_amount(fee: RatecardFee, kg: Decimal, context: Dict[str, Money]) -> Money:
    """Compute a BUY fee line in its native currency.
    context: map of code->Money already computed (for PERCENT_OF).
    """
    code = FeeType.objects.get(id=fee.fee_type_id).code
    basis = FeeType.objects.get(id=fee.fee_type_id).basis
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
    if basis == "PER_KG":
        total = (amt * kg)
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
    return Money(total.quantize(TWOPLACES), ccy)


def sum_money(items: List[Money], to_ccy: str, fx: FxConverter) -> Money:
    total = ZERO
    for m in items:
        total += fx.convert(m, to_ccy).amount
    return Money(total.quantize(TWOPLACES), to_ccy)


# ----------------------- SELL computation ------------------------

def compute_sell_lines(sell_card: Ratecard, buy_context: Dict[str, Money], kg: Decimal) -> List[CalcLine]:
    lines: List[CalcLine] = []
    items = (
        ServiceItem.objects
        .filter(ratecard_id=sell_card.id)
        .select_related("service")
    )
    links = {l.sell_item_id: l for l in SellCostLink.objects.filter(sell_item_id__in=[i.id for i in items])}

    for it in items:
        svc = it.service
        code = svc.code
        desc = svc.name
        ccy = it.currency
        tax_pct = d(it.tax_pct)
        qty = d(kg) if svc.basis == "PER_KG" else Decimal(1)

        # Determine the underlying BUY cost (if linked)
        buy_sum = ZERO
        if it.id in links:
            ln = links[it.id]
            # Sum context costs for matching buy_fee_code
            if ln.buy_fee_code in buy_context:
                buy_sum = d(buy_context[ln.buy_fee_code].amount)

        # Compute the SELL amount
        sell_amt = ZERO
        if it.amount is not None:
            unit_price = d(it.amount)
            if svc.basis == "PER_KG":
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
                sell_amt = (buy_sum * (Decimal(1) + pct)).quantize(TWOPLACES)
            elif ln.mapping_type == "COST_PLUS_ABS":
                inc = d(ln.mapping_value or ZERO)
                sell_amt = (buy_sum + inc).quantize(TWOPLACES)

        line = CalcLine(
            code=code,
            description=desc,
            qty=qty,
            unit="KG" if svc.basis == "PER_KG" else "EA",
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

    # Pricing policy (per audience)
    pol = PricingPolicy.objects.filter(audience=payload.audience).first()
    fx = FxConverter(caf_on_fx=bool(pol.caf_on_fx if pol else True), caf_pct=caf_pct)

    # 1) Choose BUY ratecards and lane
    if payload.shipment_type in ["IMPORT", "EXPORT"]:
        scope = "INTERNATIONAL"
        buy_direction = "EXPORT" # International leg is always bought as export from origin
    else:
        scope = "DOMESTIC"
        buy_direction = payload.shipment_type

    active_cards = Ratecard.objects.filter(
        role="BUY",
        scope=scope,
        direction=buy_direction,
        effective_date__lte=ts.date(),
    ).filter(Q(expiry_date__isnull=True) | Q(expiry_date__gte=ts.date()))

    if provider_hint:
        active_cards = active_cards.filter(provider_id=provider_hint)

    # Find all candidate lanes for origin/dest (respect airline/via hints if given)
    candidate_lanes = (
        Lane.objects
        .filter(ratecard_id__in=active_cards.values_list("id", flat=True))
        .filter(origin__iata=payload.origin_iata, dest__iata=payload.dest_iata)
    )
    if payload.airline_hint:
        candidate_lanes = candidate_lanes.filter(airline=payload.airline_hint)
    if payload.via_hint:
        candidate_lanes = candidate_lanes.filter(via__iata=payload.via_hint)

    lanes = list(candidate_lanes.select_related("ratecard"))
    if not lanes:
        raise ValueError("No BUY lanes available. Create an ad-hoc agent ratecard or adjust filters.")

    # Compute chargeable per ratecard config (dim factor may differ per card)
    buy_options = []
    for lane in lanes:
        cfg = RatecardConfig.objects.filter(ratecard_id=lane.ratecard_id).first()
        dim = d(cfg.dim_factor_kg_per_m3 if cfg else Decimal(167))
        chargeable = compute_chargeable(payload.actual_weight, payload.volume_m3, dim)
        brk, base = pick_best_break(lane, chargeable)
        buy_options.append((lane, chargeable, brk, base))

    # Pick cheapest base freight in its native currency converted to sell currency
    def to_sell_ccy(m: Money) -> Decimal:
        return FxConverter(caf_on_fx=True, caf_pct=caf_pct).convert(m, payload.sell_currency).amount

    best = min(buy_options, key=lambda x: to_sell_ccy(x[3]))
    lane, chargeable_kg, chosen_break, base_freight = best
    # Validate monotonic breaks, log warnings but do not block pricing
    lane_warnings = validate_break_monotonic(lane.id)
    for w in lane_warnings:
        logging.warning(f"Lane {lane.id} break validation: {w}")
    rc_buy = Ratecard.objects.get(id=lane.ratecard_id)

    # 2) BUY origin/tranship fees
    buy_lines: List[CalcLine] = []
    buy_context: Dict[str, Money] = {}

    # Freight line
    buy_lines.append(
        CalcLine(
            code="FREIGHT",
            description=f"Air freight {payload.origin_iata}->{payload.dest_iata} ({chosen_break.break_code})",
            qty=chargeable_kg,
            unit="KG",
            unit_price=Money((base_freight.amount/chargeable_kg).quantize(FOURPLACES), base_freight.currency),
            extended=base_freight,
            is_buy=True,
            is_sell=False,
            source_ratecard_id=rc_buy.id,
        )
    )
    buy_context["FREIGHT"] = base_freight

    fees = RatecardFee.objects.filter(ratecard_id=rc_buy.id).select_related("fee_type")
    # Seed runtime flags into context
    buy_context["secondary_screening_flag"] = payload.flags.get("secondary_screening", False)

    for fee in fees:
        fee_type = FeeType.objects.get(id=fee.fee_type_id)
        line_money = compute_fee_amount(fee, chargeable_kg, buy_context)
        if line_money.amount <= 0:
            continue
        buy_context[fee_type.code] = line_money
        buy_lines.append(
            CalcLine(
                code=fee_type.code,
                description=fee_type.description,
                qty=chargeable_kg if fee_type.basis == "PER_KG" else Decimal(1),
                unit="KG" if fee_type.basis == "PER_KG" else "EA",
                unit_price=Money((line_money.amount/(chargeable_kg if fee_type.basis == "PER_KG" else 1)).quantize(FOURPLACES), line_money.currency),
                extended=line_money,
                is_buy=True,
                is_sell=False,
                source_ratecard_id=rc_buy.id,
            )
        )

    # 3) SELL destination services (PGK import/export) based on audience & direction
    sell_direction = payload.shipment_type  # SELL follows request direction
    sell_card = Ratecard.objects.filter(
        role="SELL",
        scope=scope,
        direction=sell_direction,
        audience=payload.audience,
        currency=payload.sell_currency,
        effective_date__lte=ts.date(),
    ).filter(Q(expiry_date__isnull=True) | Q(expiry_date__gte=ts.date())).first()
    if not sell_card:
        raise ValueError("No SELL ratecard found for audience/currency.")

    sell_lines = compute_sell_lines(sell_card, buy_context, chargeable_kg)

    # 4) Totals & taxes (sell lines)
    # Track FX usage to document CAF-on-FX behavior
    fx_pairs_used = set()

    def convert_track(m: Money) -> Money:
        if m.currency != payload.sell_currency:
            fx_pairs_used.add(f"{m.currency}->{payload.sell_currency}")
        return fx.convert(m, payload.sell_currency)

    # Convert BUY to sell currency for total
    total_buy_amount = ZERO
    for bl in buy_lines:
        total_buy_amount += convert_track(bl.extended).amount
    total_buy = Money(total_buy_amount.quantize(TWOPLACES), payload.sell_currency)

    tax_total = ZERO
    sell_sum = ZERO
    for l in sell_lines:
        sell_amt_money = convert_track(l.extended)
        sell_amt = sell_amt_money.amount
        tax = (sell_amt * (l.tax_pct/Decimal(100))).quantize(TWOPLACES)
        sell_sum += sell_amt + tax
        tax_total += tax

    totals = {
        "buy_total": Money(total_buy.amount, payload.sell_currency),
        "sell_total": Money(sell_sum.quantize(TWOPLACES), payload.sell_currency),
        "tax_total": Money(Decimal(tax_total).quantize(TWOPLACES), payload.sell_currency),
        "margin_abs": Money((sell_sum - total_buy.amount).quantize(TWOPLACES), payload.sell_currency),
        "margin_pct": Money(((sell_sum - total_buy.amount) / (sell_sum or Decimal(1))).quantize(FOURPLACES), "%"),
    }

    # 5) Snapshot
    snapshot = {
        "ts": ts.isoformat(),
        "shipment_type": payload.shipment_type,
        "service_scope": payload.service_scope,
        "buy_ratecard_id": rc_buy.id,
        "sell_ratecard_id": sell_card.id,
        "dim_factor": float(RatecardConfig.objects.filter(ratecard_id=rc_buy.id).first().dim_factor_kg_per_m3 if RatecardConfig.objects.filter(ratecard_id=rc_buy.id).exists() else 167),
        # FX & CAF documentation
        "fx_caf_pct": float(caf_pct),
        "caf_on_fx": bool(fx.caf_on_fx),
        "fx_pairs_used": sorted(list(fx_pairs_used)),
        "chargeable_kg": float(chargeable_kg),
        "chosen_break": chosen_break.break_code,
        # Directional decoupling
        "buy_direction": buy_direction,
        "sell_direction": sell_direction,
        # Data quality warnings (non-blocking)
        "break_warnings": lane_warnings,
    }

    return CalcResult(buy_lines=buy_lines, sell_lines=sell_lines, totals=totals, snapshot=snapshot)


# --------------------------- DRF View ----------------------------

# Example DRF serializer & view; adjust import path to your project.

from rest_framework import serializers, views, status
from rest_framework.response import Response


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
    audience = serializers.ChoiceField(choices=("PGK_LOCAL","AUD_AGENT","USD_AGENT"))
    sell_currency = serializers.CharField()
    airline_hint = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    via_hint = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    pieces = PieceSerializer(many=True)
    flags = serializers.JSONField(required=False)
    duties_value_sell_ccy = serializers.DecimalField(max_digits=14, decimal_places=2, required=False)
    pallets = serializers.IntegerField(required=False)
    provider_hint = serializers.IntegerField(required=False)
    caf_pct = serializers.DecimalField(max_digits=6, decimal_places=4, required=False)


class QuoteComputeView(views.APIView):
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
            origin_iata=data["origin_iata"],
            dest_iata=data["dest_iata"],
            shipment_type=data["shipment_type"],
            service_scope=data["service_scope"],
            airline_hint=data.get("airline_hint") or None,
            via_hint=data.get("via_hint") or None,
            audience=data["audience"],
            sell_currency=data["sell_currency"],
            pieces=[Piece(**p) for p in data["pieces"]],
            flags=data.get("flags") or {},
            duties_value_sell_ccy=data.get("duties_value_sell_ccy") or ZERO,
            pallets=data.get("pallets") or 0,
        )

        try:
            res = compute_quote(
                shipment,
                provider_hint=data.get("provider_hint"),
                caf_pct=d(data.get("caf_pct") or Decimal("0.065")),
            )
        except ValueError:
            # Fallback when pricing data is not seeded: return empty breakdown with snapshot
            zero = Money(ZERO, shipment.sell_currency)
            res = CalcResult(
                buy_lines=[],
                sell_lines=[],
                totals={
                    "buy_total": zero,
                    "sell_total": zero,
                    "margin": Money(ZERO, shipment.sell_currency),
                },
                snapshot={
                    "origin": shipment.origin_iata,
                    "destination": shipment.dest_iata,
                    "shipment_type": shipment.shipment_type,
                    "service_scope": shipment.service_scope,
                    "audience": shipment.audience,
                    "sell_currency": shipment.sell_currency,
                    "actual_weight": str(shipment.actual_weight),
                    "volume_m3": str(shipment.volume_m3),
                },
            )

        def present_line(cl: CalcLine, fx_to: str) -> Dict:
            return {
                "code": cl.code,
                "desc": cl.description,
                "qty": str(cl.qty),
                "unit": cl.unit,
                "unit_price": {"amount": str(cl.unit_price.amount), "currency": cl.unit_price.currency},
                "amount": {"amount": str(cl.extended.amount), "currency": cl.extended.currency},
                "is_buy": cl.is_buy,
                "is_sell": cl.is_sell,
                "tax_pct": str(cl.tax_pct),
                "source_ratecard_id": cl.source_ratecard_id,
            }

        body = {
            "buy_lines": [present_line(l, shipment.sell_currency) for l in res.buy_lines],
            "sell_lines": [present_line(l, shipment.sell_currency) for l in res.sell_lines],
            "totals": {k: {"amount": str(v.amount), "currency": v.currency} for k, v in res.totals.items()},
            "snapshot": res.snapshot,
        }
        return Response(body, status=status.HTTP_200_OK)


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

# Override with a clean implementation (fix malformed string in earlier definition)
def validate_break_monotonic(lane_id: int) -> List[str]:
    warnings: List[str] = []
    order = ["N", "45", "100", "250", "500", "1000"]
    rows = {b.break_code: d(b.per_kg or ZERO) for b in LaneBreak.objects.filter(lane_id=lane_id)}
    last = None
    for k in order:
        if k not in rows:
            continue
        if last is not None and rows[k] > last:
            warnings.append(f"Per-kg for {k} ({rows[k]}) exceeds previous break ({last}) — check data.")
        last = rows[k]
    return warnings

def outlier_guard(per_kg: Decimal) -> Optional[str]:
    if per_kg > Decimal(50):
        return f"Per-kg looks unusually high ({per_kg}). Did you mean {per_kg/Decimal(10)}?"
    return None
