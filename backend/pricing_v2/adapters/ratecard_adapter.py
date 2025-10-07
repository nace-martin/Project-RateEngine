import os
from typing import List
from pricing_v2.dataclasses_v2 import QuoteContext, BuyOffer, BuyLane, BuyBreak, BuyFee, Provenance
from pricing_v2.types_v2 import FeeBasis, Side, ProvenanceType
from pricing_v2.resolution_v2 import resolve_currency_and_fee_scope
from pricing_v2.utils_v2 import parse_html_rate_card
from .base import BaseBuyAdapter

# Define where our test rate cards are located
TEST_CARDS_DIR = os.path.join(os.path.dirname(__file__), '..', 'tests')
RATE_CARD_MAP = {
    "AUD_DESTINATION_ONLY": os.path.join(TEST_CARDS_DIR, "2025_A2D_AUD.html"),
    "PGK_DESTINATION_ONLY": os.path.join(TEST_CARDS_DIR, "2025_A2D_PGK.html"),
    # We will add export cards here later
}

class RatecardAdapter(BaseBuyAdapter):
    """Adapter for ingesting structured rate cards from HTML files."""
    key = "ratecard"

    def collect(self, ctx: QuoteContext) -> List[BuyOffer]:
        # Step 1: Ask the "Rule Expert" what to do.
        invoice_currency, fee_scope, reason = resolve_currency_and_fee_scope(
            scope=ctx.scope,
            payment_term=ctx.payment_term,
            audience=ctx.audience
        )

        if not invoice_currency:
            return [] # Cannot determine which rate card to use.

        # Step 2: Find the correct "Recipe Book" (the HTML rate card).
        card_key = f"{invoice_currency}_{fee_scope}"
        card_path = RATE_CARD_MAP.get(card_key)

        if not card_path or not os.path.exists(card_path):
            return [] # We don't have a rate card for this scenario yet.

        # Step 3: Use the "Reading Assistant" to get the prices.
        card_data = parse_html_rate_card(card_path)

        # Step 4: Construct the 'BuyOffer' (the standard digital form).
        # This is a simplified version. A real implementation would have more complex logic
        # for weight breaks and matching multiple fees.
        
        fees = []
        # Map our generic fee codes to the item codes in the HTML file
        FEE_CODE_MAP = {
            "CLEAR": "040-61130",
            "AGENCY": "040-61000",
            "HANDLING": "040-61170",
            "CARTAGE": "040-61333",
            "FUEL_PCT": "040-61361",
        }

        for code, item_code in FEE_CODE_MAP.items():
            if fee_data := card_data["fees"].get(item_code):
                 fees.append(BuyFee(
                     code=code,
                     basis=FeeBasis(fee_data["basis"]),
                     rate=fee_data["rate"],
                     minimum=fee_data["minimum"],
                     side=Side.DEST
                 ))

        # For this MVP, we are focusing on A2D, so we create a simple offer.
        # A full implementation would handle A2A with weight breaks here.
        offer = BuyOffer(
            lane=BuyLane(origin=ctx.origin_iata, dest=ctx.dest_iata),
            ccy=invoice_currency,
            fees=fees,
            provenance=Provenance(type=ProvenanceType.RATE_CARD, ref=os.path.basename(card_path)),
        )

        return [offer]