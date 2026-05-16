from __future__ import annotations

from typing import Any

from pricing_v4.services.import_cogs_scope import classify_import_cogs_scope
from pricing_v4.services.pricing_rate_scope import PricingRateScope, classify_pricing_rate_scope


LOCAL_TABLE_NAMES = {"LocalCOGSRate", "LocalSellRate"}


def explicit_scope(row: Any) -> str:
    return str(getattr(row, "scope", "") or "UNSET")


def computed_transition_scope(row: Any) -> str:
    model_name = type(row).__name__
    if model_name in LOCAL_TABLE_NAMES:
        return PricingRateScope.LOCAL.value
    if model_name == "ImportCOGS":
        return classify_import_cogs_scope(row).value
    return classify_pricing_rate_scope(row).value


def scope_mismatch(row: Any) -> bool:
    persisted = getattr(row, "scope", None)
    if not persisted:
        return False
    return str(persisted) != computed_transition_scope(row)


def scope_mismatch_label(row: Any) -> str:
    if not getattr(row, "scope", None):
        return ""
    if scope_mismatch(row):
        return f"MISMATCH explicit={explicit_scope(row)} computed={computed_transition_scope(row)}"
    return ""
