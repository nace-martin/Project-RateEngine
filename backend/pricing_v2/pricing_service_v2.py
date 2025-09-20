import math
from typing import List, Dict, Any
from django.db.models import Q
from .dataclasses_v2 import *
from .recipes import AUDIENCE, INVOICE_CCY, SCOPE_SEGMENTS, apply_sell_recipe
from pricing.fx_service import FxConverter  # reuse your existing service
from pricing import models as M            # reuse existing models

def ceil_kg(x: float) -> float:
    return float(math.ceil(max(0.0, x)))

def volumetric_kg(p: Piece) -> float:
    if p.length_cm and p.width_cm and p.height_cm:
        m3 = (p.length_cm/100.0) * (p.width_cm/100.0) * (p.height_cm/100.0)
        return m3 * 167.0
    return 0.0

def compute_chargeable_kg(pieces: List[Piece]) -> float:
    total = 0.0
    for p in pieces:
        total += max(p.weight_kg, volumetric_kg(p))
    return ceil_kg(total)

def infer_direction(origin_country: str, dest_country: str, pg_country="PG") -> str:
    if origin_country == dest_country:
        return "DOMESTIC"
    if dest_country == pg_country:
        return "IMPORT"
    if origin_country == pg_country:
        return "EXPORT"
    # fallback: treat as IMPORT via PNG (business-specific)
    return "IMPORT"

def build_legs(origin_iata: str, dest_iata: str) -> List[Dict[str, Any]]:
    # Simple: direct leg; extend later for POM bridge
    return [{"origin": origin_iata, "dest": dest_iata, "type": "PRIMARY"}]

def normalize(ctx: QuoteContext) -> NormalizedContext:
    # You’ll map IATA→country via your stations table; stubbed here:
    def country(iata: str) -> str:
        # TODO: look up from DB
        return "PG" if iata.upper() in ("POM","LAE") else "AU" if iata.upper() in ("BNE","SYD","MEL") else "US"

    direction = infer_direction(country(ctx.origin_iata), country(ctx.dest_iata))
    audience = AUDIENCE[(direction, ctx.payment_term)]
    invoice = INVOICE_CCY[(direction, ctx.payment_term)]
    segments = SCOPE_SEGMENTS[ctx.scope]
    legs = build_legs(ctx.origin_iata, ctx.dest_iata)
    chg = compute_chargeable_kg(ctx.pieces)

    snap = {"scope": ctx.scope, "direction": direction, "audience": audience, "invoice_ccy": invoice}
    # manual conditions upfront
    manual, reasons = False, []
    if ctx.commodity != "GCR":
        manual, reasons = True, ["Non-GCR commodity requires manual rating"]

    nc = NormalizedContext(direction, audience, invoice, segments, legs, chg, "DEST", snap)
    if manual:
        nc.snapshot["manual_reasons"] = reasons
    return nc

def pick_best_break(lbqs) -> Dict[str, Any]:
    # lbqs: QuerySet of LaneBreaks; choose cheapest per-kg for chargeable weight
    # Simplified: return a dict with chosen per_kg & min
    best = None
    for lb in lbqs:
        if best is None or lb.per_kg < best.per_kg:
            best = lb
    return {"per_kg": best.per_kg, "min_amount": getattr(best, "min_amount", 0)}

def rate_buy(norm: NormalizedContext) -> BuyResult:
    if "manual_reasons" in norm.snapshot:
        return BuyResult([], True, norm.snapshot["manual_reasons"])

    comps: List[BuyComponent] = []
    reasons: List[str] = []

    for leg in norm.legs:
        # Find active BUY lanes (simplified; filter with Q on origin/dest, active date, commodity)
        lanes = (M.Lanes.objects
                 .filter(ratecard__type="BUY",
                         origin_iata=leg["origin"],
                         dest_iata=leg["dest"])
                 .select_related("ratecard"))

        if not lanes.exists():
            return BuyResult([], True, [f"No BUY lane for {leg['origin']}→{leg['dest']}"])

        # Choose cheapest break for chargeable_kg
        best_per_kg = None; best_min = None; lane_currency = None
        for lane in lanes:
            breaks = M.LaneBreaks.objects.filter(lane=lane)
            chosen = pick_best_break(breaks)
            lane_ccy = lane.ratecard.currency
            # normalize to a compare-ccy later if you want; keep simple for MVP
            if best_per_kg is None or chosen["per_kg"] < best_per_kg:
                best_per_kg = chosen["per_kg"]; best_min = chosen["min_amount"]; lane_currency = lane_ccy

        freight = max(norm.chargeable_kg * best_per_kg, best_min)
        comps.append(BuyComponent(code="FREIGHT", segment="PRIMARY", basis="PER_KG",
                                  unit_qty=norm.chargeable_kg, native_amount=freight, native_ccy=lane_currency))

        # TODO BUY fees: iterate RatecardFees for the chosen lane/ratecard and append components

    return BuyResult(comps, False, reasons)

def map_to_sell(norm: NormalizedContext, buy: BuyResult) -> SellResult:
    return apply_sell_recipe(norm, buy)

def tax_fx_round(norm: NormalizedContext, sell: SellResult) -> Totals:
    # Instantiate FxConverter from your PricingPolicy (CAF buy/sell)
    # For MVP, assume PGK already; extend to do proper FX direction later
    total = sum(l.amount for l in sell.lines)
    tax = 0.0  # apply GST on norm.gst_segment as needed
    final = math.ceil(total)  # single rounding policy
    return Totals(buy_pgk=0.0, tax=tax, final_sell=final, client_ccy=norm.invoice_ccy)

def compute_quote_v2(ctx: QuoteContext):
    norm = normalize(ctx)
    if "manual_reasons" in norm.snapshot:
        return {"manual": True, "reasons": norm.snapshot["manual_reasons"], "snapshot": norm.snapshot}

    buy = rate_buy(norm)
    if buy.manual:
        return {"manual": True, "reasons": buy.reasons, "snapshot": norm.snapshot}

    sell = map_to_sell(norm, buy)
    if sell.manual:
        return {"manual": True, "reasons": sell.reasons, "snapshot": norm.snapshot}

    totals = tax_fx_round(norm, sell)
    return {
        "manual": False,
        "buy_components": [c.__dict__ for c in buy.components],
        "sell_lines": [s.__dict__ for s in sell.lines],
        "totals": totals.__dict__,
        "snapshot": {**norm.snapshot, "policy_key":"CODE_DEFAULT","policy_version":1},
    }
