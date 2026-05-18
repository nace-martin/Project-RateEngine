# backend/pricing_v4/tests/test_domestic_engine.py
"""
Domestic Pricing Engine Tests modernized for Phase 4E.
"""
from decimal import Decimal
from datetime import date, timedelta
from dataclasses import fields
from django.test import TestCase

from core.charge_rules import (
    CALCULATION_FLAT,
    CALCULATION_MIN_OR_PER_UNIT,
    CALCULATION_TIERED_BREAK,
)
from pricing_v4.models import (
    CommodityChargeRule,
    ProductCode, Carrier, Agent,
    DomesticCOGS, DomesticSellRate, Surcharge
)
from pricing_v4.engine.domestic_engine import DomesticPricingEngine
from pricing_v4.engine.result_types import QuoteLineItem, QuoteResult
from pricing_v4.services.rate_selector import RateAmbiguityError
from pricing_v4.tests.validated_factories import (
    create_validated_domestic_cogs,
    create_validated_domestic_sell,
    create_validated_surcharge,
    get_or_create_test_product
)


EXPECTED_QUOTE_RESULT_FIELDS = {field.name for field in fields(QuoteResult)}
EXPECTED_LINE_ITEM_FIELDS = {field.name for field in fields(QuoteLineItem)}


class DomesticEngineTestCase(TestCase):
    """Base test case with common setup for Domestic Engine tests."""
    
    @classmethod
    def setUpTestData(cls):
        """Create ProductCodes and seed data for domestic tests."""
        # Create Domestic ProductCodes (3xxx range)
        cls.pc_freight = get_or_create_test_product(
            id=3001,
            code='DOM-FRT-AIR',
            domain='DOMESTIC',
            category='FREIGHT',
            is_gst_applicable=True,
            default_unit='KG'
        )
        cls.pc_doc_fee = get_or_create_test_product(
            id=3002,
            code='DOM-DOC',
            domain='DOMESTIC',
            category='DOCUMENTATION',
            is_gst_applicable=True,
            default_unit='SHIPMENT'
        )
        cls.pc_fuel = get_or_create_test_product(
            id=3003,
            code='DOM-FSC',
            domain='DOMESTIC',
            category='SURCHARGE',
            is_gst_applicable=True,
            default_unit='KG'
        )
        
        # Create Carrier
        cls.carrier_px = Carrier.objects.create(
            code='PX',
            name='Air Niugini',
            carrier_type='AIRLINE'
        )
        
        # Validity dates
        cls.valid_from = date.today() - timedelta(days=30)
        cls.valid_until = date.today() + timedelta(days=365)


class DomesticFreightTest(DomesticEngineTestCase):
    """Test freight rate calculation."""
    
    def setUp(self):
        """Create freight rates for POM-LAE."""
        create_validated_domestic_cogs(
            product_code=self.pc_freight,
            origin_zone='POM',
            destination_zone='LAE',
            carrier=self.carrier_px,
            currency='PGK',
            rate_per_kg=Decimal('6.50'),
            min_charge=Decimal('100.00'),
            valid_from=self.valid_from,
            valid_until=self.valid_until
        )
        create_validated_domestic_sell(
            product_code=self.pc_freight,
            origin_zone='POM',
            destination_zone='LAE',
            currency='PGK',
            rate_per_kg=Decimal('8.00'),
            min_charge=Decimal('120.00'),
            valid_from=self.valid_from,
            valid_until=self.valid_until
        )
    
    def test_basic_freight_calculation(self):
        """Test simple per-kg freight calculation."""
        engine = DomesticPricingEngine(
            cogs_origin='POM',
            destination='LAE',
            weight_kg=50,
            service_scope='A2A'
        )
        result = engine.calculate_quote()
        
        self.assertEqual(len(result.cogs_breakdown), 1)
        self.assertEqual(len(result.sell_breakdown), 1)
        self.assertEqual(result.cogs_breakdown[0].amount, Decimal('325.00'))
        self.assertEqual(result.sell_breakdown[0].amount, Decimal('400.00'))

    def test_multiple_domestic_cogs_without_counterparty_raises_ambiguity(self):
        agent = Agent.objects.create(
            code='DOM-AG',
            name='Domestic Agent',
            country_code='PG',
            agent_type='ORIGIN',
        )
        create_validated_domestic_cogs(
            product_code=self.pc_freight,
            origin_zone='POM',
            destination_zone='LAE',
            agent=agent,
            currency='PGK',
            rate_per_kg=Decimal('7.00'),
            min_charge=Decimal('100.00'),
            valid_from=self.valid_from,
            valid_until=self.valid_until,
        )

        engine = DomesticPricingEngine(
            cogs_origin='POM',
            destination='LAE',
            weight_kg=50,
            service_scope='A2A',
        )

        with self.assertRaises(RateAmbiguityError):
            engine.calculate_quote()


