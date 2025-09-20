from typing import Dict, Tuple, List, Any
from .dataclasses_v2 import BuyResult, SellResult, SellLine, NormalizedContext

AUDIENCE: Dict[Tuple[str, str], str] = {
    ("IMPORT", "PREPAID"): "PNG_CUSTOMER_PREPAID",
    ("IMPORT", "COLLECT"): "OVERSEAS_AGENT_COLLECT",
    ("EXPORT", "PREPAID"): "PNG_CUSTOMER_PREPAID",
    ("EXPORT", "COLLECT"): "OVERSEAS_AGENT_COLLECT",
    ("DOMESTIC", "PREPAID"): "PNG_CUSTOMER_PREPAID",
}
INVOICE_CCY: Dict[Tuple[str, str], str] = {
    ("IMPORT", "PREPAID"): "ORIGIN_CCY",
    ("IMPORT", "COLLECT"): "PGK",
    ("EXPORT", "PREPAID"): "PGK",
    ("EXPORT", "COLLECT"): "DEST_CCY",
    ("DOMESTIC", "PREPAID"): "PGK",
}
SCOPE_SEGMENTS = {
    "A2A": ["PRIMARY"],
    "A2D": ["PRIMARY", "DEST"],
    "D2A": ["ORIGIN", "PRIMARY"],
    "D2D": ["ORIGIN", "PRIMARY", "DEST"],
}

# Minimal sell recipe registry keyed by (scope, audience)
SELL_RECIPES: Dict[Tuple[str, str], Dict[str, Any]] = {
    ("A2D", "PNG_CUSTOMER_PREPAID"): {
        "items": [
            # PRIMARY (intl air)
            {"segment":"PRIMARY","sell_code":"FREIGHT","mode":"pass_through","basis":"PER_KG","source":"FREIGHT"},
            {"segment":"PRIMARY","sell_code":"SECURITY","mode":"pass_through","basis":"PER_SHIPMENT","source":"SECURITY"},
            # DEST services with margin
            {"segment":"DEST","sell_code":"TERMINAL","mode":"cost_plus_pct","value":10,"basis":"PER_SHIPMENT","source":"TERMINAL"},
            {"segment":"DEST","sell_code":"DELIVERY","mode":"cost_plus_pct","value":15,"basis":"PER_KG","source":"DELIVERY"},
        ],
        "gst_segment": "DEST",
    }
}

def apply_sell_recipe(norm: NormalizedContext, buy: BuyResult) -> SellResult:
    key = (norm.snapshot.get("scope"), norm.audience)
    recipe = SELL_RECIPES.get(key)
    if not recipe:
        return SellResult([], True, [f"No sell recipe for {key}"])

    buy_map: Dict[Tuple[str, str], float] = {}
    for c in buy.components:
        buy_map[(c.code, c.segment)] = buy_map.get((c.code, c.segment), 0.0) + c.native_amount

    lines: List[SellLine] = []
    for item in recipe["items"]:
        seg = item["segment"]; mode = item["mode"]; basis = item["basis"]
        src = item.get("source"); val = float(item.get("value", 0))
        qty = norm.chargeable_kg if basis == "PER_KG" else 1.0

        if mode == "pass_through":
            if (src, seg) not in buy_map:
                return SellResult([], True, [f"Missing source {src} on {seg}"])
            amount = buy_map[(src, seg)]
        elif mode == "cost_plus_pct":
            if (src, seg) not in buy_map:
                return SellResult([], True, [f"Missing source {src} on {seg}"])
            amount = buy_map[(src, seg)] * (1.0 + val/100.0)
        elif mode == "cost_plus_abs":
            if (src, seg) not in buy_map:
                return SellResult([], True, [f"Missing source {src} on {seg}"])
            amount = buy_map[(src, seg)] + val
        elif mode == "fixed":
            amount = val * qty
        else:
            return SellResult([], True, [f"Unknown mode {mode}"])

        lines.append(SellLine(item["sell_code"], seg, basis, qty, amount, ccy="PGK"))  # ccy set later
    return SellResult(lines, False, [])
