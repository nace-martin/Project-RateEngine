from __future__ import annotations
import logging
from .dataclasses_v2 import QuoteContext, Totals
from .recipes import get_invoice_currency_recipe, get_fee_menu_recipe

logger = logging.getLogger(__name__)

def compute_quote_v2(quote_context: QuoteContext) -> Totals:
    incomplete_reasons = []

    invoice_ccy_recipe = get_invoice_currency_recipe()
    invoice_ccy = invoice_ccy_recipe.action(quote_context)

    fee_menu_recipe = get_fee_menu_recipe()
    sell_lines = fee_menu_recipe.action(quote_context)

    if not sell_lines:
        incomplete_reasons.append("SELL rate bundle missing for IMPORT/PREPAID/A2D (destination fees)")

    # Placeholder for BUY lines - to be implemented later
    buy_lines = []
    if not buy_lines: # Assuming BUY lines are also required
        incomplete_reasons.append("BUY rate bundle missing (placeholder)")


    is_incomplete = bool(incomplete_reasons)

    sell_subtotal = sum(line.amount for line in sell_lines) if sell_lines else 0
    buy_subtotal = sum(line.amount for line in buy_lines) if buy_lines else 0


    return Totals(
        invoice_ccy=invoice_ccy,
        is_incomplete=is_incomplete,
        reasons=incomplete_reasons,
        sell_subtotal=sell_subtotal,
        sell_total=sell_subtotal,  # assume no tax for now
        sell_lines=sell_lines,
        buy_subtotal=buy_subtotal,
        buy_total=buy_subtotal, # assume no tax for now
        buy_lines=buy_lines
    )