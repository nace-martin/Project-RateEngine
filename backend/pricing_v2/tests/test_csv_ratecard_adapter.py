from pricing_v2.adapters.csv_ratecard_adapter import CsvRatecardAdapter
from pricing_v2.dataclasses_v2 import QuoteContext

def _ctx(**kw):
    """Helper to build a realistic QuoteContext for testing."""
    return QuoteContext(
        origin_iata=kw.get("o", "POM"),
        dest_iata=kw.get("d", "BNE"),
    )

class TestCsvRatecardAdapter:
    def test_collect_rates(self):
        # 1. Create an instance of the CsvRatecardAdapter
        adapter = CsvRatecardAdapter()

        # 2. Call the collect method with a QuoteContext object
        ctx = _ctx(o="POM", d="BNE")
        offers = adapter.collect(ctx)

        # 3. Assert that the method returns the correct number of BuyOffer objects
        assert len(offers) == 1

        # 4. Assert that the data in the BuyOffer objects is correct
        offer = offers[0]
        assert offer.lane.origin == "POM"
        assert offer.lane.dest == "BNE"
        assert offer.lane.min_charge == 100.0
        assert offer.ccy == "USD"
        assert len(offer.breaks) == 3
        assert offer.breaks[0].from_kg == 45
        assert offer.breaks[0].rate_per_kg == 5.5
        assert offer.breaks[1].from_kg == 100
        assert offer.breaks[1].rate_per_kg == 5.25
        assert offer.breaks[2].from_kg == 250
        assert offer.breaks[2].rate_per_kg == 5.00
