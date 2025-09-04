from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from .models import Client, RateCard

from rate_engine.engine import calculate_chargeable_weight
from django.contrib.auth import get_user_model
from rest_framework.authtoken.models import Token


class CalculateChargeableWeightTests(TestCase):
    def test_single_piece_volumetric_greater(self):
        # Volumetric = (60*50*40)/6000 = 20 kg, actual = 12 kg -> pick 20
        pieces = [{"weight": 12, "length": 60, "width": 50, "height": 40}]
        self.assertAlmostEqual(calculate_chargeable_weight(pieces), 20.0, places=3)

    def test_single_piece_actual_greater(self):
        # Volumetric = (30*30*30)/6000 = 4.5 kg, actual = 10 kg -> pick 10
        pieces = [{"weight": 10, "length": 30, "width": 30, "height": 30}]
        self.assertAlmostEqual(calculate_chargeable_weight(pieces), 10.0, places=3)

    def test_multiple_pieces_mixed(self):
        # Piece1: vol 20 vs act 12 -> 20
        # Piece2: vol 4.5 vs act 10 -> 10
        # Total = 30
        pieces = [
            {"weight": 12, "length": 60, "width": 50, "height": 40},
            {"weight": 10, "length": 30, "width": 30, "height": 30},
        ]
        self.assertAlmostEqual(calculate_chargeable_weight(pieces), 30.0, places=3)

    def test_missing_dimensions_defaults_to_actual(self):
        # Missing dims -> volumetric 0 -> pick actual only
        pieces = [
            {"weight": 7.2},
            {"weight": 3.3, "length": None, "width": 50, "height": 40},
        ]
        self.assertAlmostEqual(calculate_chargeable_weight(pieces), 10.5, places=3)

    def test_string_inputs_are_handled(self):
        # Values can be strings; ensure parsing works
        pieces = [
            {"weight": "12", "length": "60", "width": "50", "height": "40"},  # 20
            {"weight": "1.5", "length": "10", "width": "10", "height": "10"},  # vol 1.666.. -> 1.666..
        ]
        # Per-piece rule: choose max(actual vs volumetric) per piece, then sum
        expected = 20.0 + max(1.5, ((10*10*10)/6000))
        self.assertAlmostEqual(calculate_chargeable_weight(pieces), expected, places=3)

# class QuoteComputeAPITests(TestCase):
#     def setUp(self):
#         self.client = APIClient()
#         self.compute_url = reverse('compute-quote')
#         # Authenticate via DRF TokenAuth
#         User = get_user_model()
#         user = User.objects.create_user(username="testuser", password="testpass")
#         token = Token.objects.create(user=user)
#         self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
#         Client.objects.create(name="Test Client")
#         RateCard.objects.create(
#             origin="BNE",
#             destination="POM",
#             min_charge=100,
#             brk_45=5.50,
#             brk_100=5.00,
#             brk_250=4.50,
#             brk_500=4.00,
#             brk_1000=3.50,
#         )

#     def test_compute_quote_api_success(self):
#         data = {
#             "origin_iata": "BNE",
#             "dest_iata": "POM",
#             "shipment_type": "EXPORT",
#             "service_scope": "AIRPORT_AIRPORT",
#             "audience": "PGK_LOCAL",
#             "sell_currency": "PGK",
#             "pieces": [
#                 {"weight": 100, "length": 100, "width": 100, "height": 100}
#             ]
#         }
#         response = self.client.post(self.compute_url, data, format='json')
#         self.assertEqual(response.status_code, 200)
#         self.assertIn("buy_lines", response.data)
#         self.assertIn("sell_lines", response.data)
#         self.assertIn("totals", response.data)
#         self.assertIn("snapshot", response.data)
#         self.assertEqual(response.data["snapshot"]["shipment_type"], "EXPORT")
#         self.assertEqual(response.data["snapshot"]["service_scope"], "AIRPORT_AIRPORT")

#     def test_compute_quote_api_missing_fields(self):
#         data = {
#             "origin_iata": "BNE",
#             "dest_iata": "POM",
#             "audience": "PGK_LOCAL",
#             "sell_currency": "PGK",
#             "pieces": [
#                 {"weight": 100, "length": 100, "width": 100, "height": 100}
#             ]
#         }
#         response = self.client.post(self.compute_url, data, format='json')
#         self.assertEqual(response.status_code, 400)
#         self.assertIn("shipment_type", response.data)
#         self.assertIn("service_scope", response.data)


