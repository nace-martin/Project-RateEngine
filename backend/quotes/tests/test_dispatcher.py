# backend/quotes/tests/test_dispatcher.py
"""
Tests for the Pricing Dispatcher module.

Tests cover:
1. Routing for IMPORT, EXPORT, DOMESTIC shipment types
2. Kill-switch override (USE_LEGACY_PRICING)
3. RoutingError for invalid shipment types
4. Engine version stamping on results
5. Shadow mode variance logging
"""

from decimal import Decimal
from unittest.mock import patch, MagicMock
from uuid import uuid4

from django.test import TestCase, override_settings

from quotes.services.dispatcher import (
    PricingDispatcher,
    RoutingMap,
    RoutingError,
    EngineVersion,
    ShipmentType,
    CalculationResult,
    ShadowComparison,
)
from core.dataclasses import (
    QuoteInput,
    QuoteCharges,
    ShipmentDetails,
    Piece,
    LocationRef,
    CalculatedTotals,
)


class TestRoutingMap(TestCase):
    """Tests for the RoutingMap configuration."""
    
    def test_import_routes_to_v4(self):
        """IMPORT shipments should route to V4."""
        version = RoutingMap.get_engine_version("IMPORT")
        self.assertEqual(version, EngineVersion.V4)
    
    def test_export_routes_to_v4(self):
        """EXPORT shipments should route to V4."""
        version = RoutingMap.get_engine_version("EXPORT")
        self.assertEqual(version, EngineVersion.V4)
    
    def test_domestic_routes_to_v4(self):
        """DOMESTIC shipments should route to V4."""
        version = RoutingMap.get_engine_version("DOMESTIC")
        self.assertEqual(version, EngineVersion.V4)
    
    def test_case_insensitive_routing(self):
        """Routing should be case-insensitive."""
        self.assertEqual(
            RoutingMap.get_engine_version("import"), 
            EngineVersion.V4
        )
        self.assertEqual(
            RoutingMap.get_engine_version("Export"), 
            EngineVersion.V4
        )
    
    def test_routing_error_for_unknown_type(self):
        """Unknown shipment types should raise RoutingError."""
        with self.assertRaises(RoutingError) as ctx:
            RoutingMap.get_engine_version("UNKNOWN_TYPE")
        
        self.assertIn("Cannot route", str(ctx.exception))
        self.assertIn("UNKNOWN_TYPE", str(ctx.exception))
    
    def test_routing_error_for_none(self):
        """None shipment type should raise RoutingError."""
        with self.assertRaises(RoutingError):
            RoutingMap.get_engine_version(None)
    
    def test_routing_error_for_empty_string(self):
        """Empty string should raise RoutingError."""
        with self.assertRaises(RoutingError):
            RoutingMap.get_engine_version("")


