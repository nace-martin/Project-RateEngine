import pytest
from pricing_v2.adapters.ratecard_adapter import RatecardAdapter
from pricing_v2.dataclasses_v2 import QuoteContext

class TestRateCardAdapter:
    def test_adapter_initialization(self):
        adapter = RatecardAdapter()
        assert adapter.key == "ratecard"

    def test_collect_no_rate_card(self):
        adapter = RatecardAdapter()
        ctx = QuoteContext(origin_iata="XXX", dest_iata="YYY")
        offers = adapter.collect(ctx)
        assert offers == []