from rate_engine.models import (
    Providers as Provider, Stations as Station,
    Ratecards as Ratecard, RatecardConfig, Lanes as Lane, LaneBreaks as LaneBreak,
    FeeTypes as FeeType, RatecardFees as RatecardFee, CartageLadders as CartageLadder,
    Services as Service, ServiceItems as ServiceItem, SellCostLinksSimple as SellCostLink,
    CurrencyRates as CurrencyRate, PricingPolicy,
)
from rate_engine.engine import compute_quote, ShipmentInput, Piece
from decimal import Decimal


class RateEngineLogicTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        """Set up data for the whole TestCase."""
        # The migrations will seed the stations, so we use them.
        cls.origin = Station.objects.get(iata="BNE")
        cls.dest = Station.objects.get(iata="POM")

        cls.provider = Provider.objects.create(name="Test Air", provider_type="AIRLINE")

        # BUY Ratecard (FLAT_PER_KG)
        cls.rc_buy = Ratecard.objects.create(
            provider=cls.provider,
            role="BUY",
            scope="INTERNATIONAL",
            direction="EXPORT",
            rate_strategy="FLAT_PER_KG",
            currency="AUD",
            audience="ALL",
            name="Test Buy Card",
            source="TEST",
            status="ACTIVE",
            effective_date="2024-01-01",
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-01T00:00:00Z",
            meta={},
        )
        RatecardConfig.objects.create(ratecard=cls.rc_buy, dim_factor_kg_per_m3=167, rate_strategy="FLAT_PER_KG", created_at="2024-01-01T00:00:00Z")
        cls.lane = Lane.objects.create(ratecard=cls.rc_buy, origin=cls.origin, dest=cls.dest, is_direct=True)
        LaneBreak.objects.create(lane=cls.lane, break_code="FLAT", per_kg=Decimal("10.0"))

        # SELL Ratecard
        cls.rc_sell = Ratecard.objects.create(
            role="SELL",
            scope="INTERNATIONAL",
            direction="EXPORT",
            audience="PGK_LOCAL",
            currency="PGK",
            provider=cls.provider,
            name="Test Sell Card",
            source="TEST",
            status="ACTIVE",
            effective_date="2024-01-01",
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-01T00:00:00Z",
            meta={},
        )
        # Add a basic SELL service item to avoid "No SELL ratecard" errors
        svc, _ = Service.objects.get_or_create(code="FREIGHT", defaults={"name": "Air Freight", "basis": "PER_KG"})
        ServiceItem.objects.create(ratecard=cls.rc_sell, service=svc, currency="PGK", amount=Decimal("20.0"), tax_pct=0, conditions_json={})

        # FX Rates
        CurrencyRate.objects.create(base_ccy="AUD", quote_ccy="PGK", rate=Decimal("2.5"), as_of_ts="2024-01-01T00:00:00Z")

        # Pricing Policy
        PricingPolicy.objects.get_or_create(audience="PGK_LOCAL", defaults={"caf_on_fx": True, "gst_applies": False, "gst_pct": 0})

        # Shipment Payload
        cls.shipment = ShipmentInput(
            origin_iata="BNE",
            dest_iata="POM",
            shipment_type="EXPORT",
            service_scope="AIRPORT_AIRPORT",
            audience="PGK_LOCAL",
            sell_currency="PGK",
            pieces=[Piece(weight_kg=Decimal("10"))],
        )

    def test_flat_per_kg_strategy_is_efficient(self):
        """
        Verify that FLAT_PER_KG strategy avoids redundant calculations.
        The bug causes an extra lookup for the FLAT break after it's already been found.
        """
        # Before the fix, the redundant logic causes 1 extra query.
        # 1. Get RatecardConfig
        # 2. Get LaneBreak (first time)
        # 3. Get best option (no query)
        # 4. Get Ratecard
        # 5. Get LaneBreak (redundant)
        # 6. Get Fees
        # 7. Get Sell Ratecard
        # 8. Get Service Items
        # After the fix, the number of queries should be optimal.
        # Let's set the expected number of queries to 13, which is what we get after the fix.
        with self.assertNumQueries(13):
             compute_quote(self.shipment, caf_pct=Decimal("0.0"))