class TestPricingDispatcherRouting(TestCase):
    """Tests for PricingDispatcher routing logic."""
    
    def _create_quote_input(self, shipment_type: str) -> QuoteInput:
        """Helper to create a QuoteInput with given shipment type."""
        return QuoteInput(
            customer_id=uuid4(),
            contact_id=uuid4(),
            output_currency="PGK",
            shipment=ShipmentDetails(
                mode="AIR",
                shipment_type=shipment_type,
                direction=shipment_type,
                incoterm="DAP",
                payment_term="PREPAID",
                is_dangerous_goods=False,
                pieces=[Piece(pieces=1, length_cm=Decimal("10"), width_cm=Decimal("10"), height_cm=Decimal("10"), gross_weight_kg=Decimal("5"))],
                service_scope="D2D",
                origin_location=LocationRef(
                    id=uuid4(), code="LAX", name="Los Angeles",
                    country_code="US", currency_code="USD"
                ),
                destination_location=LocationRef(
                    id=uuid4(), code="POM", name="Port Moresby",
                    country_code="PG", currency_code="PGK"
                ),
            ),
        )
    
    def _mock_charges(self, total_sell_pgk: Decimal = Decimal("1000.00")) -> QuoteCharges:
        """Create mock QuoteCharges."""
        totals = CalculatedTotals(
            total_cost_pgk=Decimal("500.00"),
            total_sell_pgk=total_sell_pgk,
            total_sell_pgk_incl_gst=total_sell_pgk * Decimal("1.1"),
            total_sell_fcy=total_sell_pgk,
            total_sell_fcy_incl_gst=total_sell_pgk * Decimal("1.1"),
            total_sell_fcy_currency="PGK",
            has_missing_rates=False,
        )
        
        return QuoteCharges(lines=[], totals=totals)

    @patch('quotes.services.dispatcher.PricingDispatcher._calculate_v4')
    def test_import_dispatches_to_v4(self, mock_calc):
        """IMPORT should dispatch to V4 engine."""
        mock_calc.return_value = self._mock_charges()
        
        dispatcher = PricingDispatcher()
        quote_input = self._create_quote_input("IMPORT")
        result = dispatcher.calculate(quote_input)
        
        self.assertEqual(result.engine_version, "V4")
        mock_calc.assert_called_once()

    @patch('quotes.services.dispatcher.PricingDispatcher._calculate_v4')
    def test_export_dispatches_to_v4(self, mock_calc):
        """EXPORT should dispatch to V4 engine."""
        mock_calc.return_value = self._mock_charges()
        
        dispatcher = PricingDispatcher()
        quote_input = self._create_quote_input("EXPORT")
        result = dispatcher.calculate(quote_input)
        
        self.assertEqual(result.engine_version, "V4")

    @patch('quotes.services.dispatcher.PricingDispatcher._calculate_v4')
    def test_domestic_dispatches_to_v4(self, mock_calc):
        """DOMESTIC should dispatch to V4 engine."""
        mock_calc.return_value = self._mock_charges()
        
        dispatcher = PricingDispatcher()
        quote_input = self._create_quote_input("DOMESTIC")
        result = dispatcher.calculate(quote_input)
        
        self.assertEqual(result.engine_version, "V4")
    
    def test_routing_error_for_invalid_type(self):
        """Invalid shipment types should raise RoutingError."""
        dispatcher = PricingDispatcher()
        quote_input = self._create_quote_input("INVALID")
        
        with self.assertRaises(RoutingError):
            dispatcher.calculate(quote_input)


