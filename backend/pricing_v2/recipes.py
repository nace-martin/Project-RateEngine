from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List

from pricing_v2.dataclasses_v2 import CalcLine, QuoteContext, Snapshot

# Tiny Tables
AUDIENCE = {
    "PNG_CUSTOMER_PREPAID": "PNG_CUSTOMER_PREPAID",
    "PNG_CUSTOMER_COLLECT": "PNG_CUSTOMER_COLLECT",
    # Add other audiences as needed
}

INVOICE_CCY = {
    "AUD": "AUD",
    "PGK": "PGK",
    # Add other currencies as needed
}

SCOPE_SEGMENTS = {
    "A2D": ["AIR", "DOMESTIC"],
    # Add other scope segments as needed
}


@dataclass
class SellRecipe:
    audience: str
    invoice_ccy: str
    sell_lines: List[CalcLine] = field(default_factory=list)
    snapshot: Snapshot = field(default_factory=Snapshot)


# Recipe Index
RECIPE_INDEX: Dict[tuple, Callable] = {}


def recipe_air_a2d_prepaid(quote_context: QuoteContext, buy_result: Any) -> SellRecipe:
    """Minimal SellRecipe for (A2D, PNG_CUSTOMER_PREPAID)"""
    # T012: Implement logic for audience and invoice currency derivation
    if quote_context.payment_term == "PREPAID":
        invoice_ccy = INVOICE_CCY["AUD"]  # Origin country currency for AU->PG
        audience = AUDIENCE["PNG_CUSTOMER_PREPAID"]
    elif quote_context.payment_term == "COLLECT":
        invoice_ccy = INVOICE_CCY["PGK"]  # Destination country currency for AU->PG
        audience = AUDIENCE["PNG_CUSTOMER_COLLECT"]
    else:
        raise ValueError(f"Unsupported payment term: {quote_context.payment_term}")

    # T013: Implement logic for fee menu selection (DESTINATION-side services only)
    sell_lines: List[CalcLine] = []
    # Placeholder: In a real scenario, this would involve filtering buy_result.buy_lines
    # based on whether they are destination-side services.
    # For now, let's assume some dummy sell lines.
    sell_lines.append(
        CalcLine(
            code="DELIVERY",
            description="Delivery Fee",
            amount=100.0,
            currency=invoice_ccy,
        )
    )

    # T014: Implement logic to skip fees if their base is absent and record a warning in the snapshot.
    snapshot = Snapshot()
    # Placeholder: Example of recording a skipped fee
    # if some_fee_base_is_absent:
    #     snapshot.skipped_fees.append({"fee_code": "SOME_FEE", "reason": "Base absent"})

    return SellRecipe(
        audience=audience,
        invoice_ccy=invoice_ccy,
        sell_lines=sell_lines,
        snapshot=snapshot,
    )


RECIPE_INDEX[("AIR", "A2D", "PREPAID")] = recipe_air_a2d_prepaid
RECIPE_INDEX[("AIR", "A2D", "COLLECT")] = (
    recipe_air_a2d_prepaid  # Use the same recipe for now
)


def run_recipe(
    recipe_key: tuple, quote_context: QuoteContext, buy_result: Any
) -> SellRecipe:
    """Recipe executor"""
    recipe_func = RECIPE_INDEX.get(recipe_key)
    if not recipe_func:
        raise ValueError(f"No recipe found for key: {recipe_key}")
    return recipe_func(quote_context, buy_result)
