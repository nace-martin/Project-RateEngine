import pytest
from decimal import Decimal
from ratecards.models import RatecardFile, RateCardLane, RateBreak, Surcharge
from pricing_v2.adapters.ratecard_adapter import RatecardAdapter
from pricing_v2.dataclasses_v2 import QuoteContext

@pytest.mark.django_db
class TestRatecardAdapterIntegration:
    """
    Integration tests for the RatecardAdapter that interact with the database.
    """

    @pytest.fixture(autouse=True)
    def setup_db_data(self):
        """
        Sets up the necessary data in the test database before each test.
        """
        self.ratecard_file = RatecardFile.objects.create(name="Test Carrier Rates 2025")
        self.lane = RateCardLane.objects.create(
            ratecard_file=self.ratecard_file,
            origin_code="SYD",
            destination_code="POM"
        )
        RateBreak.objects.create(lane=self.lane, weight_break_kg=Decimal("0"), rate_per_kg=Decimal("5.50"))
        RateBreak.objects.create(lane=self.lane, weight_break_kg=Decimal("45"), rate_per_kg=Decimal("5.25"))
        RateBreak.objects.create(lane=self.lane, weight_break_kg=Decimal("100"), rate_per_kg=Decimal("5.00"))
        Surcharge.objects.create(lane=self.lane, name="Fuel Surcharge", code="FSC", rate=Decimal("25.00"))

    def test_collect_calculates_cost_correctly(self):
        """
        Tests a successful scenario where a matching lane and break are found.
        """
        adapter = RatecardAdapter()
        context = QuoteContext(
            origin_iata="SYD",
            dest_iata="POM",
            pieces=[{'weight_kg': 50, 'length_cm': 100, 'width_cm': 80, 'height_cm': 50}]
        )
        # Chargeable weight for pieces: (100*80*50)/6000 = 66.66... -> 67kg
        # This falls into the +45kg break, so rate is 5.25
        # Expected freight cost = 67 * 5.25 = 351.75
        # Expected total fees = 25.00 (FSC)

        offers = adapter.collect(context)

        assert len(offers) == 1
        offer = offers[0]
        assert offer.lane.origin == "SYD"
        assert offer.lane.dest == "POM"
        
        # Check the calculated freight cost
        assert offer.breaks[0].total == Decimal("351.75")
        
        # Check that the surcharge is included
        assert len(offer.fees) == 1
        assert offer.fees[0].code == "FSC"
        assert offer.fees[0].rate == Decimal("25.00")

    def test_collect_returns_empty_if_no_lane_found(self):
        """
        Tests that an empty list is returned if no rate card exists for the lane.
        """
        adapter = RatecardAdapter()
        context = QuoteContext(origin_iata="LAX", dest_iata="LHR", pieces=[{'weight_kg': 10}])

        offers = adapter.collect(context)

        assert len(offers) == 0

    def test_collect_returns_empty_if_weight_is_too_low(self):
        """
        Tests that an empty list is returned if the weight doesn't meet any break.
        """
        # Our lowest break is 0kg. Let's delete it to test this scenario.
        RateBreak.objects.filter(weight_break_kg=Decimal("0")).delete()
        
        adapter = RatecardAdapter()
        context = QuoteContext(origin_iata="SYD", dest_iata="POM", pieces=[{'weight_kg': 10}])
        
        offers = adapter.collect(context)

        # Since 10kg is less than the new lowest break of 45kg, no rate should be found.
        assert len(offers) == 0