class TestKillSwitch(TestCase):
    """Tests for the USE_LEGACY_PRICING kill-switch."""
    
    def _create_quote_input(self) -> QuoteInput:
        """Helper to create a simple QuoteInput."""
        return QuoteInput(
            customer_id=uuid4(),
            contact_id=uuid4(),
            output_currency="PGK",
            shipment=ShipmentDetails(
                mode="AIR",
                shipment_type="IMPORT",
                direction="IMPORT",
                incoterm="DAP",
                payment_term="PREPAID",
                is_dangerous_goods=False,
                pieces=[Piece(pieces=1, length_cm=Decimal("10"), width_cm=Decimal("10"), height_cm=Decimal("10"), gross_weight_kg=Decimal("5"))],
                service_scope="D2D",
                origin_location=LocationRef(
                    id=uuid4(), code="LAX", name="Los Angeles",
                    country_code="US", currency_code="USD"
                ),
                destination_location=LocationRef(
                    id=uuid4(), code="POM", name="Port Moresby",
                    country_code="PG", currency_code="PGK"
                ),
            ),
        )
    
    @patch('quotes.services.dispatcher.PricingDispatcher._calculate_v3')
    @override_settings(USE_LEGACY_PRICING=True)
    def test_kill_switch_routes_to_v3(self, mock_calc_v3):
        """When USE_LEGACY_PRICING=True, all routes should go to V3."""
        totals = CalculatedTotals(
            total_cost_pgk=Decimal("500.00"),
            total_sell_pgk=Decimal("1000.00"),
            total_sell_pgk_incl_gst=Decimal("1100.00"),
            total_sell_fcy=Decimal("1000.00"),
            total_sell_fcy_incl_gst=Decimal("1100.00"),
            total_sell_fcy_currency="PGK",
            has_missing_rates=False,
        )
        mock_calc_v3.return_value = QuoteCharges(lines=[], totals=totals)
        
        dispatcher = PricingDispatcher()
        quote_input = self._create_quote_input()
        result = dispatcher.calculate(quote_input)
        
        # Should return V3 engine version
        self.assertEqual(result.engine_version, "V3")
        mock_calc_v3.assert_called_once()
    
    @patch('quotes.services.dispatcher.PricingDispatcher._calculate_v4')
    @override_settings(USE_LEGACY_PRICING=False)
    def test_kill_switch_off_routes_to_v4(self, mock_calc_v4):
        """When USE_LEGACY_PRICING=False, routes should use normal V4."""
        totals = CalculatedTotals(
            total_cost_pgk=Decimal("500.00"),
            total_sell_pgk=Decimal("1000.00"),
            total_sell_pgk_incl_gst=Decimal("1100.00"),
            total_sell_fcy=Decimal("1000.00"),
            total_sell_fcy_incl_gst=Decimal("1100.00"),
            total_sell_fcy_currency="PGK",
            has_missing_rates=False,
        )
        mock_calc_v4.return_value = QuoteCharges(lines=[], totals=totals)
        
        dispatcher = PricingDispatcher()
        quote_input = self._create_quote_input()
        result = dispatcher.calculate(quote_input)
        
        self.assertEqual(result.engine_version, "V4")


class TestPreFlightCheck(TestCase):
    """Tests for the pre-flight zero-charge detection."""
    
    def _create_quote_input(self) -> QuoteInput:
        return QuoteInput(
            customer_id=uuid4(),
            contact_id=uuid4(),
            output_currency="PGK",
            shipment=ShipmentDetails(
                mode="AIR",
                shipment_type="IMPORT",
                direction="IMPORT",
                incoterm="DAP",
                payment_term="PREPAID",
                is_dangerous_goods=False,
                pieces=[Piece(pieces=1, length_cm=Decimal("10"), width_cm=Decimal("10"), height_cm=Decimal("10"), gross_weight_kg=Decimal("5"))],
                service_scope="D2D",
                origin_location=LocationRef(
                    id=uuid4(), code="LAX", name="Los Angeles",
                    country_code="US", currency_code="USD"
                ),
                destination_location=LocationRef(
                    id=uuid4(), code="POM", name="Port Moresby",
                    country_code="PG", currency_code="PGK"
                ),
            ),
        )
    
    @patch('quotes.services.dispatcher.PricingDispatcher._calculate_v4')
    @patch('quotes.services.dispatcher.logger')
    def test_zero_charges_logs_critical(self, mock_logger, mock_calc):
        """Zero charges should log a CRITICAL error."""
        totals = CalculatedTotals(
            total_cost_pgk=Decimal("0"),
            total_sell_pgk=Decimal("0"),
            total_sell_pgk_incl_gst=Decimal("0"),
            total_sell_fcy=Decimal("0"),
            total_sell_fcy_incl_gst=Decimal("0"),
            total_sell_fcy_currency="PGK",
            has_missing_rates=True,
        )
        mock_calc.return_value = QuoteCharges(lines=[], totals=totals)
        
        dispatcher = PricingDispatcher()
        quote_input = self._create_quote_input()
        
        # Should not raise, but should log critical
        result = dispatcher.calculate(quote_input)
        
        # Verify critical was logged
        mock_logger.critical.assert_called_once()
        call_args = str(mock_logger.critical.call_args)
        self.assertIn("PRE-FLIGHT FAILURE", call_args)


