from decimal import Decimal
from django.test import TestCase
from django.utils.timezone import now

from core.models import FeeTypes, Providers, Services, Stations, CurrencyRates
from pricing.models import (
    Audience,
    LaneBreaks,
    Lanes,
    PricingPolicy,
    RatecardConfig,
    RatecardFees,
    Ratecards,
    SellCostLinksSimple,
    ServiceItems,
    Routes,
    RouteLegs,
)
from pricing.dataclasses import Money, Piece, ShipmentInput
from pricing.services.pricing_service import (
    calculate_chargeable_weight_per_piece,
    compute_quote,
    _normalize_basis,
)
from pricing.services.utils import d, TWOPLACES, ZERO


class PricingEngineTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        # --- Common foundational data ---
        cls.provider = Providers.objects.create(name="Test Carrier", provider_type="CARRIER")
        cls.agent_provider = Providers.objects.create(name="Test Agent", provider_type="AGENT")
        cls.station_pom = Stations.objects.create(iata="POM", city="Port Moresby", country="PG")
        cls.station_bne = Stations.objects.create(iata="BNE", city="Brisbane", country="AU")
        cls.audience = Audience.get_or_create_from_code("PNG_CUSTOMER_PREPAID")
        PricingPolicy.objects.create(
            audience=cls.audience.code,
            gst_applies=True,
            gst_pct=Decimal("10.00"),
        )
        CurrencyRates.objects.create(base_ccy="AUD", quote_ccy="PGK", rate="2.5")

        # --- Fee & Service Types ---
        cls.fee_freight = FeeTypes.objects.create(code="FREIGHT", description="Freight", basis="PER_KG")
        cls.fee_fuel = FeeTypes.objects.create(code="FUEL", description="Fuel Surcharge", basis="PER_KG")
        cls.fee_doc = FeeTypes.objects.create(code="DOC", description="Documentation", basis="PER_SHIPMENT")

        cls.svc_freight = Services.objects.create(code="AIR_FREIGHT", name="Air Freight", basis="PER_KG")
        cls.svc_fuel = Services.objects.create(code="FUEL_SURCHARGE", name="Fuel Surcharge", basis="PER_KG")
        cls.svc_doc = Services.objects.create(code="DOC_FEE", name="Documentation Fee", basis="PER_SHIPMENT")

        # --- BUY Rate Card ---
        cls.rc_buy = Ratecards.objects.create(
            provider=cls.provider, name="Test BUY Card", role="BUY", scope="INTERNATIONAL",
            direction="IMPORT", currency="AUD", audience=cls.audience, effective_date=now(),
            created_at=now(), updated_at=now(), meta={}
        )
        RatecardConfig.objects.create(ratecard=cls.rc_buy, dim_factor_kg_per_m3=167)
        RatecardFees.objects.create(ratecard=cls.rc_buy, fee_type=cls.fee_fuel, currency="AUD", amount="1.00", created_at=now(), applies_if={})
        RatecardFees.objects.create(ratecard=cls.rc_buy, fee_type=cls.fee_doc, currency="AUD", amount="50.00", created_at=now(), applies_if={})

        # --- SELL Rate Card ---
        cls.rc_sell = Ratecards.objects.create(
            provider=cls.agent_provider, name="Test SELL Menu", role="SELL", scope="INTERNATIONAL",
            direction="IMPORT", currency="PGK", audience=cls.audience, effective_date=now(),
            created_at=now(), updated_at=now(), meta={}
        )

        # --- Lane & Breaks ---
        cls.lane = Lanes.objects.create(ratecard=cls.rc_buy, origin=cls.station_bne, dest=cls.station_pom, is_direct=True)
        LaneBreaks.objects.create(lane=cls.lane, break_code="MIN", min_charge="200.00")
        LaneBreaks.objects.create(lane=cls.lane, break_code="N", per_kg="10.00")
        LaneBreaks.objects.create(lane=cls.lane, break_code="45", per_kg="8.00")
        LaneBreaks.objects.create(lane=cls.lane, break_code="100", per_kg="6.00")

        # --- Link BUY costs to SELL items ---
        # Pass-through
        sell_item_fuel = ServiceItems.objects.create(ratecard=cls.rc_sell, service=cls.svc_fuel, currency="PGK", tax_pct=10)
        SellCostLinksSimple.objects.create(sell_item=sell_item_fuel, buy_fee_code=cls.fee_fuel, mapping_type="PASS_THROUGH")
        # Cost-plus percentage
        sell_item_freight = ServiceItems.objects.create(ratecard=cls.rc_sell, service=cls.svc_freight, currency="PGK", tax_pct=10)
        SellCostLinksSimple.objects.create(sell_item=sell_item_freight, buy_fee_code=cls.fee_freight, mapping_type="COST_PLUS_PCT", mapping_value="0.20") # 20% margin
        # Cost-plus absolute
        sell_item_doc = ServiceItems.objects.create(ratecard=cls.rc_sell, service=cls.svc_doc, currency="PGK", tax_pct=10)
        SellCostLinksSimple.objects.create(sell_item=sell_item_doc, buy_fee_code=cls.fee_doc, mapping_type="COST_PLUS_ABS", mapping_value="25.00") # 25 PGK markup

    def test_piecewise_chargeable_rounding(self):
        dim_factor = Decimal("167")
        pieces = [Piece(weight_kg=Decimal("10.1"), length_cm=30, width_cm=30, height_cm=30)] # 10.1kg vs 4.509kg vol
        self.assertEqual(calculate_chargeable_weight_per_piece(pieces, dim_factor), Decimal("11"))

    def test_break_selection(self):
        # Test MIN enforcement (10kg * 10/kg = 100 AUD, but MIN is 200 AUD)
        payload = ShipmentInput(org_id=1, origin_iata="BNE", dest_iata="POM", pieces=[Piece(weight_kg=10)])
        result = compute_quote(payload)
        freight_buy = next(l for l in result.buy_lines if l.code == 'FREIGHT')
        self.assertEqual(freight_buy.extended.amount, d("200.00"))

        # Test 'N' rate (25kg * 10/kg = 250 AUD)
        payload = ShipmentInput(org_id=1, origin_iata="BNE", dest_iata="POM", pieces=[Piece(weight_kg=25)])
        result = compute_quote(payload)
        freight_buy = next(l for l in result.buy_lines if l.code == 'FREIGHT')
        self.assertEqual(freight_buy.extended.amount, d("250.00"))

        # Test '45KG' break (50kg * 8/kg = 400 AUD)
        payload = ShipmentInput(org_id=1, origin_iata="BNE", dest_iata="POM", pieces=[Piece(weight_kg=50)])
        result = compute_quote(payload)
        freight_buy = next(l for l in result.buy_lines if l.code == 'FREIGHT')
        self.assertEqual(freight_buy.extended.amount, d("400.00"))

    def test_fee_basis_normalization(self):
        self.assertEqual(_normalize_basis("PER KG"), "PER_KG")
        self.assertEqual(_normalize_basis("per-kg"), "PER_KG")
        self.assertEqual(_normalize_basis("KG"), "PER_KG")
        self.assertEqual(_normalize_basis("PER_SHIPMENT"), "PER_SHIPMENT")
        self.assertEqual(_normalize_basis(" per awb "), "PER_AWB")

    def test_sell_mapping_modes_and_gst(self):
        payload = ShipmentInput(org_id=1, origin_iata="BNE", dest_iata="POM", pieces=[Piece(weight_kg=100)])
        result = compute_quote(payload)

        # Freight: BUY is 100kg * 6/kg = 600 AUD. SELL is 20% margin.
        # 600 AUD * 2.5 FX = 1500 PGK. 1500 * 1.20 = 1800 PGK. With 10% GST = 1980 PGK
        freight_sell = next(l for l in result.sell_lines if l.code == 'AIR_FREIGHT')
        self.assertEqual(freight_sell.extended.amount, d("1980.00"))

        # Fuel: Pass-through. BUY is 100kg * 1/kg = 100 AUD. SELL is 100 AUD.
        # 100 AUD * 2.5 FX = 250 PGK. With 10% GST = 275 PGK
        fuel_sell = next(l for l in result.sell_lines if l.code == 'FUEL_SURCHARGE')
        self.assertEqual(fuel_sell.extended.amount, d("275.00"))

        # Doc Fee: Cost-plus-abs. BUY is 50 AUD. SELL is 50 AUD + 25 PGK.
        # 50 AUD * 2.5 FX = 125 PGK. 125 + 25 = 150 PGK. With 10% GST = 165 PGK
        doc_sell = next(l for l in result.sell_lines if l.code == 'DOC_FEE')
        self.assertEqual(doc_sell.extended.amount, d("165.00"))

    def test_final_total_rounding(self):
        # Use a custom ratecard to force a non-whole number total
        svc = Services.objects.create(code="ODD_FEE", name="Odd Fee", basis="PER_SHIPMENT")
        si = ServiceItems.objects.create(ratecard=self.rc_sell, service=svc, currency="PGK", tax_pct=0, amount="123.45")
        
        payload = ShipmentInput(org_id=1, origin_iata="BNE", dest_iata="POM", pieces=[Piece(weight_kg=1)])
        result = compute_quote(payload)
        # Total should round up to the next whole number
        self.assertGreater(result.totals['sell_total'].amount, d("123.45"))
        self.assertEqual(result.totals['sell_total'].amount % 1, 0)

    def test_manual_rate_trigger(self):
        # Set route to require manual rating
        route, _ = Routes.objects.get_or_create(origin_country="AU", dest_country="PG", shipment_type="IMPORT")
        route.requires_manual_rate = True
        route.save()
        RouteLegs.objects.get_or_create(route=route, sequence=1, origin=self.station_bne, dest=self.station_pom)

        payload = ShipmentInput(org_id=1, origin_iata="BNE", dest_iata="POM", pieces=[Piece(weight_kg=100)])
        result = compute_quote(payload)

        self.assertTrue(result.snapshot['manual_rate_required'])
        self.assertIn("Route flagged for manual rating", result.snapshot['manual_reasons'][0])

        # Cleanup
        route.requires_manual_rate = False
        route.save()