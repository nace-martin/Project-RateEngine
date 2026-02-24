# backend/quotes/tests/test_dispatcher.py
"""
Tests for the Pricing Dispatcher module.

Tests cover:
1. Routing for IMPORT, EXPORT, DOMESTIC shipment types
2. RoutingError for invalid shipment types
3. Engine version stamping on results
4. Pre-flight zero-charge logging
"""

from decimal import Decimal
from unittest.mock import patch, MagicMock
from uuid import uuid4

from django.test import TestCase

from quotes.services.dispatcher import (
    PricingDispatcher,
    RoutingMap,
    RoutingError,
    EngineVersion,
    ShipmentType,
    CalculationResult,
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
        self.assertEqual(result.engine_version, "V4")
        self.assertIsNotNone(result.charges)
    
    def test_get_engine_version_method(self):
        """Dispatcher should expose current default engine version."""
        dispatcher = PricingDispatcher()
        version = dispatcher.get_engine_version()
        
        self.assertEqual(version, "V4")
    