class DomesticWeightBreaksTest(DomesticEngineTestCase):
    """Test tiered weight break pricing."""
    
    def setUp(self):
        """Create freight rates with weight breaks."""
        weight_breaks = [
            {"min_kg": 0, "rate": "8.00"},
            {"min_kg": 50, "rate": "7.50"},
            {"min_kg": 100, "rate": "7.00"},
            {"min_kg": 500, "rate": "6.00"},
        ]
        create_validated_domestic_cogs(
            product_code=self.pc_freight,
            origin_zone='POM',
            destination_zone='HGU',
            carrier=self.carrier_px,
            currency='PGK',
            weight_breaks=weight_breaks,
            valid_from=self.valid_from,
            valid_until=self.valid_until
        )
        create_validated_domestic_sell(
            product_code=self.pc_freight,
            origin_zone='POM',
            destination_zone='HGU',
            currency='PGK',
            weight_breaks=weight_breaks,
            valid_from=self.valid_from,
            valid_until=self.valid_until
        )
    
    def test_weight_break_tier_selection(self):
        """Test correct tier is selected based on weight."""
        engine = DomesticPricingEngine(
            cogs_origin='POM',
            destination='HGU',
            weight_kg=75,
            service_scope='A2A'
        )
        result = engine.calculate_quote()
        self.assertEqual(result.cogs_breakdown[0].amount, Decimal('562.50'))


class DomesticSurchargeTest(DomesticEngineTestCase):
    """Test surcharge application."""
    
    def setUp(self):
        """Create freight rates and surcharges."""
        create_validated_domestic_cogs(
            product_code=self.pc_freight,
            origin_zone='POM',
            destination_zone='LAE',
            carrier=self.carrier_px,
            currency='PGK',
            rate_per_kg=Decimal('6.50'),
            valid_from=self.valid_from,
            valid_until=self.valid_until
        )
        create_validated_domestic_sell(
            product_code=self.pc_freight,
            origin_zone='POM',
            destination_zone='LAE',
            currency='PGK',
            rate_per_kg=Decimal('8.00'),
            valid_from=self.valid_from,
            valid_until=self.valid_until
        )
        
        # Flat Doc Fee Surcharge
        create_validated_surcharge(
            product_code=self.pc_doc_fee,
            rate_side='COGS',
            service_type='DOMESTIC_AIR',
            rate_type='FLAT',
            amount=Decimal('25.00'),
            currency='PGK',
            valid_from=self.valid_from,
            valid_until=self.valid_until
        )
        create_validated_surcharge(
            product_code=self.pc_doc_fee,
            rate_side='SELL',
            service_type='DOMESTIC_AIR',
            rate_type='FLAT',
            amount=Decimal('35.00'),
            currency='PGK',
            valid_from=self.valid_from,
            valid_until=self.valid_until
        )
        
        # Per-KG Fuel Surcharge
        create_validated_surcharge(
            product_code=self.pc_fuel,
            rate_side='COGS',
            service_type='DOMESTIC_AIR',
            rate_type='PER_KG',
            amount=Decimal('0.20'),
            currency='PGK',
            valid_from=self.valid_from,
            valid_until=self.valid_until
        )
        create_validated_surcharge(
            product_code=self.pc_fuel,
            rate_side='SELL',
            service_type='DOMESTIC_AIR',
            rate_type='PER_KG',
            amount=Decimal('0.30'),
            currency='PGK',
            valid_from=self.valid_from,
            valid_until=self.valid_until
        )
    
    def test_flat_surcharge_applied(self):
        engine = DomesticPricingEngine(
            cogs_origin='POM',
            destination='LAE',
            weight_kg=100,
            service_scope='A2A'
        )
        result = engine.calculate_quote()
        self.assertEqual(len(result.cogs_breakdown), 3)
        
        doc_cogs = next((c for c in result.cogs_breakdown if c.product_code == 'DOM-DOC'), None)
        self.assertEqual(doc_cogs.amount, Decimal('25.00'))


