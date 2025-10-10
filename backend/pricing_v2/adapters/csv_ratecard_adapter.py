import csv
import os
from typing import List
from ..dataclasses_v2 import QuoteContext, BuyOffer, BuyLane, BuyBreak
from .base import BaseBuyAdapter

CSV_RATE_CARD_PATH = os.path.join(os.path.dirname(__file__), '..', 'tests', 'rates.csv')

class CsvRatecardAdapter(BaseBuyAdapter):
    """Adapter for ingesting structured rate cards from CSV files."""
    key = "csv_ratecard"

    def collect(self, ctx: QuoteContext) -> List[BuyOffer]:
        offers = []
        if not os.path.exists(CSV_RATE_CARD_PATH):
            return offers

        with open(CSV_RATE_CARD_PATH, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if ctx.origin_iata == row['origin'] and ctx.dest_iata == row['destination']:
                    lane = BuyLane(
                        origin=row['origin'],
                        dest=row['destination'],
                        min_charge=float(row['min_charge'])
                    )
                    breaks = [
                        BuyBreak(from_kg=45, rate_per_kg=float(row['45kg'])),
                        BuyBreak(from_kg=100, rate_per_kg=float(row['100kg'])),
                        BuyBreak(from_kg=250, rate_per_kg=float(row['250kg']))
                    ]
                    offer = BuyOffer(
                        lane=lane,
                        ccy="USD", # Assuming USD for now
                        breaks=breaks
                    )
                    offers.append(offer)
        return offers
