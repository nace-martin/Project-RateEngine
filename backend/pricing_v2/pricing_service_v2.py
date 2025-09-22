from typing import Any, Dict, List

from .dataclasses_v2 import (BuyResult, CalcLine, NormalizedContext,
                             QuoteContext, SellResult, Snapshot, Totals)
from .recipes import AUDIENCE, INVOICE_CCY, run_recipe


def normalize(context: QuoteContext) -> NormalizedContext:
    """Normalizes the QuoteContext into a standardized format and derives audience/invoice currency."""
    # T015: Update the normalize function to derive audience and invoice currency.
    # For A2D Import, PREPAID -> AUD, COLLECT -> PGK
    if context.payment_term == "PREPAID":
        invoice_ccy = INVOICE_CCY["AUD"]
        audience = AUDIENCE["PNG_CUSTOMER_PREPAID"]
    elif context.payment_term == "COLLECT":
        invoice_ccy = INVOICE_CCY["PGK"]
        audience = AUDIENCE["PNG_CUSTOMER_COLLECT"]
    else:
        raise ValueError(f"Unsupported payment term: {context.payment_term}")

    return NormalizedContext(audience=audience, invoice_ccy=invoice_ccy, origin_iata=context.origin_iata)


def rate_buy(context: QuoteContext) -> BuyResult:
    """Rates the buy side of the quote, applies fee menu selection, and handles missing BUY data."""
    # T016: Update the rate_buy function to apply the new fee menu selection rules and handle missing BUY data.
    buy_lines: List[CalcLine] = []
    is_incomplete = False
    reasons: List[str] = []

    # Simulate fetching BUY rates and applying fee selection rules
    if context.origin_iata == "UNS":  # Example for unsupported origin
        is_incomplete = True
        reasons.append("Manual Rate Required: Unsupported origin IATA.")
    else:
        # Placeholder for actual BUY rate fetching and fee selection
        buy_lines.append(
            CalcLine(
                code="FREIGHT", description="Air Freight", amount=50.0, currency="PGK"
            )
        )
        buy_lines.append(
            CalcLine(
                code="FUEL_SURCHARGE",
                description="Fuel Surcharge",
                amount=5.0,
                currency="PGK",
            )
        )

    buy_total_pgk = sum(line.amount for line in buy_lines if line.currency == "PGK")

    return BuyResult(
        buy_lines=buy_lines,
        buy_total_pgk=buy_total_pgk,
        is_incomplete=is_incomplete,
        reasons=reasons,
    )


def map_to_sell(quote_context: QuoteContext, buy_result: BuyResult) -> SellResult:
    """Maps the buy result to the sell side using the appropriate recipe."""
    # T017: Update the map_to_sell function to reflect the new fee menu and currency rules.
    recipe_key = (quote_context.mode, quote_context.scope, quote_context.payment_term)
    sell_recipe = run_recipe(recipe_key, quote_context, buy_result)

    sell_subtotal = sum(line.amount for line in sell_recipe.sell_lines)
    # Placeholder for tax calculation
    sell_tax = sell_subtotal * 0.10  # Example 10% tax
    sell_total = sell_subtotal + sell_tax

    return SellResult(
        sell_lines=sell_recipe.sell_lines,
        sell_subtotal=sell_subtotal,
        sell_tax=sell_tax,
        sell_total=sell_total,
        snapshot=sell_recipe.snapshot,
        buy_total_pgk=buy_result.buy_total_pgk,
        is_incomplete=buy_result.is_incomplete,
        reasons=buy_result.reasons,
    )


def tax_fx_round(sell_result: SellResult, invoice_ccy: str) -> Totals:
    """Applies taxes, foreign exchange, and rounding to the sell result."""
    # T018: Update the tax_fx_round function to ensure totals.invoice_ccy is correctly set and itemized sell lines are aligned to the invoice currency.
    # Placeholder for FX and rounding logic
    # For now, assume sell_result.sell_total is already in invoice_ccy

    return Totals(
        invoice_ccy=invoice_ccy,
        sell_subtotal=sell_result.sell_subtotal,
        sell_tax=sell_result.sell_tax,
        sell_total=sell_result.sell_total,
        buy_total_pgk=sell_result.buy_total_pgk,  # Assuming buy_total_pgk is passed through
        is_incomplete=sell_result.is_incomplete,  # Assuming is_incomplete is passed through
        reasons=sell_result.reasons,  # Assuming reasons is passed through
    )


def compute_quote_v2(context: QuoteContext) -> Totals:
    """Orchestrates the V2 rating core functions."""
    # T019: Update the compute_quote_v2 orchestrator function to handle the is_incomplete flag and snapshot generation.
    normalized_context = normalize(context)
    buy_result = rate_buy(normalized_context) # Pass normalized_context to rate_buy

    # If buy_result indicates incomplete, propagate it
    if buy_result.is_incomplete:
        return Totals(
            invoice_ccy=normalized_context.invoice_ccy,
            sell_subtotal=0.0,
            sell_tax=0.0,
            sell_total=0.0,
            buy_total_pgk=0.0,
            is_incomplete=True,
            reasons=buy_result.reasons,
        )

    sell_result = map_to_sell(context, buy_result)
    totals = tax_fx_round(sell_result, normalized_context.invoice_ccy)
    return totals