class DomesticCommodityRuleSelectionTest(DomesticEngineTestCase):
    def setUp(self):
        create_validated_domestic_cogs(
            product_code=self.pc_freight,
            origin_zone='POM',
            destination_zone='LAE',
            carrier=self.carrier_px,
            currency='PGK',
            rate_per_kg=Decimal('6.50'),
            valid_from=self.valid_from,
            valid_until=self.valid_until
        )
        create_validated_domestic_sell(
            product_code=self.pc_freight,
            origin_zone='POM',
            destination_zone='LAE',
            currency='PGK',
            rate_per_kg=Decimal('8.00'),
            valid_from=self.valid_from,
            valid_until=self.valid_until
        )

        self.pc_live = get_or_create_test_product(
            id=3009,
            code='DOM-AVI-HANDLING',
            domain='DOMESTIC',
            category='HANDLING',
            is_gst_applicable=True,
            default_unit='SHIPMENT'
        )
        self.pc_express = get_or_create_test_product(
            id=3010,
            code='DOM-EXPRESS',
            domain='DOMESTIC',
            category='SURCHARGE',
            is_gst_applicable=True,
            default_unit='PERCENT'
        )
        CommodityChargeRule.objects.create(
            shipment_type='DOMESTIC',
            service_scope='A2A',
            commodity_code='SCR',
            product_code=self.pc_express,
            leg='MAIN',
            trigger_mode='AUTO',
            origin_code='POM',
            destination_code='LAE',
            effective_from=self.valid_from,
            effective_to=self.valid_until,
        )
        create_validated_surcharge(
            product_code=self.pc_express,
            rate_side='SELL',
            service_type='DOMESTIC_AIR',
            rate_type='PERCENT',
            amount=Decimal('100.00'),
            currency='PGK',
            valid_from=self.valid_from,
            valid_until=self.valid_until
        )
        CommodityChargeRule.objects.create(
            shipment_type='DOMESTIC',
            service_scope='A2A',
            commodity_code='AVI',
            product_code=self.pc_live,
            leg='MAIN',
            trigger_mode='AUTO',
            origin_code='POM',
            destination_code='LAE',
            effective_from=self.valid_from,
            effective_to=self.valid_until,
        )
        create_validated_surcharge(
            product_code=self.pc_live,
            rate_side='SELL',
            service_type='DOMESTIC_AIR',
            rate_type='FLAT',
            amount=Decimal('75.00'),
            currency='PGK',
            valid_from=self.valid_from,
            valid_until=self.valid_until
        )

    def test_domestic_engine_only_includes_matching_commodity_surcharge(self):
        commodity_result = DomesticPricingEngine(
            cogs_origin='POM',
            destination='LAE',
            weight_kg=20,
            service_scope='A2A',
            commodity_code='AVI'
        ).calculate_quote()

        commodity_codes = {item.product_code for item in commodity_result.sell_breakdown}
        self.assertIn('DOM-AVI-HANDLING', commodity_codes)
