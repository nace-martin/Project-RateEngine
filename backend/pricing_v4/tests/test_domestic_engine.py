# backend/pricing_v4/tests/test_domestic_engine.py
"""
Domestic Pricing Engine Tests

Tests the DomesticPricingEngine for:
1. Basic freight calculation
2. Weight break tiered pricing
3. Surcharge application (FLAT, PER_KG)
4. Minimum charge enforcement
5. Service scope validation (Door availability)
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


EXPECTED_QUOTE_RESULT_FIELDS = {field.name for field in fields(QuoteResult)}
EXPECTED_LINE_ITEM_FIELDS = {field.name for field in fields(QuoteLineItem)}


class DomesticEngineTestCase(TestCase):
    """Base test case with common setup for Domestic Engine tests."""
    
    @classmethod
    def setUpTestData(cls):
        """Create ProductCodes and seed data for domestic tests."""
        # Create Domestic ProductCodes (3xxx range)
        cls.pc_freight = ProductCode.objects.create(
            id=3001,
            code='DOM-FRT-AIR',
            description='Domestic Air Freight',
            domain='DOMESTIC',
            category='FREIGHT',
            is_gst_applicable=True,
            gst_rate=Decimal('0.10'),
            gl_revenue_code='4100',
            gl_cost_code='5100',
            default_unit='KG'
        )
        cls.pc_doc_fee = ProductCode.objects.create(
            id=3002,
            code='DOM-DOC',
            description='Documentation Fee',
            domain='DOMESTIC',
            category='DOCUMENTATION',
            is_gst_applicable=True,
            gst_rate=Decimal('0.10'),
            gl_revenue_code='4200',
            gl_cost_code='5200',
            default_unit='SHIPMENT'
        )
        cls.pc_fuel = ProductCode.objects.create(
            id=3003,
            code='DOM-FSC',
            description='Fuel Surcharge',
            domain='DOMESTIC',
            category='SURCHARGE',
            is_gst_applicable=True,
            gst_rate=Decimal('0.10'),
            gl_revenue_code='4300',
            gl_cost_code='5300',
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
        self.cogs = DomesticCOGS.objects.create(
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
        self.sell = DomesticSellRate.objects.create(
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
        
        # COGS: 50kg * 6.50 = 325.00
        # SELL: 50kg * 8.00 = 400.00
        self.assertEqual(len(result.cogs_breakdown), 1)
        self.assertEqual(len(result.sell_breakdown), 1)
        self.assertEqual(len(result.line_items), 1)
        
        self.assertEqual(result.cogs_breakdown[0].amount, Decimal('325.00'))
        self.assertEqual(result.sell_breakdown[0].amount, Decimal('400.00'))
        self.assertEqual(result.total_cost_pgk, Decimal('325.00'))
        self.assertEqual(result.total_sell_pgk, Decimal('400.00'))
        self.assertIn('service_in_PNG', result.tax_breakdown)
        self.assertEqual(set(result.__dict__.keys()), EXPECTED_QUOTE_RESULT_FIELDS)
        self.assertEqual(set(result.line_items[0].__dict__.keys()), EXPECTED_LINE_ITEM_FIELDS)
        self.assertEqual(result.line_items[0].rule_family, CALCULATION_MIN_OR_PER_UNIT)
    
    def test_minimum_charge_enforcement(self):
        """Test that minimum charge is applied for small shipments."""
        engine = DomesticPricingEngine(
            cogs_origin='POM',
            destination='LAE',
            weight_kg=10,  # Small shipment
            service_scope='A2A'
        )
        result = engine.calculate_quote()
        
        # COGS: 10kg * 6.50 = 65.00 < min 100.00 -> 100.00
        # SELL: 10kg * 8.00 = 80.00 < min 120.00 -> 120.00
        self.assertEqual(result.cogs_breakdown[0].amount, Decimal('100.00'))
        self.assertEqual(result.sell_breakdown[0].amount, Decimal('120.00'))
    
    def test_no_rates_emits_missing_placeholder(self):
        """Test that missing routes emit is_rate_missing=True placeholder instead of empty breakdowns."""
        engine = DomesticPricingEngine(
            cogs_origin='POM',
            destination='WEW',  # No rates seeded
            weight_kg=50,
            service_scope='A2A'
        )
        result = engine.calculate_quote()
        
        # [FIX 🔴] Missing freight should emit a placeholder, not be silently dropped.
        # cogs_breakdown and sell_breakdown now include is_rate_missing items.
        self.assertEqual(len(result.cogs_breakdown), 1)
        self.assertEqual(len(result.sell_breakdown), 1)
        self.assertEqual(result.cogs_breakdown[0].amount, Decimal('0'))
        self.assertEqual(result.cogs_breakdown[0].product_code, 'DOM-FRT-AIR')
        
        # The placeholder line item should be excluded from totals
        freight_line = next((li for li in result.line_items if li.product_code == 'DOM-FRT-AIR'), None)
        self.assertIsNotNone(freight_line)
        self.assertTrue(freight_line.is_rate_missing)
        self.assertFalse(freight_line.included_in_total)
        self.assertEqual(result.tax_breakdown, {'service_in_PNG': Decimal('0.00')})


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
        self.cogs = DomesticCOGS.objects.create(
            product_code=self.pc_freight,
            origin_zone='POM',
            destination_zone='HGU',
            carrier=self.carrier_px,
            currency='PGK',
            weight_breaks=weight_breaks,
            valid_from=self.valid_from,
            valid_until=self.valid_until
        )
        self.sell = DomesticSellRate.objects.create(
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
        # 75kg should use 50kg tier (7.50/kg)
        engine = DomesticPricingEngine(
            cogs_origin='POM',
            destination='HGU',
            weight_kg=75,
            service_scope='A2A'
        )
        result = engine.calculate_quote()
        
        # 75 * 7.50 = 562.50
        self.assertEqual(result.cogs_breakdown[0].amount, Decimal('562.50'))
        self.assertEqual(result.line_items[0].rule_family, CALCULATION_TIERED_BREAK)
        
    def test_highest_weight_break(self):
        """Test that highest tier is used for heavy shipments."""
        engine = DomesticPricingEngine(
            cogs_origin='POM',
            destination='HGU',
            weight_kg=600,  # Above 500kg tier
            service_scope='A2A'
        )
        result = engine.calculate_quote()
        
        # 600 * 6.00 = 3600.00
        self.assertEqual(result.cogs_breakdown[0].amount, Decimal('3600.00'))


class DomesticSurchargeTest(DomesticEngineTestCase):
    """Test surcharge application."""
    
    def setUp(self):
        """Create freight rates and surcharges."""
        # Freight
        DomesticCOGS.objects.create(
            product_code=self.pc_freight,
            origin_zone='POM',
            destination_zone='LAE',
            carrier=self.carrier_px,
            currency='PGK',
            rate_per_kg=Decimal('6.50'),
            valid_from=self.valid_from,
            valid_until=self.valid_until
        )
        DomesticSellRate.objects.create(
            product_code=self.pc_freight,
            origin_zone='POM',
            destination_zone='LAE',
            currency='PGK',
            rate_per_kg=Decimal('8.00'),
            valid_from=self.valid_from,
            valid_until=self.valid_until
        )
        
        # Flat Doc Fee Surcharge (COGS & SELL)
        Surcharge.objects.create(
            product_code=self.pc_doc_fee,
            rate_side='COGS',
            service_type='DOMESTIC_AIR',
            rate_type='FLAT',
            amount=Decimal('25.00'),
            currency='PGK',
            valid_from=self.valid_from,
            valid_until=self.valid_until,
            is_active=True
        )
        Surcharge.objects.create(
            product_code=self.pc_doc_fee,
            rate_side='SELL',
            service_type='DOMESTIC_AIR',
            rate_type='FLAT',
            amount=Decimal('35.00'),
            currency='PGK',
            valid_from=self.valid_from,
            valid_until=self.valid_until,
            is_active=True
        )
        
        # Per-KG Fuel Surcharge (COGS & SELL)
        Surcharge.objects.create(
            product_code=self.pc_fuel,
            rate_side='COGS',
            service_type='DOMESTIC_AIR',
            rate_type='PER_KG',
            amount=Decimal('0.20'),
            currency='PGK',
            valid_from=self.valid_from,
            valid_until=self.valid_until,
            is_active=True
        )
        Surcharge.objects.create(
            product_code=self.pc_fuel,
            rate_side='SELL',
            service_type='DOMESTIC_AIR',
            rate_type='PER_KG',
            amount=Decimal('0.30'),
            currency='PGK',
            valid_from=self.valid_from,
            valid_until=self.valid_until,
            is_active=True
        )
    
    def test_flat_surcharge_applied(self):
        """Test flat surcharges are added to quote."""
        engine = DomesticPricingEngine(
            cogs_origin='POM',
            destination='LAE',
            weight_kg=100,
            service_scope='A2A'
        )
        result = engine.calculate_quote()
        
        # Should have Freight + Doc Fee + Fuel = 3 lines each
        self.assertEqual(len(result.cogs_breakdown), 3)
        self.assertEqual(len(result.sell_breakdown), 3)
        
        # Find Doc Fee line
        doc_cogs = next((c for c in result.cogs_breakdown if c.product_code == 'DOM-DOC'), None)
        doc_sell = next((c for c in result.sell_breakdown if c.product_code == 'DOM-DOC'), None)
        
        self.assertIsNotNone(doc_cogs)
        self.assertIsNotNone(doc_sell)
        self.assertEqual(doc_cogs.amount, Decimal('25.00'))
        self.assertEqual(doc_sell.amount, Decimal('35.00'))
        doc_line = next((line for line in result.line_items if line.product_code == 'DOM-DOC'), None)
        self.assertIsNotNone(doc_line)
        self.assertEqual(doc_line.rule_family, CALCULATION_FLAT)
    
    def test_per_kg_surcharge_applied(self):
        """Test per-kg surcharges are calculated correctly."""
        engine = DomesticPricingEngine(
            cogs_origin='POM',
            destination='LAE',
            weight_kg=100,
            service_scope='A2A'
        )
        result = engine.calculate_quote()
        
        # Find Fuel line
        fuel_cogs = next((c for c in result.cogs_breakdown if c.product_code == 'DOM-FSC'), None)
        fuel_sell = next((c for c in result.sell_breakdown if c.product_code == 'DOM-FSC'), None)
        
        self.assertIsNotNone(fuel_cogs)
        self.assertIsNotNone(fuel_sell)
        # 100kg * 0.20 = 20.00, 100kg * 0.30 = 30.00
        self.assertEqual(fuel_cogs.amount, Decimal('20.00'))
        self.assertEqual(fuel_sell.amount, Decimal('30.00'))
    
    def test_totals_include_all_charges(self):
        """Test that totals sum freight + surcharges."""
        engine = DomesticPricingEngine(
            cogs_origin='POM',
            destination='LAE',
            weight_kg=100,
            service_scope='A2A'
        )
        result = engine.calculate_quote()
        
        # COGS: Freight 650 + Doc 25 + Fuel 20 = 695
        # SELL: Freight 800 + Doc 35 + Fuel 30 = 865
        self.assertEqual(result.total_cost, Decimal('695.00'))
        self.assertEqual(result.total_sell, Decimal('865.00'))

    def test_surcharges_only_use_rows_valid_for_quote_date(self):
        Surcharge.objects.create(
            product_code=self.pc_doc_fee,
            rate_side='COGS',
            service_type='DOMESTIC_AIR',
            rate_type='FLAT',
            amount=Decimal('99.00'),
            currency='PGK',
            valid_from=self.valid_from - timedelta(days=400),
            valid_until=self.valid_from - timedelta(days=200),
            is_active=True
        )
        Surcharge.objects.create(
            product_code=self.pc_doc_fee,
            rate_side='SELL',
            service_type='DOMESTIC_AIR',
            rate_type='FLAT',
            amount=Decimal('101.00'),
            currency='PGK',
            valid_from=self.valid_from - timedelta(days=400),
            valid_until=self.valid_from - timedelta(days=200),
            is_active=True
        )

        engine = DomesticPricingEngine(
            cogs_origin='POM',
            destination='LAE',
            weight_kg=100,
            service_scope='A2A',
            quote_date=self.valid_from,
        )
        result = engine.calculate_quote()

        doc_cogs = next((c for c in result.cogs_breakdown if c.product_code == 'DOM-DOC'), None)
        doc_sell = next((c for c in result.sell_breakdown if c.product_code == 'DOM-DOC'), None)

        self.assertEqual(doc_cogs.amount, Decimal('25.00'))
        self.assertEqual(doc_sell.amount, Decimal('35.00'))


class DomesticServiceScopeValidationTest(DomesticEngineTestCase):
    """Test service scope validation (Door availability)."""
    
    def test_door_service_allowed_in_pom(self):
        """Test D2D is allowed from POM."""
        # Should not raise
        engine = DomesticPricingEngine(
            cogs_origin='POM',
            destination='LAE',
            weight_kg=50,
            service_scope='D2D'
        )
        self.assertEqual(engine.service_scope, 'D2D')
    
    def test_door_service_not_allowed_in_small_port(self):
        """Test D2D raises error for non-DOOR ports."""
        with self.assertRaises(ValueError) as context:
            DomesticPricingEngine(
                cogs_origin='POM',
                destination='WEW',  # Not a DOOR_PORT
                weight_kg=50,
                service_scope='D2D'
            )
        self.assertIn('Delivery not available', str(context.exception))
    
    def test_origin_door_not_allowed_in_small_port(self):
        """Test D2A raises error if origin is not a DOOR port."""
        with self.assertRaises(ValueError) as context:
            DomesticPricingEngine(
                cogs_origin='HGU',  # Not a DOOR_PORT
                destination='LAE',
                weight_kg=50,
                service_scope='D2A'
            )
        self.assertIn('Pickup not available', str(context.exception))


class DomesticCommodityRuleSelectionTest(DomesticEngineTestCase):
    def setUp(self):
        DomesticCOGS.objects.create(
            product_code=self.pc_freight,
            origin_zone='POM',
            destination_zone='LAE',
            carrier=self.carrier_px,
            currency='PGK',
            rate_per_kg=Decimal('6.50'),
            valid_from=self.valid_from,
            valid_until=self.valid_until
        )
        DomesticSellRate.objects.create(
            product_code=self.pc_freight,
            origin_zone='POM',
            destination_zone='LAE',
            currency='PGK',
            rate_per_kg=Decimal('8.00'),
            valid_from=self.valid_from,
            valid_until=self.valid_until
        )

        self.pc_live = ProductCode.objects.create(
            id=3009,
            code='DOM-AVI-HANDLING',
            description='Domestic Live Animal Handling',
            domain='DOMESTIC',
            category='HANDLING',
            is_gst_applicable=True,
            gst_rate=Decimal('0.10'),
            gl_revenue_code='4400',
            gl_cost_code='5400',
            default_unit='SHIPMENT'
        )
        CommodityChargeRule.objects.create(
            shipment_type='DOMESTIC',
            service_scope='A2A',
            commodity_code='SCR',
            product_code=ProductCode.objects.create(
                id=3010,
                code='DOM-EXPRESS',
                description='Domestic Express Cargo Uplift',
                domain='DOMESTIC',
                category='SURCHARGE',
                is_gst_applicable=True,
                gst_rate=Decimal('0.10'),
                gl_revenue_code='4401',
                gl_cost_code='5401',
                default_unit='PERCENT'
            ),
            leg='MAIN',
            trigger_mode='AUTO',
            origin_code='POM',
            destination_code='LAE',
            effective_from=self.valid_from,
            effective_to=self.valid_until,
        )
        Surcharge.objects.create(
            product_code=ProductCode.objects.get(code='DOM-EXPRESS'),
            rate_side='SELL',
            service_type='DOMESTIC_AIR',
            rate_type='PERCENT',
            amount=Decimal('100.00'),
            currency='PGK',
            valid_from=self.valid_from,
            valid_until=self.valid_until,
            is_active=True
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
        Surcharge.objects.create(
            product_code=self.pc_live,
            rate_side='SELL',
            service_type='DOMESTIC_AIR',
            rate_type='FLAT',
            amount=Decimal('75.00'),
            currency='PGK',
            valid_from=self.valid_from,
            valid_until=self.valid_until,
            is_active=True
        )

    def test_domestic_engine_only_includes_matching_commodity_surcharge(self):
        general_result = DomesticPricingEngine(
            cogs_origin='POM',
            destination='LAE',
            weight_kg=20,
            service_scope='A2A',
            commodity_code='GCR'
        ).calculate_quote()
        commodity_result = DomesticPricingEngine(
            cogs_origin='POM',
            destination='LAE',
            weight_kg=20,
            service_scope='A2A',
            commodity_code='AVI'
        ).calculate_quote()

        general_codes = {item.product_code for item in general_result.sell_breakdown}
        commodity_codes = {item.product_code for item in commodity_result.sell_breakdown}

        self.assertNotIn('DOM-AVI-HANDLING', general_codes)
        self.assertNotIn('DOM-EXPRESS', general_codes)
        self.assertIn('DOM-AVI-HANDLING', commodity_codes)

    def test_domestic_engine_only_includes_express_for_scr(self):
        general_result = DomesticPricingEngine(
            cogs_origin='POM',
            destination='LAE',
            weight_kg=20,
            service_scope='A2A',
            commodity_code='GCR'
        ).calculate_quote()
        express_result = DomesticPricingEngine(
            cogs_origin='POM',
            destination='LAE',
            weight_kg=20,
            service_scope='A2A',
            commodity_code='SCR'
        ).calculate_quote()

        general_codes = {item.product_code for item in general_result.sell_breakdown}
        express_codes = {item.product_code for item in express_result.sell_breakdown}

        self.assertNotIn('DOM-EXPRESS', general_codes)
        self.assertIn('DOM-EXPRESS', express_codes)


class DomesticSpecialMultiplierTest(DomesticEngineTestCase):
    def setUp(self):
        DomesticCOGS.objects.create(
            product_code=self.pc_freight,
            origin_zone='POM',
            destination_zone='LAE',
            carrier=self.carrier_px,
            currency='PGK',
            rate_per_kg=Decimal('6.10'),
            valid_from=self.valid_from,
            valid_until=self.valid_until
        )
        DomesticSellRate.objects.create(
            product_code=self.pc_freight,
            origin_zone='POM',
            destination_zone='LAE',
            currency='PGK',
            rate_per_kg=Decimal('6.10'),
            valid_from=self.valid_from,
            valid_until=self.valid_until
        )

        self.pc_valuable = ProductCode.objects.create(
            id=3110,
            code='DOM-VALUABLE-TEST',
            description='Domestic Valuable Cargo Uplift',
            domain='DOMESTIC',
            category='SPECIAL',
            is_gst_applicable=True,
            gst_rate=Decimal('0.10'),
            gl_revenue_code='4410',
            gl_cost_code='5410',
            default_unit='PERCENT'
        )
        CommodityChargeRule.objects.create(
            shipment_type='DOMESTIC',
            service_scope='A2A',
            commodity_code='HVC',
            product_code=self.pc_valuable,
            leg='MAIN',
            trigger_mode='AUTO',
            origin_code='POM',
            destination_code='LAE',
            effective_from=self.valid_from,
            effective_to=self.valid_until,
        )
        Surcharge.objects.create(
            product_code=self.pc_valuable,
            rate_side='SELL',
            service_type='DOMESTIC_AIR',
            rate_type='PERCENT',
            amount=Decimal('400.00'),
            currency='PGK',
            valid_from=self.valid_from,
            valid_until=self.valid_until,
            is_active=True
        )

    def test_percent_special_surcharge_uses_freight_as_basis(self):
        engine = DomesticPricingEngine(
            cogs_origin='POM',
            destination='LAE',
            weight_kg=10,
            service_scope='A2A',
            commodity_code='HVC'
        )
        result = engine.calculate_quote()

        valuable_line = next((c for c in result.sell_breakdown if c.product_code == 'DOM-VALUABLE-TEST'), None)
        freight_line = next((c for c in result.sell_breakdown if c.product_code == 'DOM-FRT-AIR'), None)

        self.assertIsNotNone(freight_line)
        self.assertIsNotNone(valuable_line)
        self.assertEqual(freight_line.amount, Decimal('61.00'))
        self.assertEqual(valuable_line.amount, Decimal('244.00'))
