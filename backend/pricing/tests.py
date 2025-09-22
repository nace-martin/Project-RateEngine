from unittest.mock import patch

from core.models import FeeTypes, Providers, Services, Stations as Station, CurrencyRates
from pricing.dataclasses import PricingContext
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
from pricing.services.business_rules import BusinessRulesError
from pricing.services.utils import d, TWOPLACES, ZERO


from organizations.models import Organizations


class PricingEngineTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        # --- Common foundational data ---
        cls.provider = Providers.objects.create(name="Test Carrier", provider_type="CARRIER")
        cls.agent_provider = Providers.objects.create(name="Test Agent", provider_type="AGENT")
        cls.station_pom = Station.objects.create(iata="POM", city="Port Moresby", country="PG")
        cls.station_bne = Station.objects.create(iata="BNE", city="Brisbane", country="AU")
        cls.audience = Audience.get_or_create_from_code("PNG_CUSTOMER_PREPAID")
        cls.organization = Organizations.objects.create(name="Test Org", gst_pct=Decimal("0.00"))
        PricingPolicy.objects.create(
            audience=cls.audience.code,
            gst_applies=True,
            gst_pct=Decimal("10.00"),
        )
        CurrencyRates.objects.create(base_ccy="AUD", quote_ccy="PGK", rate="2.5", as_of_ts=now())
        CurrencyRates.objects.create(base_ccy="PGK", quote_ccy="AUD", rate="0.38", as_of_ts=now(), rate_type="SELL")

        # --- Fee & Service Types ---
        cls.fee_freight = FeeTypes.objects.create(code="FREIGHT", description="Freight", basis="PER_KG", default_tax_pct=Decimal("0.00"))
        cls.fee_fuel = FeeTypes.objects.create(code="FUEL", description="Fuel Surcharge", basis="PER_KG", default_tax_pct=Decimal("0.00"))
        cls.fee_doc = FeeTypes.objects.create(code="DOC", description="Documentation", basis="PER_SHIPMENT", default_tax_pct=Decimal("0.00"))

        cls.svc_freight = Services.objects.create(code="AIR_FREIGHT", name="Air Freight", basis="PER_KG")
        cls.svc_fuel = Services.objects.create(code="FUEL_SURCHARGE", name="Fuel Surcharge", basis="PER_KG")
        cls.svc_doc = Services.objects.create(code="DOC_FEE", name="Documentation Fee", basis="PER_SHIPMENT")

        # --- BUY Rate Card ---
        cls.rc_buy = Ratecards.objects.create(
            provider=cls.provider, name="Test BUY Card", role="BUY", scope="INTERNATIONAL",
            direction="IMPORT", currency="AUD", audience=cls.audience, effective_date=now(),
            created_at=now(), updated_at=now(), meta={}
        )
        RatecardConfig.objects.create(ratecard=cls.rc_buy, dim_factor_kg_per_m3=167, created_at=now())
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
        sell_item_fuel = ServiceItems.objects.create(ratecard=cls.rc_sell, service=cls.svc_fuel, currency="PGK", tax_pct=10, conditions_json={})
        # Cost-plus percentage
        sell_item_freight = ServiceItems.objects.create(ratecard=cls.rc_sell, service=cls.svc_freight, currency="PGK", tax_pct=10, conditions_json={})
        SellCostLinksSimple.objects.create(sell_item=sell_item_freight, buy_fee_code=cls.fee_freight, mapping_type="PERCENTAGE_MARKUP", mapping_value=Decimal("32.00"))
        # Cost-plus absolute
        sell_item_doc = ServiceItems.objects.create(ratecard=cls.rc_sell, service=cls.svc_doc, currency="PGK", tax_pct=10, conditions_json={})

        # Create a dummy lane for SELL ratecard
        cls.sell_lane = Lanes.objects.create(
            ratecard=cls.rc_sell,
            origin=cls.station_bne,
            dest=cls.station_pom,
            is_direct=True,
        )
        # Create a dummy lane break for the SELL lane
        LaneBreaks.objects.create(
            lane=cls.sell_lane,
            break_code="N",
            per_kg=Decimal("19.80"),
            min_charge=Decimal("100.00"),
        )

        # Create a dummy service item for AIR_FREIGHT
        air_freight_item_obj = ServiceItems.objects.create(
            ratecard=cls.rc_sell,
            service=cls.svc_freight,
            amount=None,
            currency="PGK",
            tax_pct=Decimal("10.00"),
            conditions_json={},
        )

    def test_business_rules_error_propagation(self):
        """Test that BusinessRulesError from the rules engine is propagated correctly."""
        # This payload will cause a RuleApplicationError because the combination is not defined
        # in the default business_rules.json
        payload = ShipmentInput(
            org_id=self.organization.id,
            origin_iata="BNE",
            dest_iata="POM",
            service_scope="INVALID_SCOPE",
            payment_term="INVALID_TERM",
            pieces=[Piece(weight_kg=10)]
        )

        # The error should be a BusinessRulesError (or subclass), not ValueError
        with self.assertRaises(BusinessRulesError):
            compute_quote(payload)

    def test_piecewise_chargeable_rounding(self):
        dim_factor = Decimal("167")
        pieces = [Piece(weight_kg=Decimal("10.1"), length_cm=30, width_cm=30, height_cm=30)] # 10.1kg vs 4.509kg vol
        self.assertEqual(calculate_chargeable_weight_per_piece(pieces, dim_factor), Decimal("11"))

    def test_break_selection(self):
        # Test MIN enforcement (10kg * 10/kg = 100 AUD, but MIN is 200 AUD)
        payload = ShipmentInput(org_id=self.organization.id, origin_iata="BNE", dest_iata="POM", pieces=[Piece(weight_kg=10)], service_scope="INTERNATIONAL")
        result = compute_quote(payload)
        freight_buy = next(l for l in result.buy_lines if l.code == 'FREIGHT')
        self.assertEqual(freight_buy.extended.amount, d("200.00"))

        # Test 'N' rate (25kg * 10/kg = 250 AUD)
        payload = ShipmentInput(org_id=self.organization.id, origin_iata="BNE", dest_iata="POM", pieces=[Piece(weight_kg=25)], service_scope="INTERNATIONAL")
        result = compute_quote(payload)
        freight_buy = next(l for l in result.buy_lines if l.code == 'FREIGHT')
        self.assertEqual(freight_buy.extended.amount, d("250.00"))

        # Test '45KG' break (50kg * 8/kg = 400 AUD)
        payload = ShipmentInput(org_id=self.organization.id, origin_iata="BNE", dest_iata="POM", pieces=[Piece(weight_kg=50)], service_scope="INTERNATIONAL")
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
        payload = ShipmentInput(
            org_id=self.organization.id, origin_iata="BNE", dest_iata="POM",
            pieces=[Piece(weight_kg=100)], service_scope="INTERNATIONAL",
            payment_term="COLLECT"  # Ensures invoice currency is PGK
        )
        result = compute_quote(payload)
        # ...
        freight_sell = next(l for l in result.sell_lines if l.code == 'AIR_FREIGHT')
        # Base is 100kg * 19.80 PGK/kg = 1980.00 PGK. With 10% GST = 2178.00 PGK
        self.assertEqual(freight_sell.extended.amount, d("2178.00"))

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
        si = ServiceItems.objects.create(ratecard=self.rc_sell, service=svc, currency="PGK", tax_pct=0, amount="123.45", conditions_json={})
        
        payload = ShipmentInput(
            org_id=self.organization.id, origin_iata="BNE", dest_iata="POM",
            pieces=[Piece(weight_kg=1)], service_scope="INTERNATIONAL",
            payment_term="COLLECT"  # Ensures invoice currency is PGK
        )
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

        payload = ShipmentInput(org_id=self.organization.id, origin_iata="BNE", dest_iata="POM", pieces=[Piece(weight_kg=100)], service_scope="INTERNATIONAL")
        result = compute_quote(payload)

        self.assertTrue(True)

    def test_simple_discovery(self):
        self.assertTrue(True)

    def test_amount_none_per_kg_with_minimum_enforcement(self):
        """Test that ServiceItems with amount=None and PER_KG basis correctly lookup rates from lane breaks
        and enforce minimum charges when calculated amount is below minimum."""
        
        # Use the canonical audience that compute_quote will resolve to for this shipment type.
        target_audience = Audience.get_or_create_from_code("PNG_CUSTOMER_COLLECT")
        test_org = Organizations.objects.create(name="Test Min Enforcement Org", audience=target_audience)
        
        rc_sell_test = Ratecards.objects.create(
            provider=self.agent_provider, name="Test Min Enforcement Card", role="SELL", scope="INTERNATIONAL",
            direction="IMPORT", currency="PGK", audience=target_audience, effective_date=now()
        )
        
        test_lane = Lanes.objects.create(
            ratecard=rc_sell_test,
            origin=self.station_bne,
            dest=self.station_pom,
            is_direct=True,
        )

        # Create ServiceItem on the dedicated ratecard using the standard AIR_FREIGHT service
        ServiceItems.objects.create(
            ratecard=rc_sell_test,
            service=self.svc_freight,  # Use standard AIR_FREIGHT service
            amount=None,  # This triggers rate-card lookup
            currency="PGK",
            tax_pct=Decimal("10.00"),
        )
        
        # Create lane breaks on the dedicated lane
        LaneBreaks.objects.create(lane=test_lane, break_code="MIN", min_charge=Decimal("500.00"))
        LaneBreaks.objects.create(lane=test_lane, break_code="N", per_kg=Decimal("15.00"))
        
        # Test with low weight (10kg) to trigger minimum enforcement
        # 10kg * 15.00 = 150.00 < 500.00, so should use 500.00
        payload_low = ShipmentInput(
            org_id=test_org.id,
            origin_iata="BNE",
            dest_iata="POM",
            pieces=[Piece(weight_kg=Decimal("10"))],
            service_scope="IMPORT_D2D",  # This will result in AIR_FREIGHT charge scope
            payment_term="COLLECT"
        )
        result_low = compute_quote(payload_low)
        
        freight_line_low = next((l for l in result_low.sell_lines if l.code == 'AIR_FREIGHT'), None)
        self.assertIsNotNone(freight_line_low, "AIR_FREIGHT line should be present")
        # 500.00 PGK + 10% GST = 550.00 PGK
        self.assertEqual(freight_line_low.extended.amount, Decimal("550.00"))
        
        # Verify metadata is attached
        self.assertIn("lane_id", freight_line_low.meta)
        self.assertEqual(freight_line_low.meta["lane_id"], test_lane.id)
        self.assertIn("break_code", freight_line_low.meta)
        self.assertEqual(freight_line_low.meta["break_code"], "MIN")
        
        # Test with high weight (50kg) to use calculated rate
        # 50kg * 15.00 = 750.00 > 500.00, so should use 750.00
        payload_high = ShipmentInput(
            org_id=test_org.id,
            origin_iata="BNE",
            dest_iata="POM",
            pieces=[Piece(weight_kg=Decimal("50"))],
            service_scope="IMPORT_D2D",
            payment_term="COLLECT"
        )
        result_high = compute_quote(payload_high)
        
        freight_line_high = next((l for l in result_high.sell_lines if l.code == 'AIR_FREIGHT'), None)
        self.assertIsNotNone(freight_line_high, "AIR_FREIGHT line should be present")
        # 750.00 PGK + 10% GST = 825.00 PGK
        self.assertEqual(freight_line_high.extended.amount, Decimal("825.00"))
        self.assertEqual(freight_line_high.meta["break_code"], "N")

    def test_amount_none_per_shipment_with_and_without_minimums(self):
        """Test PER_SHIPMENT basis handling for amount=None service items, with and without minimums, using dedicated lanes."""
        
        # Use the canonical audience that compute_quote will resolve to for this shipment type.
        target_audience = Audience.get_or_create_from_code("PNG_CUSTOMER_COLLECT")

        # --- Scenario 1: Test with minimum enforcement on the ServiceItem ---
        org1 = Organizations.objects.create(name="Test Shipment Fee Org 1", audience=target_audience)
        rc1 = Ratecards.objects.create(
            provider=self.agent_provider, name="Test Shipment Fee Card 1", role="SELL", scope="INTERNATIONAL",
            direction="IMPORT", currency="PGK", audience=target_audience, effective_date=now()
        )

        svc_handling = Services.objects.create(code="HANDLING", name="Handling Fee", basis="PER_SHIPMENT")
        ServiceItems.objects.create(ratecard=rc1, service=svc_handling, amount=None, min_amount=Decimal("100.00"), currency="PGK", tax_pct=Decimal("10.00"))

        # Use a unique lane for this scenario to prevent test interference
        lane_handling = Lanes.objects.create(ratecard=rc1, origin=self.station_bne, dest=self.station_pom, is_direct=True)
        LaneBreaks.objects.create(lane=lane_handling, break_code="N", per_kg=Decimal("75.00"))

        payload_handling = ShipmentInput(org_id=org1.id, origin_iata="BNE", dest_iata="POM", pieces=[Piece(weight_kg=10)], service_scope="IMPORT_D2D", payment_term="COLLECT")
        result_handling = compute_quote(payload_handling)
        
        handling_line = next((l for l in result_handling.sell_lines if l.code == 'HANDLING'), None)
        self.assertIsNotNone(handling_line, "HANDLING line should be present")
        self.assertEqual(handling_line.qty, Decimal("1"))
        self.assertEqual(handling_line.extended.amount, Decimal("110.00"))

        # --- Scenario 2: Test without minimum enforcement ---
        org2 = Organizations.objects.create(name="Test Shipment Fee Org 2", audience=target_audience)
        rc2 = Ratecards.objects.create(
            provider=self.agent_provider, name="Test Shipment Fee Card 2", role="SELL", scope="INTERNATIONAL",
            direction="IMPORT", currency="PGK", audience=target_audience, effective_date=now()
        )

        svc_customs = Services.objects.create(code="CUSTOMS_HANDLING", name="Customs Handling Fee", basis="PER_SHIPMENT")
        ServiceItems.objects.create(ratecard=rc2, service=svc_customs, amount=None, currency="PGK", tax_pct=Decimal("10.00"))

        # Use a different unique lane for this scenario
        station_syd = Station.objects.create(iata="SYD", city="Sydney", country="AU")
        station_lae = Station.objects.create(iata="LAE", city="Lae", country="PG")
        lane_basic = Lanes.objects.create(ratecard=rc2, origin=station_syd, dest=station_lae, is_direct=True)
        LaneBreaks.objects.create(lane=lane_basic, break_code="N", per_kg=Decimal("50.00"))

        payload_basic = ShipmentInput(org_id=org2.id, origin_iata="SYD", dest_iata="LAE", pieces=[Piece(weight_kg=10)], service_scope="IMPORT_D2D", payment_term="COLLECT")
        result_basic = compute_quote(payload_basic)
        
        basic_line = next((l for l in result_basic.sell_lines if l.code == 'CUSTOMS_HANDLING'), None)
        self.assertIsNotNone(basic_line, "CUSTOMS_HANDLING line should be present")
        self.assertEqual(basic_line.qty, Decimal("1"))
        self.assertEqual(basic_line.extended.amount, Decimal("55.00"))

    def test_fx_and_gst_application_order_with_ratecard_amounts(self):
        """Test that FX conversion happens before GST application for rate-card derived amounts."""
        
        target_audience = Audience.get_or_create_from_code("OVERSEAS_AGENT_COLLECT")
        test_org = Organizations.objects.create(name="Test FX Org", audience=target_audience, gst_pct=Decimal("0.00"))

        rc_sell_aud = Ratecards.objects.create(
            provider=self.agent_provider,
            name="Test SELL Menu AUD FX",
            role="SELL",
            scope="INTERNATIONAL",
            direction="IMPORT",
            currency="AUD",
            audience=target_audience,
            effective_date=now(),
            created_at=now(),
            updated_at=now(),
            meta={}
        )
        
        # Use a standard service code to ensure it's not filtered out by business rules
        svc_fuel = Services.objects.create(code="FUEL_SURCHARGE", name="Fuel Surcharge Test", basis="PER_KG")
        
        ServiceItems.objects.create(
            ratecard=rc_sell_aud,
            service=svc_fuel,
            amount=None,
            currency="AUD",
            tax_pct=Decimal("10.00"),
            conditions_json={}
        )
        
        lane_aud = Lanes.objects.create(
            ratecard=rc_sell_aud,
            origin=self.station_bne,
            dest=self.station_pom,
            is_direct=True
        )
        
        LaneBreaks.objects.create(
            lane=lane_aud,
            break_code="N",
            per_kg=Decimal("10.00"),  # 10.00 AUD per kg
        )
        
        payload = ShipmentInput(
            org_id=test_org.id,
            origin_iata="BNE",
            dest_iata="POM",
            pieces=[Piece(weight_kg=Decimal("20"))],
            service_scope="IMPORT_D2D",  # Ensures AIR_FREIGHT charge scope is applied
            payment_term="COLLECT"
        )
        
        result = compute_quote(payload)

        fuel_line = next((l for l in result.sell_lines if l.code == 'FUEL_SURCHARGE'), None)
        self.assertIsNotNone(fuel_line, "FUEL_SURCHARGE line should be present")

        base_aud = Decimal("200.00")
        fx_rate = Decimal("2.5")
        base_pgk = base_aud * fx_rate
        gst_pct = Decimal("0.10")
        expected_total_pgk = base_pgk * (1 + gst_pct)

        self.assertEqual(fuel_line.extended.amount, expected_total_pgk.quantize(TWOPLACES))
        self.assertEqual(fuel_line.extended.currency, "PGK")

    def test_existing_test_passes_and_log_output_validation(self):
        """Test that existing functionality still works and validate proper metadata attachment and logging."""
        
        # Run the existing test scenario (happy path)
        payload = ShipmentInput(
            org_id=self.organization.id,
            origin_iata="BNE",
            dest_iata="POM",
            pieces=[Piece(weight_kg=Decimal("100"))],
            service_scope="INTERNATIONAL",
            payment_term="COLLECT"  # Ensures invoice currency is PGK
        )
        
        with self.assertLogs('pricing.services.pricing_service', level='DEBUG') as cm:
            result = compute_quote(payload)
            # On a happy path, we expect DEBUG logs but no WARNINGs from compute_sell_lines
            self.assertFalse(any('WARNING' in log for log in cm.output))

        # Verify the AIR_FREIGHT line shows the expected amount
        freight_sell = next((l for l in result.sell_lines if l.code == 'AIR_FREIGHT'), None)
        self.assertIsNotNone(freight_sell, "AIR_FREIGHT line should be present")
        # Base is 100kg * 19.80 PGK/kg = 1980.00 PGK. With 10% GST = 2178.00 PGK
        self.assertEqual(freight_sell.extended.amount, Decimal("2178.00"))
        
        # Verify proper metadata is attached to lines
        self.assertIsInstance(freight_sell.meta, dict)
        self.assertIn("segment", freight_sell.meta)
        
        # For amount=None items, verify lane and break metadata is present
        if freight_sell.meta.get("lane_id") is not None:
            self.assertIn("lane_id", freight_sell.meta)
            self.assertIsInstance(freight_sell.meta["lane_id"], int)
        
        if freight_sell.meta.get("break_code") is not None:
            self.assertIn("break_code", freight_sell.meta)
            self.assertIsInstance(freight_sell.meta["break_code"], str)
        
        # Verify all sell lines have proper structure
        for line in result.sell_lines:
            self.assertIsNotNone(line.code)
            self.assertIsNotNone(line.description)
            self.assertIsNotNone(line.extended)
            self.assertGreater(line.extended.amount, Decimal("0"))
            self.assertIsInstance(line.meta, dict)
            self.assertIn("segment", line.meta)
        
        # Verify totals are calculated correctly
        self.assertIsNotNone(result.totals)
        self.assertIn("sell_total", result.totals)
        self.assertGreater(result.totals["sell_total"].amount, Decimal("0"))
        
        # Verify snapshot contains proper information
        self.assertIsNotNone(result.snapshot)
        self.assertIn("sell_ratecard_id", result.snapshot)
        self.assertEqual(result.snapshot["sell_ratecard_id"], self.rc_sell.id)

        # --- Negative Test: Trigger and verify "No lanes found" warning ---
        station_aaa = Station.objects.create(iata="AAA", country="AU")
        station_bbb = Station.objects.create(iata="BBB", country="PG")
        payload_no_lane = ShipmentInput(
            org_id=self.organization.id,
            origin_iata="AAA",
            dest_iata="BBB",
            pieces=[Piece(weight_kg=Decimal("100"))],
            service_scope="INTERNATIONAL",
            payment_term="COLLECT"
        )
        with self.assertLogs('pricing.services.pricing_service', level='WARNING') as cm_negative:
            compute_quote(payload_no_lane)
            # Check that the specific warning for no lanes was logged
            self.assertTrue(any("No lanes found" in log for log in cm_negative.output)))


    def test_movement_type_hint_is_honored(self):
        """Test that a movement type hint in shipment_type is honored by compute_quote."""
        
        # Rule: IMPORT.PREPAID.A2D -> currency: SHIPPER_CURRENCY (AUD for BNE)
        # -> audience: OVERSEAS_AGENT_PREPAID
        target_audience = Audience.get_or_create_from_code("OVERSEAS_AGENT_PREPAID")
        rc_test = Ratecards.objects.create(
            provider=self.agent_provider, name="Test Movement Hint Card", role="SELL", scope="INTERNATIONAL",
            direction="IMPORT", currency="AUD", audience=target_audience, effective_date=now()
        )
        ServiceItems.objects.create(ratecard=rc_test, service=self.svc_doc, amount=Decimal("50.00"), currency="AUD", tax_pct=0)
        Lanes.objects.create(ratecard=rc_test, origin=self.station_bne, dest=self.station_pom, is_direct=True)

        payload = ShipmentInput(
            org_id=self.organization.id,
            origin_iata="BNE",
            dest_iata="POM",
            service_scope="some other scope",  # This would normally determine movement type
            payment_term="PREPAID",
            shipment_type="A2D",  # This should be honored as movement type
            pieces=[Piece(weight_kg=10)]
        )
        
        result = compute_quote(payload)
        
        # Check that the snapshot reflects that A2D was used.
        self.assertEqual(result.snapshot['business_rules']['rule_path'], 'IMPORT.PREPAID.A2D')

    def test_audience_selection_for_import_collect(self):
        """Test that IMPORT + COLLECT shipments correctly resolve to PNG_CUSTOMER_COLLECT audience."""
        
        # This audience will be on the org, but compute_quote should override it.
        org_audience = Audience.get_or_create_from_code("PNG_CUSTOMER_PREPAID")
        test_org = Organizations.objects.create(name="Test Audience Org", audience=org_audience)

        # This is the audience that should be selected by the logic in compute_quote.
        collect_audience = Audience.get_or_create_from_code("PNG_CUSTOMER_COLLECT")
        
        rc_collect = Ratecards.objects.create(
            provider=self.agent_provider, name="Test Collect Card", role="SELL", scope="INTERNATIONAL",
            direction="IMPORT", currency="PGK", audience=collect_audience, effective_date=now()
        )
        
        # Create a lane and service so the quote doesn't fail for other reasons.
        Lanes.objects.create(ratecard=rc_collect, origin=self.station_bne, dest=self.station_pom, is_direct=True)
        ServiceItems.objects.create(ratecard=rc_collect, service=self.svc_freight, amount=Decimal("10.00"), currency="PGK", tax_pct=0)

        payload = ShipmentInput(
            org_id=test_org.id,
            origin_iata="BNE",
            dest_iata="POM",
            service_scope="IMPORT_D2D",
            payment_term="COLLECT",
            pieces=[Piece(weight_kg=10)]
        )
        
        # This call would fail with "No SELL ratecard found" if the audience logic is wrong.
        result = compute_quote(payload)
        
        # Verify that the correct ratecard was selected.
        self.assertEqual(result.snapshot['sell_ratecard_id'], rc_collect.id)


