from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from .models import Client, RateCard

from rate_engine.engine import calculate_chargeable_weight
from rate_engine.engine import compute_fee_amount, compute_sell_lines, ShipmentInput, Piece, Money
from rate_engine.models import FeeTypes, RatecardFees, Ratecards, Services, ServiceItems, Providers, Lanes, LaneBreaks, CurrencyRates, PricingPolicy, Stations
from decimal import Decimal
from django.utils.timezone import now
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

class QuoteComputeAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.compute_url = reverse('compute-quote')
        # Authenticate via DRF TokenAuth
        User = get_user_model()
        user = User.objects.create_user(username="testuser", password="testpass")
        token = Token.objects.create(user=user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        Client.objects.create(name="Test Client")
        RateCard.objects.create(
            origin="BNE",
            destination="POM",
            min_charge=100,
            brk_45=5.50,
            brk_100=5.00,
            brk_250=4.50,
            brk_500=4.00,
            brk_1000=3.50,
        )

    def test_compute_quote_api_success(self):
        data = {
            "origin_iata": "BNE",
            "dest_iata": "POM",
            "shipment_type": "EXPORT",
            "service_scope": "AIRPORT_AIRPORT",
            "audience": "PGK_LOCAL",
            "sell_currency": "PGK",
            "pieces": [
                {"weight": 100, "length": 100, "width": 100, "height": 100}
            ]
        }
        response = self.client.post(self.compute_url, data, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertIn("buy_lines", response.data)
        self.assertIn("sell_lines", response.data)
        self.assertIn("totals", response.data)
        self.assertIn("snapshot", response.data)
        self.assertEqual(response.data["snapshot"]["shipment_type"], "EXPORT")
        self.assertEqual(response.data["snapshot"]["service_scope"], "AIRPORT_AIRPORT")

    def test_compute_quote_api_missing_fields(self):
        data = {
            "origin_iata": "BNE",
            "dest_iata": "POM",
            "audience": "PGK_LOCAL",
            "sell_currency": "PGK",
            "pieces": [
                {"weight": 100, "length": 100, "width": 100, "height": 100}
            ]
        }
        response = self.client.post(self.compute_url, data, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn("shipment_type", response.data)
        self.assertIn("service_scope", response.data)


class EngineBehaviorTests(TestCase):
    def setUp(self):
        # Minimal SELL ratecard and services to test cartage scope behavior
        self.provider = Providers.objects.create(name="Test Provider", provider_type="AIR")
        self.sell_card = Ratecards.objects.create(
            provider=self.provider,
            name="Test SELL",
            role="SELL",
            scope="DOMESTIC",
            direction="DOMESTIC",
            audience="PGK_LOCAL",
            currency="PGK",
            source="TEST",
            status="ACTIVE",
            effective_date=now().date(),
            meta={},
            created_at=now(),
            updated_at=now(),
        )
        # Ensure services exist
        self.svc_cartage, _ = Services.objects.get_or_create(code="CARTAGE", defaults={"name": "Pickup/Delivery", "basis": "PER_KG"})
        self.svc_cartage_fsc, _ = Services.objects.get_or_create(code="CARTAGE_FSC", defaults={"name": "Cartage FSC", "basis": "PERCENT_OF"})
        self.svc_air, _ = Services.objects.get_or_create(code="AIR_FREIGHT", defaults={"name": "Air Freight", "basis": "PER_KG"})

        # Create SELL items with simple amounts
        self.item_air = ServiceItems.objects.create(ratecard=self.sell_card, service=self.svc_air, currency="PGK", amount=Decimal("10.00"), tax_pct=Decimal("0.00"), conditions_json={})
        self.item_cart = ServiceItems.objects.create(ratecard=self.sell_card, service=self.svc_cartage, currency="PGK", amount=Decimal("1.00"), min_amount=Decimal("20.00"), tax_pct=Decimal("0.00"), conditions_json={})
        self.item_cart_fsc = ServiceItems.objects.create(ratecard=self.sell_card, service=self.svc_cartage_fsc, currency="PGK", amount=Decimal("0.10"), percent_of_service_code="CARTAGE", tax_pct=Decimal("0.00"), conditions_json={})

        # Minimal PER_KG fee type for compute_fee_amount test
        self.ft_perkg, _ = FeeTypes.objects.get_or_create(code="TEST_PERKG", defaults={"description": "Test Per Kg", "basis": "PER_KG", "default_tax_pct": Decimal("0.00")})
        self.rc_buy = Ratecards.objects.create(
            provider=self.provider,
            name="Test BUY",
            role="BUY",
            scope="DOMESTIC",
            direction="DOMESTIC",
            currency="PGK",
            source="TEST",
            status="ACTIVE",
            effective_date=now().date(),
            meta={},
            created_at=now(),
            updated_at=now(),
        )
        self.rf_perkg = RatecardFees.objects.create(ratecard=self.rc_buy, fee_type=self.ft_perkg, currency="PGK", amount=Decimal("0.30"), min_amount=Decimal("0.00"), max_amount=None, applies_if={}, created_at="2025-01-01T00:00:00Z")

    def test_buy_fee_perkg_multiplies_by_kg(self):
        m = compute_fee_amount(self.rf_perkg, Decimal("120.0"), {})
        self.assertEqual(m.amount, Decimal("36.00"))  # 0.30 * 120
        self.assertEqual(m.currency, "PGK")

    def test_sell_cartage_scope_exclusion_and_inclusion(self):
        # Airport-Airport: CARTAGE items should be excluded
        lines_aa = compute_sell_lines(self.sell_card, buy_context={}, kg=Decimal("50.0"), service_scope="AIRPORT_AIRPORT")
        codes_aa = [l.code for l in lines_aa]
        self.assertNotIn("CARTAGE", codes_aa)
        self.assertNotIn("CARTAGE_FSC", codes_aa)

        # Door-Door: CARTAGE items should be included
        lines_dd = compute_sell_lines(self.sell_card, buy_context={}, kg=Decimal("50.0"), service_scope="DOOR_DOOR")
        codes_dd = [l.code for l in lines_dd]
        self.assertIn("CARTAGE", codes_dd)
        self.assertIn("CARTAGE_FSC", codes_dd)


class CAFOnFxTests(TestCase):
    def setUp(self):
        # Provider
        self.provider = Providers.objects.create(name="Provider CAF", provider_type="AIR")
        # Stations minimal for lane
        self.st_origin = Stations.objects.create(iata="XOR", city="Origin", country="PG")
        self.st_dest = Stations.objects.create(iata="XDE", city="Dest", country="PG")

        # BUY ratecard in AUD with flat per-kg strategy
        self.rc_buy = Ratecards.objects.create(
            provider=self.provider,
            name="BUY AUD Flat",
            role="BUY",
            scope="DOMESTIC",
            direction="DOMESTIC",
            currency="AUD",
            rate_strategy="FLAT_PER_KG",
            source="TEST",
            status="ACTIVE",
            effective_date=now().date(),
            meta={},
            created_at=now(),
            updated_at=now(),
        )
        self.lane = Lanes.objects.create(
            ratecard=self.rc_buy,
            origin=self.st_origin,
            dest=self.st_dest,
            airline="X",
            is_direct=True,
        )
        LaneBreaks.objects.create(lane=self.lane, break_code="FLAT", per_kg=Decimal("10.00"))  # 10 AUD/kg

        # SELL ratecard in PGK (no services needed for this test)
        self.rc_sell = Ratecards.objects.create(
            provider=self.provider,
            name="SELL PGK",
            role="SELL",
            scope="DOMESTIC",
            direction="DOMESTIC",
            audience="PGK_LOCAL",
            currency="PGK",
            source="TEST",
            status="ACTIVE",
            effective_date=now().date(),
            meta={},
            created_at=now(),
            updated_at=now(),
        )

        # Pricing policy enables CAF-on-FX
        PricingPolicy.objects.create(audience="PGK_LOCAL", caf_on_fx=True, gst_applies=True, gst_pct=Decimal("10.0"))

        # FX AUD->PGK = 2.0
        CurrencyRates.objects.create(as_of_ts=now(), base_ccy="AUD", quote_ccy="PGK", rate=Decimal("2.0"))

    def test_caf_applies_on_buy_fx_conversion(self):
        # 100 kg -> base freight 1000 AUD; convert to PGK with FX=2.0 and CAF=10% -> 1000*2*1.10 = 2200 PGK
        payload = ShipmentInput(
            origin_iata=self.st_origin.iata,
            dest_iata=self.st_dest.iata,
            shipment_type="DOMESTIC",
            service_scope="AIRPORT_AIRPORT",
            audience="PGK_LOCAL",
            sell_currency="PGK",
            pieces=[Piece(weight_kg=Decimal("100.0"))],
        )
        from rate_engine.engine import compute_quote
        res = compute_quote(payload, provider_hint=self.provider.id, caf_pct=Decimal("0.10"))
        self.assertEqual(res.totals["buy_total"].amount, Decimal("2200.00"))


class SellTotalsFxCafTests(TestCase):
    def setUp(self):
        # Provider and stations
        self.provider = Providers.objects.create(name="Provider SELL FX", provider_type="AIR")
        self.st_origin = Stations.objects.create(iata="SFX", city="Origin", country="PG")
        self.st_dest = Stations.objects.create(iata="DFX", city="Dest", country="PG")

        # BUY in AUD flat 10 AUD/kg
        self.rc_buy = Ratecards.objects.create(
            provider=self.provider,
            name="BUY AUD Flat FX",
            role="BUY",
            scope="DOMESTIC",
            direction="DOMESTIC",
            currency="AUD",
            rate_strategy="FLAT_PER_KG",
            source="TEST",
            status="ACTIVE",
            effective_date=now().date(),
            meta={},
            created_at=now(),
            updated_at=now(),
        )
        self.lane = Lanes.objects.create(ratecard=self.rc_buy, origin=self.st_origin, dest=self.st_dest, airline="X", is_direct=True)
        LaneBreaks.objects.create(lane=self.lane, break_code="FLAT", per_kg=Decimal("10.00"))

        # SELL in AUD with AIR_FREIGHT service, mapping COST_PLUS_PCT 0.20 over FREIGHT
        self.rc_sell = Ratecards.objects.create(
            provider=self.provider,
            name="SELL AUD FX",
            role="SELL",
            scope="DOMESTIC",
            direction="DOMESTIC",
            audience="PGK_LOCAL",
            currency="AUD",
            source="TEST",
            status="ACTIVE",
            effective_date=now().date(),
            meta={},
            created_at=now(),
            updated_at=now(),
        )

        # Ensure required types and services
        self.ft_freight, _ = FeeTypes.objects.get_or_create(code="FREIGHT", defaults={"description": "Base Freight", "basis": "PER_KG", "default_tax_pct": Decimal("0.00")})
        self.svc_air, _ = Services.objects.get_or_create(code="AIR_FREIGHT", defaults={"name": "Air Freight", "basis": "PER_KG"})
        self.item_air = ServiceItems.objects.create(ratecard=self.rc_sell, service=self.svc_air, currency="AUD", amount=None, tax_pct=Decimal("0.00"), conditions_json={})

        from rate_engine.models import SellCostLinksSimple
        SellCostLinksSimple.objects.create(sell_item=self.item_air, buy_fee_code=self.ft_freight, mapping_type="COST_PLUS_PCT", mapping_value=Decimal("0.20"))

        # Policy + FX
        PricingPolicy.objects.create(audience="PGK_LOCAL", caf_on_fx=True, gst_applies=False, gst_pct=Decimal("0.00"))
        CurrencyRates.objects.create(as_of_ts=now(), base_ccy="AUD", quote_ccy="PGK", rate=Decimal("2.0"))

    def test_sell_total_converts_with_caf(self):
        from rate_engine.engine import compute_quote
        payload = ShipmentInput(
            origin_iata=self.st_origin.iata,
            dest_iata=self.st_dest.iata,
            shipment_type="DOMESTIC",
            service_scope="AIRPORT_AIRPORT",
            audience="PGK_LOCAL",
            sell_currency="PGK",
            pieces=[Piece(weight_kg=Decimal("100.0"))],
        )
        res = compute_quote(payload, provider_hint=self.provider.id, caf_pct=Decimal("0.10"))
        # BUY: 100kg * 10 AUD -> 1000 AUD -> 1000*2*1.10 = 2200 PGK
        self.assertEqual(res.totals["buy_total"].amount, Decimal("2200.00"))
        # SELL AIR_FREIGHT: 1000 * 1.20 = 1200 AUD -> 1200*2*1.10 = 2640 PGK
        self.assertEqual(res.totals["sell_total"].amount, Decimal("2640.00"))