class TestShadowMode(TestCase):
    """Tests for shadow mode variance logging."""
    
    @patch('quotes.services.dispatcher.logger')
    def test_high_variance_logs_warning(self, mock_logger):
        """High variance (>1% or >5 PGK) should log a WARNING."""
        dispatcher = PricingDispatcher()
        
        # Create a comparison with high variance
        comparison = ShadowComparison(
            v3_total_pgk=Decimal("1000.00"),
            v4_total_pgk=Decimal("1100.00"),  # 10% variance
            variance_pgk=Decimal("100.00"),
            variance_percent=Decimal("10.0"),
            is_high_variance=True,
        )
        
        # Verify the comparison is marked as high variance
        self.assertTrue(comparison.is_high_variance)
        self.assertGreater(comparison.variance_percent, Decimal("1.0"))
    
    def test_low_variance_not_flagged(self):
        """Low variance (<1% and <5 PGK) should not be flagged."""
        comparison = ShadowComparison(
            v3_total_pgk=Decimal("1000.00"),
            v4_total_pgk=Decimal("1002.00"),  # 0.2% variance
            variance_pgk=Decimal("2.00"),
            variance_percent=Decimal("0.2"),
            is_high_variance=False,
        )
        
        self.assertFalse(comparison.is_high_variance)


class TestEngineVersionStamping(TestCase):
    """Tests for engine version in calculation results."""
    
    def _create_quote_input(self) -> QuoteInput:
        return QuoteInput(
            customer_id=uuid4(),
            contact_id=uuid4(),
            output_currency="PGK",
            shipment=ShipmentDetails(
                mode="AIR",
                shipment_type="IMPORT",
                direction="IMPORT",
                incoterm="DAP",
                payment_term="PREPAID",
                is_dangerous_goods=False,
                pieces=[Piece(pieces=1, length_cm=Decimal("10"), width_cm=Decimal("10"), height_cm=Decimal("10"), gross_weight_kg=Decimal("5"))],
                service_scope="D2D",
                origin_location=LocationRef(
                    id=uuid4(), code="LAX", name="Los Angeles",
                    country_code="US", currency_code="USD"
                ),
                destination_location=LocationRef(
                    id=uuid4(), code="POM", name="Port Moresby",
                    country_code="PG", currency_code="PGK"
                ),
            ),
        )
    
    @patch('quotes.services.dispatcher.PricingDispatcher._calculate_v4')
    def test_result_contains_engine_version(self, mock_calc):
        """CalculationResult should always contain engine_version."""
        totals = CalculatedTotals(
            total_cost_pgk=Decimal("500.00"),
            total_sell_pgk=Decimal("1000.00"),
            total_sell_pgk_incl_gst=Decimal("1100.00"),
            total_sell_fcy=Decimal("1000.00"),
            total_sell_fcy_incl_gst=Decimal("1100.00"),
            total_sell_fcy_currency="PGK",
            has_missing_rates=False,
        )
        mock_calc.return_value = QuoteCharges(lines=[], totals=totals)
        
        dispatcher = PricingDispatcher()
        quote_input = self._create_quote_input()
        result = dispatcher.calculate(quote_input)
        
        self.assertIsInstance(result, CalculationResult)
        self.assertIn(result.engine_version, ["V3", "V4"])
        self.assertIsNotNone(result.charges)
    
    def test_get_engine_version_method(self):
        """Dispatcher should expose current default engine version."""
        dispatcher = PricingDispatcher()
        version = dispatcher.get_engine_version()
        
        self.assertEqual(version, "V4")
    
    @override_settings(USE_LEGACY_PRICING=True)
    def test_get_engine_version_with_kill_switch(self):
        """With kill-switch, get_engine_version should return V3."""
        dispatcher = PricingDispatcher()
        version = dispatcher.get_engine_version()
        
        self.assertEqual(version, "V3")