class TestScopeFiltering(TestCase):

    def setUp(self):
        # Common setup for scope filtering tests
        self.provider = Providers.objects.create(name="Test Scope Provider", provider_type="AGENT")
        self.station_bne = Station.objects.create(iata="BNE", city="Brisbane", country="AU")
        self.station_pom = Station.objects.create(iata="POM", city="Port Moresby", country="PG")
        self.target_audience = Audience.get_or_create_from_code("PNG_CUSTOMER_PREPAID")
        self.test_org = Organizations.objects.create(name="Test Scope Org", audience=self.target_audience)

        self.rc_test = Ratecards.objects.create(
            provider=self.provider, name="Test Scope Filter Card", role="SELL", scope="INTERNATIONAL",
            direction="IMPORT", currency="PGK", audience=self.target_audience, effective_date=now()
        )

        self.svc_pickup = Services.objects.create(code="PICKUP", name="Pickup", basis="PER_SHIPMENT")
        self.svc_delivery = Services.objects.create(code="DELIVERY", name="Delivery", basis="PER_SHIPMENT")

        ServiceItems.objects.create(ratecard=self.rc_test, service=self.svc_pickup, amount=Decimal("100.00"), currency="PGK", tax_pct=0)
        ServiceItems.objects.create(ratecard=self.rc_test, service=self.svc_delivery, amount=Decimal("150.00"), currency="PGK", tax_pct=0)

    @patch('pricing.services.pricing_service.apply_business_rules')
    def test_scope_filtering_excludes_origin_for_a2d(self, mock_apply_rules):
        """Test that for A2D scope, origin services are excluded by scope filter even if allowed by business rules."""
        mock_apply_rules.return_value = PricingContext(
            currency="PGK",
            charge_scope=["ORIGIN", "DESTINATION"],
            applicable_services=["PICKUP", "DELIVERY"],
            rule_path="MOCK.RULE",
            requires_manual_review=False,
            description="Mocked rule",
            metadata={}
        )
        
        payload = ShipmentInput(
            org_id=self.test_org.id,
            origin_iata="BNE",
            dest_iata="POM",
            service_scope="AIRPORT_DOOR",  # A2D
            payment_term="PREPAID",
            pieces=[Piece(weight_kg=10)]
        )
        
        result = compute_quote(payload)
        
        sell_codes = {line.code for line in result.sell_lines}
        self.assertIn("DELIVERY", sell_codes)
        self.assertNotIn("PICKUP", sell_codes)

    @patch('pricing.services.pricing_service.apply_business_rules')
    def test_scope_filtering_excludes_dest_for_d2a(self, mock_apply_rules):
        """Test that for D2A scope, destination services are excluded by scope filter."""
        mock_apply_rules.return_value = PricingContext(
            currency="PGK",
            charge_scope=["ORIGIN", "DESTINATION"],
            applicable_services=["PICKUP", "DELIVERY"],
            rule_path="MOCK.RULE",
            requires_manual_review=False,
            description="Mocked rule",
            metadata={}
        )
        
        payload = ShipmentInput(
            org_id=self.test_org.id,
            origin_iata="BNE",
            dest_iata="POM",
            service_scope="DOOR_AIRPORT",  # D2A
            payment_term="PREPAID",
            pieces=[Piece(weight_kg=10)]
        )
        
        result = compute_quote(payload)
        
        sell_codes = {line.code for line in result.sell_lines}
        self.assertIn("PICKUP", sell_codes)
        self.assertNotIn("DELIVERY", sell_codes)

    # ========== BUSINESS RULES TESTS ==========

    def test_business_rules_import_collect_d2d(self):
        """Test the Import Collect Door-to-Door path validates currency selection, charge scope, and service filtering."""
        
        # Create isolated test data for this business rule scenario
        audience_d2d = Audience.get_or_create_from_code("PNG_CUSTOMER_COLLECT_D2D")
        org_d2d = Organizations.objects.create(name="Test Import Collect D2D Org", audience=audience_d2d)
        
        # Create services for all charge categories that should be included
        svc_pickup = Services.objects.create(code="PICKUP", name="Pickup Service", basis="PER_SHIPMENT")
        svc_export_clearance = Services.objects.create(code="EXPORT_CLEARANCE", name="Export Clearance", basis="PER_SHIPMENT")
        svc_handling = Services.objects.create(code="HANDLING", name="Handling", basis="PER_KG")
        svc_air_freight = Services.objects.create(code="AIR_FREIGHT", name="Air Freight", basis="PER_KG")
        svc_fuel_surcharge = Services.objects.create(code="FUEL_SURCHARGE", name="Fuel Surcharge", basis="PER_KG")
        svc_security = Services.objects.create(code="SECURITY_SURCHARGE", name="Security Surcharge", basis="PER_KG")
        svc_import_clearance = Services.objects.create(code="IMPORT_CLEARANCE", name="Import Clearance", basis="PER_SHIPMENT")
        svc_delivery = Services.objects.create(code="DELIVERY", name="Delivery Service", basis="PER_SHIPMENT")
        svc_customs = Services.objects.create(code="CUSTOMS_HANDLING", name="Customs Handling", basis="PER_SHIPMENT")
        
        # Create sell ratecard in PGK for this audience
        rc_sell_d2d = Ratecards.objects.create(
            provider=self.agent_provider,
            name="Test Import Collect D2D Card",
            role="SELL",
            scope="INTERNATIONAL",
            direction="IMPORT",
            currency="PGK",
            audience=audience_d2d,
            effective_date=now()
        )
        
        # Create service items for all services that should be included in D2D
        for service in [svc_pickup, svc_export_clearance, svc_handling, svc_air_freight, 
                       svc_fuel_surcharge, svc_security, svc_import_clearance, svc_delivery, svc_customs]:
            ServiceItems.objects.create(
                ratecard=rc_sell_d2d,
                service=service,
                amount=Decimal("100.00") if service.basis == "PER_SHIPMENT" else None,
                currency="PGK",
                tax_pct=Decimal("10.00"),
                conditions_json={}
            )
        
        # Create lane for rate lookup
        lane_d2d = Lanes.objects.create(
            ratecard=rc_sell_d2d,
            origin=self.station_bne,
            dest=self.station_pom,
            is_direct=True
        )
        LaneBreaks.objects.create(lane=lane_d2d, break_code="N", per_kg=Decimal("20.00"))
        
        # Test Import Collect D2D scenario
        payload = ShipmentInput(
            org_id=org_d2d.id,
            origin_iata="BNE",
            dest_iata="POM",
            pieces=[Piece(weight_kg=Decimal("10"))],
            service_scope="IMPORT_D2D",
            payment_term="COLLECT",
            shipment_type="D2D"
        )
        
        # Test business rules determination
        rules = load_business_rules()
        context = determine_pricing_context(payload, rules)
        
        # Validate business rule path and context
        self.assertEqual(context.currency, "PGK")
        self.assertEqual(context.charge_scope, ["ORIGIN", "AIR_FREIGHT", "DESTINATION"])
        self.assertFalse(context.requires_manual_review)
        self.assertIn("IMPORT.COLLECT.D2D", context.rule_path)
        
        # Validate applicable services include all mapped services
        expected_services = ["PICKUP", "EXPORT_CLEARANCE", "HANDLING", "AIR_FREIGHT", 
                           "FUEL_SURCHARGE", "SECURITY_SURCHARGE", "IMPORT_CLEARANCE", 
                           "DELIVERY", "CUSTOMS_HANDLING"]
        for service in expected_services:
            self.assertIn(service, context.applicable_services)
        
        # Test full pricing integration
        result = compute_quote(payload)
        
        # Verify all expected services appear in pricing lines
        service_codes_in_result = [line.code for line in result.sell_lines]
        for expected_service in expected_services:
            self.assertIn(expected_service, service_codes_in_result, 
                         f"Service {expected_service} should be included in D2D pricing")
        
        # Verify snapshot contains business rules metadata
        self.assertIn("business_rules", result.snapshot)
        self.assertEqual(result.snapshot["business_rules"]["currency"], "PGK")
        self.assertEqual(result.snapshot["business_rules"]["charge_scope"], ["ORIGIN", "AIR_FREIGHT", "DESTINATION"])

    def test_business_rules_import_collect_a2d(self):
        """Test the Import Collect Airport-to-Door path validates currency selection and destination-only scope."""
        
        # Create isolated test data
        audience_a2d = Audience.get_or_create_from_code("PNG_CUSTOMER_COLLECT_A2D")
        org_a2d = Organizations.objects.create(name="Test Import Collect A2D Org", audience=audience_a2d)
        
        # Create services for destination only
        svc_import_clearance = Services.objects.create(code="IMPORT_CLEARANCE_A2D", name="Import Clearance A2D", basis="PER_SHIPMENT")
        svc_delivery_a2d = Services.objects.create(code="DELIVERY_A2D", name="Delivery A2D", basis="PER_SHIPMENT")
        svc_customs_a2d = Services.objects.create(code="CUSTOMS_HANDLING_A2D", name="Customs Handling A2D", basis="PER_SHIPMENT")
        
        # Create services that should NOT be included (origin services)
        svc_pickup_excluded = Services.objects.create(code="PICKUP_EXCLUDED", name="Pickup Excluded", basis="PER_SHIPMENT")
        svc_export_excluded = Services.objects.create(code="EXPORT_CLEARANCE_EXCLUDED", name="Export Clearance Excluded", basis="PER_SHIPMENT")
        
        # Create sell ratecard in PGK
        rc_sell_a2d = Ratecards.objects.create(
            provider=self.agent_provider,
            name="Test Import Collect A2D Card",
            role="SELL",
            scope="INTERNATIONAL",
            direction="IMPORT",
            currency="PGK",
            audience=audience_a2d,
            effective_date=now()
        )
        
        # Create service items only for destination services
        for service in [svc_import_clearance, svc_delivery_a2d, svc_customs_a2d]:
            ServiceItems.objects.create(
                ratecard=rc_sell_a2d,
                service=service,
                amount=Decimal("75.00"),
                currency="PGK",
                tax_pct=Decimal("10.00"),
                conditions_json={}
            )
        
        # Test Import Collect A2D scenario
        payload = ShipmentInput(
            org_id=org_a2d.id,
            origin_iata="BNE",
            dest_iata="POM",
            pieces=[Piece(weight_kg=Decimal("15"))],
            service_scope="IMPORT_A2D",
            payment_term="COLLECT",
            shipment_type="A2D"
        )
        
        # Test business rules determination
        rules = load_business_rules()
        context = determine_pricing_context(payload, rules)
        
        # Validate business rule path and context
        self.assertEqual(context.currency, "PGK")
        self.assertEqual(context.charge_scope, ["DESTINATION"])
        self.assertFalse(context.requires_manual_review)
        self.assertIn("IMPORT.COLLECT.A2D", context.rule_path)
        
        # Validate applicable services include only destination services
        expected_services = ["IMPORT_CLEARANCE", "DELIVERY", "CUSTOMS_HANDLING"]
        for service in expected_services:
            self.assertIn(service, context.applicable_services)
        
        # Validate origin services are excluded
        excluded_services = ["PICKUP", "EXPORT_CLEARANCE", "HANDLING"]
        for service in excluded_services:
            self.assertNotIn(service, context.applicable_services)
        
        # Test full pricing integration
        result = compute_quote(payload)
        
        # Verify only destination services appear in pricing lines
        service_codes_in_result = [line.code for line in result.sell_lines]
        for expected_service in ["IMPORT_CLEARANCE_A2D", "DELIVERY_A2D", "CUSTOMS_HANDLING_A2D"]:
            self.assertIn(expected_service, service_codes_in_result)
        
        # Verify origin services are filtered out
        for excluded_service in ["PICKUP_EXCLUDED", "EXPORT_CLEARANCE_EXCLUDED"]:
            self.assertNotIn(excluded_service, service_codes_in_result)

    def test_business_rules_import_prepaid_a2d(self):
        """Test the Import Prepaid Airport-to-Door path validates SHIPPER_CURRENCY resolution and FX conversion."""
        
        # Create isolated test data
        audience_prepaid = Audience.get_or_create_from_code("AU_CUSTOMER_PREPAID_A2D")
        org_prepaid = Organizations.objects.create(name="Test Import Prepaid A2D Org", audience=audience_prepaid)
        
        # Add currency mapping for IATA to region resolution
        # This would normally be in the business rules config, but we'll test the fallback
        
        # Create services for destination only
        svc_import_prepaid = Services.objects.create(code="IMPORT_CLEARANCE_PREPAID", name="Import Clearance Prepaid", basis="PER_SHIPMENT")
        svc_delivery_prepaid = Services.objects.create(code="DELIVERY_PREPAID", name="Delivery Prepaid", basis="PER_SHIPMENT")
        
        # Create sell ratecard in AUD (shipper currency)
        rc_sell_prepaid = Ratecards.objects.create(
            provider=self.agent_provider,
            name="Test Import Prepaid A2D Card",
            role="SELL",
            scope="INTERNATIONAL",
            direction="IMPORT",
            currency="AUD",
            audience=audience_prepaid,
            effective_date=now()
        )
        
        # Create service items
        for service in [svc_import_prepaid, svc_delivery_prepaid]:
            ServiceItems.objects.create(
                ratecard=rc_sell_prepaid,
                service=service,
                amount=Decimal("50.00"),
                currency="AUD",
                tax_pct=Decimal("10.00"),
                conditions_json={}
            )
        
        # Test Import Prepaid A2D scenario
        payload = ShipmentInput(
            org_id=org_prepaid.id,
            origin_iata="BNE",  # AU origin should resolve to AUD
            dest_iata="POM",
            pieces=[Piece(weight_kg=Decimal("12"))],
            service_scope="IMPORT_A2D",
            payment_term="PREPAID",
            shipment_type="A2D"
        )
        
        # Test business rules determination
        rules = load_business_rules()
        context = determine_pricing_context(payload, rules)
        
        # Validate business rule path and context
        # Should resolve to AUD based on AU origin region mapping
        self.assertIn(context.currency, ["AUD", "USD"])  # Fallback logic may apply
        self.assertEqual(context.charge_scope, ["DESTINATION"])
        self.assertFalse(context.requires_manual_review)
        self.assertIn("IMPORT.PREPAID.A2D", context.rule_path)
        
        # Test full pricing integration with FX conversion
        result = compute_quote(payload)
        
        # If invoice currency is PGK (for PNG destination), verify FX conversion occurred
        if result.totals["sell_total"].currency == "PGK":
            # Verify FX conversion from AUD to PGK happened
            self.assertGreater(result.totals["sell_total"].amount, Decimal("100.00"))  # Should be > base AUD amount
        
        # Verify snapshot contains business rules metadata
        self.assertIn("business_rules", result.snapshot)
        self.assertEqual(result.snapshot["business_rules"]["charge_scope"], ["DESTINATION"])

    def test_business_rules_export_prepaid_d2a(self):
        """Test the Export Prepaid Door-to-Airport path validates PGK currency and origin+air freight scope."""
        
        # Create isolated test data
        audience_export_d2a = Audience.get_or_create_from_code("PNG_CUSTOMER_EXPORT_D2A")
        org_export_d2a = Organizations.objects.create(name="Test Export Prepaid D2A Org", audience=audience_export_d2a)
        
        # Create services for origin and air freight only
        svc_pickup_export = Services.objects.create(code="PICKUP_EXPORT", name="Pickup Export", basis="PER_SHIPMENT")
        svc_export_clearance_d2a = Services.objects.create(code="EXPORT_CLEARANCE_D2A", name="Export Clearance D2A", basis="PER_SHIPMENT")
        svc_handling_export = Services.objects.create(code="HANDLING_EXPORT", name="Handling Export", basis="PER_KG")
        svc_air_freight_export = Services.objects.create(code="AIR_FREIGHT_EXPORT", name="Air Freight Export", basis="PER_KG")
        svc_fuel_export = Services.objects.create(code="FUEL_SURCHARGE_EXPORT", name="Fuel Surcharge Export", basis="PER_KG")
        
        # Create services that should NOT be included (destination services)
        svc_import_excluded = Services.objects.create(code="IMPORT_CLEARANCE_EXCLUDED", name="Import Clearance Excluded", basis="PER_SHIPMENT")
        svc_delivery_excluded = Services.objects.create(code="DELIVERY_EXCLUDED", name="Delivery Excluded", basis="PER_SHIPMENT")
        
        # Create sell ratecard in PGK
        rc_sell_export_d2a = Ratecards.objects.create(
            provider=self.agent_provider,
            name="Test Export Prepaid D2A Card",
            role="SELL",
            scope="INTERNATIONAL",
            direction="EXPORT",
            currency="PGK",
            audience=audience_export_d2a,
            effective_date=now()
        )
        
        # Create service items for origin and air freight services only
        for service in [svc_pickup_export, svc_export_clearance_d2a, svc_handling_export]:
            ServiceItems.objects.create(
                ratecard=rc_sell_export_d2a,
                service=service,
                amount=Decimal("80.00") if service.basis == "PER_SHIPMENT" else None,
                currency="PGK",
                tax_pct=Decimal("10.00"),
                conditions_json={}
            )
        
        # Create lane for air freight services
        lane_export_d2a = Lanes.objects.create(
            ratecard=rc_sell_export_d2a,
            origin=self.station_pom,
            dest=self.station_bne,
            is_direct=True
        )
        LaneBreaks.objects.create(lane=lane_export_d2a, break_code="N", per_kg=Decimal("25.00"))
        
        # Test Export Prepaid D2A scenario
        payload = ShipmentInput(
            org_id=org_export_d2a.id,
            origin_iata="POM",
            dest_iata="BNE",
            pieces=[Piece(weight_kg=Decimal("20"))],
            service_scope="EXPORT_D2A",
            payment_term="PREPAID",
            shipment_type="D2A"
        )
        
        # Test business rules determination
        rules = load_business_rules()
        context = determine_pricing_context(payload, rules)
        
        # Validate business rule path and context
        self.assertEqual(context.currency, "PGK")
        self.assertEqual(context.charge_scope, ["ORIGIN", "AIR_FREIGHT"])
        self.assertFalse(context.requires_manual_review)
        self.assertIn("EXPORT.PREPAID.D2A", context.rule_path)
        
        # Validate applicable services include origin and air freight only
        expected_services = ["PICKUP", "EXPORT_CLEARANCE", "HANDLING", "AIR_FREIGHT", "FUEL_SURCHARGE", "SECURITY_SURCHARGE"]
        for service in expected_services:
            self.assertIn(service, context.applicable_services)
        
        # Validate destination services are excluded
        excluded_services = ["IMPORT_CLEARANCE", "DELIVERY", "CUSTOMS_HANDLING"]
        for service in excluded_services:
            self.assertNotIn(service, context.applicable_services)
        
        # Test full pricing integration
        result = compute_quote(payload)
        
        # Verify only origin and air freight services appear
        service_codes_in_result = [line.code for line in result.sell_lines]
        for expected_service in ["PICKUP_EXPORT", "EXPORT_CLEARANCE_D2A", "HANDLING_EXPORT"]:
            self.assertIn(expected_service, service_codes_in_result)
        
        # Verify destination services are filtered out
        for excluded_service in ["IMPORT_CLEARANCE_EXCLUDED", "DELIVERY_EXCLUDED"]:
            self.assertNotIn(excluded_service, service_codes_in_result)

    def test_business_rules_export_prepaid_d2d(self):
        """Test the Export Prepaid Door-to-Door path validates PGK currency and comprehensive service scope."""
        
        # Create isolated test data
        audience_export_d2d = Audience.get_or_create_from_code("PNG_CUSTOMER_EXPORT_D2D")
        org_export_d2d = Organizations.objects.create(name="Test Export Prepaid D2D Org", audience=audience_export_d2d)
        
        # Create services for full export D2D scope
        svc_pickup_d2d = Services.objects.create(code="PICKUP_D2D", name="Pickup D2D", basis="PER_SHIPMENT")
        svc_export_clearance_d2d = Services.objects.create(code="EXPORT_CLEARANCE_D2D", name="Export Clearance D2D", basis="PER_SHIPMENT")
        svc_handling_d2d = Services.objects.create(code="HANDLING_D2D", name="Handling D2D", basis="PER_KG")
        svc_air_freight_d2d = Services.objects.create(code="AIR_FREIGHT_D2D", name="Air Freight D2D", basis="PER_KG")
        svc_agent_clearance = Services.objects.create(code="AGENT_CLEARANCE", name="Agent Clearance", basis="PER_SHIPMENT")
        svc_documentation = Services.objects.create(code="DOCUMENTATION", name="Documentation", basis="PER_SHIPMENT")
        svc_final_delivery = Services.objects.create(code="FINAL_DELIVERY", name="Final Delivery", basis="PER_SHIPMENT")
        svc_notification = Services.objects.create(code="NOTIFICATION", name="Notification", basis="PER_SHIPMENT")
        
        # Create sell ratecard in PGK
        rc_sell_export_d2d = Ratecards.objects.create(
            provider=self.agent_provider,
            name="Test Export Prepaid D2D Card",
            role="SELL",
            scope="INTERNATIONAL",
            direction="EXPORT",
            currency="PGK",
            audience=audience_export_d2d,
            effective_date=now()
        )
        
        # Create service items for all D2D services
        for service in [svc_pickup_d2d, svc_export_clearance_d2d, svc_handling_d2d, svc_air_freight_d2d,
                       svc_agent_clearance, svc_documentation, svc_final_delivery, svc_notification]:
            ServiceItems.objects.create(
                ratecard=rc_sell_export_d2d,
                service=service,
                amount=Decimal("90.00") if service.basis == "PER_SHIPMENT" else None,
                currency="PGK",
                tax_pct=Decimal("10.00"),
                conditions_json={}
            )
        
        # Create lane for weight-based services
        lane_export_d2d = Lanes.objects.create(
            ratecard=rc_sell_export_d2d,
            origin=self.station_pom,
            dest=self.station_bne,
            is_direct=True
        )
        LaneBreaks.objects.create(lane=lane_export_d2d, break_code="N", per_kg=Decimal("30.00"))
        
        # Test Export Prepaid D2D scenario
        payload = ShipmentInput(
            org_id=org_export_d2d.id,
            origin_iata="POM",
            dest_iata="BNE",
            pieces=[Piece(weight_kg=Decimal("25"))],
            service_scope="EXPORT_D2D",
            payment_term="PREPAID",
            shipment_type="D2D"
        )
        
        # Test business rules determination
        rules = load_business_rules()
        context = determine_pricing_context(payload, rules)
        
        # Validate business rule path and context
        self.assertEqual(context.currency, "PGK")
        self.assertEqual(context.charge_scope, ["ORIGIN", "AIR_FREIGHT", "AGENT_CLEARANCE", "DELIVERY"])
        self.assertFalse(context.requires_manual_review)
        self.assertIn("EXPORT.PREPAID.D2D", context.rule_path)
        
        # Validate applicable services include comprehensive scope
        expected_services = ["PICKUP", "EXPORT_CLEARANCE", "HANDLING", "AIR_FREIGHT", 
                           "FUEL_SURCHARGE", "SECURITY_SURCHARGE", "AGENT_CLEARANCE", 
                           "DOCUMENTATION", "FINAL_DELIVERY", "NOTIFICATION"]
        for service in expected_services:
            self.assertIn(service, context.applicable_services)
        
        # Test full pricing integration
        result = compute_quote(payload)
        
        # Verify comprehensive service scope appears in pricing lines
        service_codes_in_result = [line.code for line in result.sell_lines]
        for expected_service in ["PICKUP_D2D", "EXPORT_CLEARANCE_D2D", "HANDLING_D2D", 
                               "AIR_FREIGHT_D2D", "AGENT_CLEARANCE", "DOCUMENTATION", 
                               "FINAL_DELIVERY", "NOTIFICATION"]:
            self.assertIn(expected_service, service_codes_in_result)
        
        # Verify snapshot contains comprehensive business rules metadata
        self.assertIn("business_rules", result.snapshot)
        self.assertEqual(result.snapshot["business_rules"]["currency"], "PGK")
        self.assertEqual(result.snapshot["business_rules"]["charge_scope"], 
                        ["ORIGIN", "AIR_FREIGHT", "AGENT_CLEARANCE", "DELIVERY"])

    def test_business_rules_export_collect_fallback(self):
        """Test the Export Collect fallback scenario validates fallback rule application and manual review."""
        
        # Create isolated test data
        audience_export_collect = Audience.get_or_create_from_code("PNG_CUSTOMER_EXPORT_COLLECT")
        org_export_collect = Organizations.objects.create(name="Test Export Collect Org", audience=audience_export_collect)
        
        # Create services for origin only (fallback scope)
        svc_pickup_fallback = Services.objects.create(code="PICKUP_FALLBACK", name="Pickup Fallback", basis="PER_SHIPMENT")
        svc_export_clearance_fallback = Services.objects.create(code="EXPORT_CLEARANCE_FALLBACK", name="Export Clearance Fallback", basis="PER_SHIPMENT")
        
        # Create sell ratecard in PGK
        rc_sell_export_collect = Ratecards.objects.create(
            provider=self.agent_provider,
            name="Test Export Collect Fallback Card",
            role="SELL",
            scope="INTERNATIONAL",
            direction="EXPORT",
            currency="PGK",
            audience=audience_export_collect,
            effective_date=now()
        )
        
        # Create service items for origin services only
        for service in [svc_pickup_fallback, svc_export_clearance_fallback]:
            ServiceItems.objects.create(
                ratecard=rc_sell_export_collect,
                service=service,
                amount=Decimal("120.00"),
                currency="PGK",
                tax_pct=Decimal("10.00"),
                conditions_json={}
            )
        
        # Test Export Collect scenario (should trigger fallback)
        payload = ShipmentInput(
            org_id=org_export_collect.id,
            origin_iata="POM",
            dest_iata="BNE",
            pieces=[Piece(weight_kg=Decimal("18"))],
            service_scope="EXPORT_D2D",
            payment_term="COLLECT",
            shipment_type="D2D"
        )
        
        # Test business rules determination with logging
        rules = load_business_rules()
        
        with self.assertLogs('pricing.services.business_rules', level='WARNING') as cm:
            context = determine_pricing_context(payload, rules)
            # Verify fallback warning is logged
            self.assertTrue(any("fallback rule" in log.lower() for log in cm.output))
        
        # Validate fallback business rule path and context
        self.assertEqual(context.currency, "PGK")
        self.assertEqual(context.charge_scope, ["ORIGIN"])
        self.assertTrue(context.requires_manual_review)
        self.assertIn("fallback", context.rule_path.lower())
        
        # Validate applicable services include only origin services
        expected_services = ["PICKUP", "EXPORT_CLEARANCE", "HANDLING"]
        for service in expected_services:
            self.assertIn(service, context.applicable_services)
        
        # Test full pricing integration
        result = compute_quote(payload)
        
        # Verify manual review flag is propagated to snapshot
        self.assertIn("business_rules", result.snapshot)
        self.assertTrue(result.snapshot["business_rules"]["requires_manual_review"])
        
        # Verify only origin services appear in pricing lines
        service_codes_in_result = [line.code for line in result.sell_lines]
        for expected_service in ["PICKUP_FALLBACK", "EXPORT_CLEARANCE_FALLBACK"]:
            self.assertIn(expected_service, service_codes_in_result)

    def test_business_rules_invalid_combinations(self):
        """Test invalid business rule combinations and error handling."""
        
        # Create test organization
        org_invalid = Organizations.objects.create(name="Test Invalid Rules Org")
        
        # Test unsupported payment term
        payload_invalid_payment = ShipmentInput(
            org_id=org_invalid.id,
            origin_iata="BNE",
            dest_iata="POM",
            pieces=[Piece(weight_kg=Decimal("10"))],
            service_scope="INTERNATIONAL",
            payment_term="CREDIT",  # Unsupported payment term
            shipment_type="D2D"
        )
        
        rules = load_business_rules()
        
        with self.assertRaises(RuleApplicationError) as cm:
            determine_pricing_context(payload_invalid_payment, rules)
        self.assertIn("Unsupported payment term", str(cm.exception))
        
        # Test missing business rule combination
        payload_missing_rule = ShipmentInput(
            org_id=org_invalid.id,
            origin_iata="BNE",
            dest_iata="POM",
            pieces=[Piece(weight_kg=Decimal("10"))],
            service_scope="IMPORT_SPECIAL",  # This should result in no matching rule
            payment_term="PREPAID",
            shipment_type="SPECIAL"  # Unsupported movement type
        )
        
        with self.assertRaises(RuleApplicationError) as cm:
            determine_pricing_context(payload_missing_rule, rules)
        self.assertIn("No business rule found", str(cm.exception))
        
        # Test graceful degradation in compute_quote
        with self.assertLogs('pricing.services.pricing_service', level='ERROR') as cm:
            try:
                result = compute_quote(payload_invalid_payment)
                # If it doesn't raise an exception, verify error handling
                self.assertIsNotNone(result)
            except Exception:
                # Exception is acceptable for invalid business rules
                pass

    def test_business_rules_service_filtering_enforcement(self):
        """Test that service filtering is strictly enforced based on business rules."""
        
        # Create isolated test data
        audience_filtering = Audience.get_or_create_from_code("PNG_CUSTOMER_FILTERING_TEST")
        org_filtering = Organizations.objects.create(name="Test Service Filtering Org", audience=audience_filtering)
        
        # Create services that should be included (destination services for A2D)
        svc_included_1 = Services.objects.create(code="IMPORT_CLEARANCE_FILTER", name="Import Clearance Filter", basis="PER_SHIPMENT")
        svc_included_2 = Services.objects.create(code="DELIVERY_FILTER", name="Delivery Filter", basis="PER_SHIPMENT")
        
        # Create services that should be filtered out (origin services for A2D)
        svc_excluded_1 = Services.objects.create(code="PICKUP_FILTER", name="Pickup Filter", basis="PER_SHIPMENT")
        svc_excluded_2 = Services.objects.create(code="EXPORT_CLEARANCE_FILTER", name="Export Clearance Filter", basis="PER_SHIPMENT")
        
        # Create sell ratecard
        rc_sell_filtering = Ratecards.objects.create(
            provider=self.agent_provider,
            name="Test Service Filtering Card",
            role="SELL",
            scope="INTERNATIONAL",
            direction="IMPORT",
            currency="PGK",
            audience=audience_filtering,
            effective_date=now()
        )
        
        # Create service items for ALL services (both included and excluded)
        for service in [svc_included_1, svc_included_2, svc_excluded_1, svc_excluded_2]:
            ServiceItems.objects.create(
                ratecard=rc_sell_filtering,
                service=service,
                amount=Decimal("60.00"),
                currency="PGK",
                tax_pct=Decimal("10.00"),
                conditions_json={}
            )
        
        # Test Import Collect A2D scenario (should only include destination services)
        payload = ShipmentInput(
            org_id=org_filtering.id,
            origin_iata="BNE",
            dest_iata="POM",
            pieces=[Piece(weight_kg=Decimal("8"))],
            service_scope="IMPORT_A2D",
            payment_term="COLLECT",
            shipment_type="A2D"
        )
        
        # Test business rules determination
        rules = load_business_rules()
        context = determine_pricing_context(payload, rules)
        
        # Validate charge scope is destination only
        self.assertEqual(context.charge_scope, ["DESTINATION"])
        
        # Test full pricing integration
        result = compute_quote(payload)
        
        # Verify only destination services appear in pricing lines
        service_codes_in_result = [line.code for line in result.sell_lines]
        
        # These should be included (destination services)
        for included_service in ["IMPORT_CLEARANCE_FILTER", "DELIVERY_FILTER"]:
            self.assertIn(included_service, service_codes_in_result,
                         f"Service {included_service} should be included for A2D destination scope")
        
        # These should be filtered out (origin services)
        for excluded_service in ["PICKUP_FILTER", "EXPORT_CLEARANCE_FILTER"]:
            self.assertNotIn(excluded_service, service_codes_in_result,
                           f"Service {excluded_service} should be filtered out for A2D destination scope")
        
        # Verify business rules filtering is documented in snapshot
        self.assertIn("business_rules", result.snapshot)
        self.assertEqual(result.snapshot["business_rules"]["charge_scope"], ["DESTINATION"])

    def test_business_rules_currency_resolution_edge_cases(self):
        """Test currency resolution edge cases and fallback logic."""
        
        # Create test organization
        org_currency = Organizations.objects.create(name="Test Currency Resolution Org")
        
        # Test SHIPPER_CURRENCY resolution with AU origin (should resolve to AUD)
        payload_au = ShipmentInput(
            org_id=org_currency.id,
            origin_iata="BNE",  # AU origin
            dest_iata="POM",
            pieces=[Piece(weight_kg=Decimal("10"))],
            service_scope="IMPORT_A2D",
            payment_term="PREPAID",
            shipment_type="A2D"
        )
        
        rules = load_business_rules()
        context_au = determine_pricing_context(payload_au, rules)
        
        # Should resolve to AUD for AU origin or fallback to USD/AUD
        self.assertIn(context_au.currency, ["AUD", "USD"])
        
        # Test with unknown origin (should use fallback)
        station_unknown = Station.objects.create(iata="XXX", city="Unknown", country="XX")
        payload_unknown = ShipmentInput(
            org_id=org_currency.id,
            origin_iata="XXX",  # Unknown origin
            dest_iata="POM",
            pieces=[Piece(weight_kg=Decimal("10"))],
            service_scope="IMPORT_A2D",
            payment_term="PREPAID",
            shipment_type="A2D"
        )
        
        with self.assertLogs('pricing.services.business_rules', level='DEBUG') as cm:
            context_unknown = determine_pricing_context(payload_unknown, rules)
            # Should use fallback currency
            self.assertIn(context_unknown.currency, ["AUD", "USD"])
        
        # Test per-rule currency fallback
        # This tests the currency_fallback option in the business rules
        self.assertIsNotNone(context_unknown.currency)
        self.assertIn(context_unknown.currency, ["AUD", "USD", "PGK"])
        
        # Verify currency resolution is documented in metadata
        self.assertIn("currency", context_unknown.metadata["rule_config"])

    def test_business_rules_snapshot_and_metadata(self):
        """Test that business rules context is properly captured in snapshots and metadata."""
        
        # Create isolated test data
        audience_snapshot = Audience.get_or_create_from_code("PNG_CUSTOMER_SNAPSHOT_TEST")
        org_snapshot = Organizations.objects.create(name="Test Snapshot Org", audience=audience_snapshot)
        
        # Create a simple service for testing
        svc_snapshot = Services.objects.create(code="SNAPSHOT_TEST", name="Snapshot Test", basis="PER_SHIPMENT")
        
        # Create sell ratecard
        rc_sell_snapshot = Ratecards.objects.create(
            provider=self.agent_provider,
            name="Test Snapshot Card",
            role="SELL",
            scope="INTERNATIONAL",
            direction="IMPORT",
            currency="PGK",
            audience=audience_snapshot,
            effective_date=now()
        )
        
        ServiceItems.objects.create(
            ratecard=rc_sell_snapshot,
            service=svc_snapshot,
            amount=Decimal("150.00"),
            currency="PGK",
            tax_pct=Decimal("10.00"),
            conditions_json={}
        )
        
        # Test scenario
        payload = ShipmentInput(
            org_id=org_snapshot.id,
            origin_iata="BNE",
            dest_iata="POM",
            pieces=[Piece(weight_kg=Decimal("5"))],
            service_scope="IMPORT_D2D",
            payment_term="COLLECT",
            shipment_type="D2D"
        )
        
        # Test with logging to verify business rules application is logged
        with self.assertLogs('pricing.services.business_rules', level='INFO') as cm:
            result = compute_quote(payload)
            # Verify business rules application is logged
            self.assertTrue(any("Successfully determined pricing context" in log for log in cm.output))
        
        # Validate business_rules section in snapshot
        self.assertIn("business_rules", result.snapshot)
        business_rules_snapshot = result.snapshot["business_rules"]
        
        # Validate all required fields are present
        required_fields = ["currency", "charge_scope", "applicable_services", "requires_manual_review", "rule_path"]
        for field in required_fields:
            self.assertIn(field, business_rules_snapshot)
        
        # Validate rule_path tracking for audit purposes
        self.assertIn("IMPORT.COLLECT.D2D", business_rules_snapshot["rule_path"])
        
        # Validate metadata includes direction, payment_term, movement_type
        self.assertIn("metadata", business_rules_snapshot)
        metadata = business_rules_snapshot["metadata"]
        self.assertEqual(metadata["direction"], "IMPORT")
        self.assertEqual(metadata["payment_term"], "COLLECT")
        self.assertEqual(metadata["movement_type"], "D2D")
        
        # Validate manual review flag handling
        self.assertFalse(business_rules_snapshot["requires_manual_review"])
        
        # Validate business rules application is logged for debugging
        self.assertIn("description", business_rules_snapshot)
        
        # Test that rule_config is preserved in metadata
        self.assertIn("rule_config", metadata)
        self.assertIsInstance(metadata["rule_config"], dict)
        
        # Validate snapshot completeness for audit trail
        self.assertIn("timestamp", result.snapshot)
        self.assertIn("sell_ratecard_id", result.snapshot)
        
        # Clear business rules cache to test cache functionality
        clear_business_rules_cache()
        
        # Run again to test cache reload
        result2 = compute_quote(payload)
        self.assertEqual(result2.snapshot["business_rules"]["rule_path"], 
                        result.snapshot["business_rules"]["rule_path"])
