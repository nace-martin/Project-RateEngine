from __future__ import annotations

from enum import StrEnum
from typing import Any


class ImportCOGSScope(StrEnum):
    LANE = "LANE"
    ORIGIN = "ORIGIN"
    DESTINATION = "DESTINATION"
    UNKNOWN = "UNKNOWN"


ORIGIN_CODE_TOKENS = (
    "-ORIGIN",
    "IMP-PICKUP",
    "IMP-FSC-PICKUP",
)
ORIGIN_TEXT_TOKENS = (
    "ORIGIN",
    "PICKUP",
    "PICK UP",
    "AWB",
    "X-RAY",
    "XRAY",
    "SCREEN",
)

DESTINATION_CODE_TOKENS = (
    "-DEST",
    "IMP-CLEAR",
    "IMP-CARTAGE",
    "IMP-FSC-CARTAGE",
)
DESTINATION_TEXT_TOKENS = (
    "DESTINATION",
    "CUSTOMS CLEARANCE",
    "CARTAGE",
    "DELIVERY",
    "HANDLING",
    "TERMINAL",
)

LANE_CODE_TOKENS = (
    "IMP-FRT",
    "FRT-AIR",
)
LANE_TEXT_TOKENS = (
    "IMPORT AIR FREIGHT",
    "LINEHAUL",
    "LANE FREIGHT",
)


def classify_import_cogs_scope(row_or_product: Any) -> ImportCOGSScope:
    """
    Classify the intended scope of an ImportCOGS row without database lookups.

    The helper intentionally uses only fields already present on the row or its
    attached product_code. Ambiguous import charges stay UNKNOWN so cleanup work
    remains visible instead of being guessed into a future normalized scope.
    """
    product = getattr(row_or_product, "product_code", row_or_product)
    code = str(getattr(product, "code", "") or "").upper()
    description = str(getattr(product, "description", "") or "").upper()
    category = str(getattr(product, "category", "") or "").upper()
    text = f"{code} {description} {category}"

    if _has_any(code, ORIGIN_CODE_TOKENS) or _has_any(text, ORIGIN_TEXT_TOKENS):
        return ImportCOGSScope.ORIGIN

    if _has_any(code, DESTINATION_CODE_TOKENS) or _has_any(text, DESTINATION_TEXT_TOKENS):
        return ImportCOGSScope.DESTINATION

    if category == "FREIGHT" or _has_any(code, LANE_CODE_TOKENS) or _has_any(text, LANE_TEXT_TOKENS):
        return ImportCOGSScope.LANE

    return ImportCOGSScope.UNKNOWN


def _has_any(value: str, tokens: tuple[str, ...]) -> bool:
    return any(token in value for token in tokens)
