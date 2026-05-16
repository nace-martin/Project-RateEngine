from __future__ import annotations

from enum import StrEnum
from typing import Any


class PricingRateScope(StrEnum):
    LANE = "LANE"
    ORIGIN = "ORIGIN"
    DESTINATION = "DESTINATION"
    LOCAL = "LOCAL"
    UNKNOWN = "UNKNOWN"


LOCAL_CATEGORIES = {
    "AGENCY",
    "CARTAGE",
    "CLEARANCE",
    "DOCUMENTATION",
    "HANDLING",
    "REGULATORY",
    "SCREENING",
    "SECURITY",
    "SURCHARGE",
    "TERMINAL",
}

LANE_CODE_TOKENS = (
    "FRT",
    "FREIGHT",
)
LANE_TEXT_TOKENS = (
    "AIR FREIGHT",
    "LINEHAUL",
    "LANE FREIGHT",
)

ORIGIN_CODE_TOKENS = (
    "-ORIGIN",
    "PICKUP",
    "PICK-UP",
    "PICK_UP",
)
ORIGIN_TEXT_TOKENS = (
    "ORIGIN",
    "PICKUP",
    "PICK UP",
    "PICK-UP",
    "COLLECTION",
    "AWB",
    "SCREEN",
    "X-RAY",
    "XRAY",
    "BUILD UP",
    "BUILDUP",
)

DESTINATION_CODE_TOKENS = (
    "-DEST",
    "DELIVERY",
    "CARTAGE",
)
DESTINATION_TEXT_TOKENS = (
    "DESTINATION",
    "DELIVERY",
    "CARTAGE",
    "CUSTOMS CLEARANCE",
    "DEST",
)


def classify_pricing_rate_scope(row_or_product: Any) -> PricingRateScope:
    """
    Classify a rate row's intended storage scope without database lookups.

    This is intentionally conservative. It uses only local fields already on the
    row/product and keeps unclear rows UNKNOWN so follow-up data work remains
    explicit instead of being inferred into a lane or local bucket.
    """
    product = getattr(row_or_product, "product_code", row_or_product)
    code = str(getattr(product, "code", "") or "").upper()
    description = str(getattr(product, "description", "") or "").upper()
    category = str(getattr(product, "category", "") or "").upper()
    domain = str(getattr(product, "domain", "") or "").upper()
    text = f"{code} {description} {category}"

    if category == "FREIGHT" or _has_any(code, LANE_CODE_TOKENS) or _has_any(text, LANE_TEXT_TOKENS):
        return PricingRateScope.LANE

    if _has_any(code, ORIGIN_CODE_TOKENS) or _has_any(text, ORIGIN_TEXT_TOKENS):
        return PricingRateScope.ORIGIN

    if _has_any(code, DESTINATION_CODE_TOKENS) or _has_any(text, DESTINATION_TEXT_TOKENS):
        return PricingRateScope.DESTINATION

    if category in LOCAL_CATEGORIES:
        if domain == "EXPORT":
            return PricingRateScope.ORIGIN
        if domain == "IMPORT":
            return PricingRateScope.DESTINATION
        if domain == "DOMESTIC":
            return PricingRateScope.LOCAL

    return PricingRateScope.UNKNOWN


def _has_any(value: str, tokens: tuple[str, ...]) -> bool:
    return any(token in value for token in tokens)
