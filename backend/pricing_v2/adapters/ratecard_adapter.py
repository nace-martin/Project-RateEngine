from typing import List
from decimal import Decimal

# Models from our new ratecards app
from ratecards.models import RateCardLane

# Dataclasses and types for the pricing engine
from pricing_v2.dataclasses_v2 import QuoteContext, BuyOffer, BuyLane, BuyBreak, BuyFee, Provenance
from pricing_v2.types_v2 import FeeBasis, ProvenanceType

# The chargeable weight utility we just created
from pricing_v2.utils_v2 import calculate_chargeable_weight

# The base adapter class
from .base import BaseBuyAdapter


class RatecardAdapter(BaseBuyAdapter):
    """
    Adapter for ingesting cost rates from the database-backed rate card system.
    """
    key = "ratecard_db"

    def collect(self, ctx: QuoteContext) -> List[BuyOffer]:
        # 1. Calculate chargeable weight using the utility
        chargeable_weight = calculate_chargeable_weight(ctx.pieces)
        if chargeable_weight <= 0:
            return [] # No weight, no rate

        # 2. Find the correct rate card lane from the database
        try:
            lane = RateCardLane.objects.get(
                origin_code=ctx.origin_iata,
                destination_code=ctx.dest_iata
                # Note: This assumes only one active rate card per lane.
                # A future version might need filtering by date or rate card name.
            )
        except RateCardLane.DoesNotExist:
            return [] # No cost rate card found for this lane

        # 3. Find the applicable weight break for the chargeable weight
        # We look for the highest weight break that is less than or equal to our weight.
        rate_break = lane.breaks.filter(weight_break_kg__lte=chargeable_weight).last()

        if not rate_break:
            # No applicable weight break found (e.g., shipment is too light)
            return []

        # 4. Calculate the base freight cost
        # The cost is the chargeable weight multiplied by the rate from the break.
        freight_cost = chargeable_weight * rate_break.rate_per_kg

        # 5. Gather all surcharges for the lane
        fees = []
        for surcharge in lane.surcharges.all():
            fees.append(BuyFee(
                code=surcharge.code,
                basis=FeeBasis.PER_SHIPMENT, # Assuming per-shipment for now
                rate=surcharge.rate
            ))

        # 6. Construct and return the final BuyOffer
        offer = BuyOffer(
            lane=BuyLane(origin=ctx.origin_iata, dest=ctx.dest_iata),
            # For now, we'll assume the currency is on the rate card file,
            # but we'll need a way to store and retrieve this. Hardcoding PGK for now.
            ccy="PGK",
            breaks=[
                BuyBreak(
                    from_kg=chargeable_weight,
                    rate_per_kg=rate_break.rate_per_kg,
                    # This represents the calculated total freight cost
                    total=freight_cost
                )
            ],
            fees=fees,
            provenance=Provenance(
                type=ProvenanceType.RATE_CARD,
                ref=f"db:{lane.ratecard_file.name}:lane:{lane.id}"
            ),
        )

        return [offer]