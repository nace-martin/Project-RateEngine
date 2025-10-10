from typing import List

from ..dataclasses_v2 import BuyOffer, QuoteContext
from .base import BaseBuyAdapter


from datetime import datetime
from ..types_v2 import FeeBasis, ProvenanceType
from ..dataclasses_v2 import BuyOffer, QuoteContext, BuyLane, BuyBreak, BuyFee, Provenance

class SpotAdapter(BaseBuyAdapter):
    def collect(self, context: QuoteContext) -> List[BuyOffer]:
        offers = []
        if not context.spot_offers:
            return offers

        for spot_offer_data in context.spot_offers:
            lane = BuyLane(origin=context.origin_iata, dest=context.dest_iata, min_charge=spot_offer_data.get("min_charge", 0))
            fees = []
            for fee_code, rate in spot_offer_data.get("fees", {}).items():
                # This is a simplification. A real implementation would need to know the basis for each fee.
                fees.append(BuyFee(code=fee_code, basis=FeeBasis.PER_SHIPMENT, rate=rate))

            offer = BuyOffer(
                lane=lane,
                ccy=spot_offer_data["ccy"],
                breaks=[
                    BuyBreak(
                        from_kg=spot_offer_data["min_kg"],
                        rate_per_kg=spot_offer_data["af_per_kg"],
                    )
                ],

                fees=fees,
                valid_from=datetime.strptime(spot_offer_data["valid_from"], "%Y-%m-%d").date(),
                valid_to=datetime.strptime(spot_offer_data["valid_to"], "%Y-%m-%d").date(),
                provenance=Provenance(
                    type=ProvenanceType.SPOT,
                    ref=f"Spot offer for {lane.origin}->{lane.dest}",
                ),
            )
            offers.append(offer)

        return offers
