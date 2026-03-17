# backend/pricing_v4/tests/test_import_engine.py
"""
Import Pricing Engine Tests

Tests the ImportPricingEngine for:
1. Payment Term / Quote Currency determination
2. Service Scope / Active Legs
3. FX Conversion (FCY->PGK and PGK->FCY)
4. Margin application
5. CAF adjustment
"""
from decimal import Decimal
from datetime import date, timedelta
from django.test import TestCase

from pricing_v4.models import (
    CommodityChargeRule,
    ProductCode, Agent,
    ImportCOGS, LocalCOGSRate, LocalSellRate
)
from pricing_v4.engine.import_engine import (
    ImportPricingEngine, PaymentTerm, ServiceScope
)


class ImportEngineTestCase(TestCase):
    """Base test case with common setup for Import Engine tests."""
    
    @classmethod
    def setUpTestData(cls):
        """Create ProductCodes and seed data for import tests."""
        # Create Import ProductCodes (2xxx range)
        cls.pc_freight = ProductCode.objects.create(
            id=2001,
            code='IMP-FRT-AIR',
            description='Import Air Freight',
            domain='IMPORT',
            category='FREIGHT',
            is_gst_applicable=True,
            gst_rate=Decimal('0.10'),
            gl_revenue_code='4100',
            gl_cost_code='5100',
            default_unit='KG'
        )
        cls.pc_clearance = ProductCode.objects.create(
            id=2002,
            code='IMP-CLEAR',
            description='Import Customs Clearance',
            domain='IMPORT',
            category='CLEARANCE',
            is_gst_applicable=True,
            gst_rate=Decimal('0.10'),
            gl_revenue_code='4200',
            gl_cost_code='5200',
            default_unit='SHIPMENT'
        )
        cls.pc_cartage = ProductCode.objects.create(
            id=2003,
            code='IMP-CARTAGE-DEST',
            description='Destination Cartage',
            domain='IMPORT',
            category='CARTAGE',
            is_gst_applicable=True,
            gst_rate=Decimal('0.10'),
            gl_revenue_code='4300',
            gl_cost_code='5300',
            default_unit='SHIPMENT'
        )
        
        # Create Agent
        cls.agent_efm = Agent.objects.create(
            code='EFM-AU',
            name='EFM Australia',
            country_code='AU',
            agent_type='ORIGIN'
        )
        
        # Validity dates
        cls.valid_from = date.today() - timedelta(days=30)
        cls.valid_until = date.today() + timedelta(days=365)


class ImportQuoteCurrencyTest(ImportEngineTestCase):
    """Test quote currency determination based on payment term."""
    
    def test_collect_returns_pgk(self):
        """COLLECT payment term should quote in PGK."""
        engine = ImportPricingEngine(
            quote_date=date.today(),
            origin='SYD',
            destination='POM',
            chargeable_weight_kg=Decimal('50'),
            payment_term=PaymentTerm.COLLECT,
            service_scope=ServiceScope.A2D
        )
        self.assertEqual(engine.quote_currency, 'PGK')
    
    def test_prepaid_returns_fcy(self):
        """PREPAID payment term should default to FCY (USD) without explicit override."""
        engine = ImportPricingEngine(
            quote_date=date.today(),
            origin='SYD',
            destination='POM',
            chargeable_weight_kg=Decimal('50'),
            payment_term=PaymentTerm.PREPAID,
            service_scope=ServiceScope.A2D
        )
        self.assertEqual(engine.quote_currency, 'USD')


class ImportActiveLegTest(ImportEngineTestCase):
    """Test active leg determination based on service scope."""
    
    def test_a2a_returns_freight_only(self):
        """A2A scope should only include FREIGHT leg."""
        engine = ImportPricingEngine(
            quote_date=date.today(),
            origin='SYD',
            destination='POM',
            chargeable_weight_kg=Decimal('50'),
            payment_term=PaymentTerm.COLLECT,
            service_scope=ServiceScope.A2A
        )
        legs = engine._get_active_legs()
        self.assertEqual(legs, ['FREIGHT'])
    
    def test_a2d_returns_destination_only(self):
        """A2D scope should only include DESTINATION leg."""
        engine = ImportPricingEngine(
            quote_date=date.today(),
            origin='SYD',
            destination='POM',
            chargeable_weight_kg=Decimal('50'),
            payment_term=PaymentTerm.COLLECT,
            service_scope=ServiceScope.A2D
        )
        legs = engine._get_active_legs()
        self.assertEqual(legs, ['DESTINATION'])
    
    def test_d2d_returns_all_legs(self):
        """D2D scope should include all legs."""
        engine = ImportPricingEngine(
            quote_date=date.today(),
            origin='SYD',
            destination='POM',
            chargeable_weight_kg=Decimal('50'),
            payment_term=PaymentTerm.COLLECT,
            service_scope=ServiceScope.D2D
        )
        legs = engine._get_active_legs()
        self.assertEqual(legs, ['ORIGIN', 'FREIGHT', 'DESTINATION'])


class ImportFxConversionTest(ImportEngineTestCase):
    """Test FX conversion logic."""
    
    def setUp(self):
        """Create rates for FX testing."""
        # Import Freight COGS (AUD)
        ImportCOGS.objects.create(
            product_code=self.pc_freight,
            origin_airport='SYD',
            destination_airport='POM',
            agent=self.agent_efm,
            currency='AUD',
            rate_per_kg=Decimal('5.00'),
            valid_from=self.valid_from,
            valid_until=self.valid_until
        )
        # Destination Clearance COGS (PGK)
        LocalCOGSRate.objects.create(
            product_code=self.pc_clearance,
            location='POM',
            direction='IMPORT',
            agent=self.agent_efm,
            currency='PGK',
            rate_type='FIXED',
            amount=Decimal('350.00'),
            valid_from=self.valid_from,
            valid_until=self.valid_until
        )
        # Destination Clearance Sell (PGK)
        LocalSellRate.objects.create(
            product_code=self.pc_clearance,
            location='POM',
            direction='IMPORT',
            payment_term='COLLECT',
            currency='PGK',
            rate_type='FIXED',
            amount=Decimal('500.00'),
            valid_from=self.valid_from,
            valid_until=self.valid_until
        )
    
    def test_fcy_to_pgk_conversion(self):
        """Test FCY (AUD) to PGK conversion with CAF."""
        engine = ImportPricingEngine(
            quote_date=date.today(),
            origin='SYD',
            destination='POM',
            chargeable_weight_kg=Decimal('100'),
            payment_term=PaymentTerm.COLLECT,
            service_scope=ServiceScope.D2D,
            tt_buy=Decimal('0.35'),
            caf_rate=Decimal('0.05')
        )
        
        # 100 AUD should become:
        # effective_rate = 0.35 * (1 - 0.05) = 0.3325
        # pgk = 100 / 0.3325 = 300.75
        result = engine._convert_fcy_to_pgk(Decimal('100'))
        self.assertEqual(result, Decimal('300.75'))
    
    def test_pgk_to_fcy_conversion(self):
        """Test PGK to FCY conversion with CAF."""
        engine = ImportPricingEngine(
            quote_date=date.today(),
            origin='SYD',
            destination='POM',
            chargeable_weight_kg=Decimal('100'),
            payment_term=PaymentTerm.PREPAID,
            service_scope=ServiceScope.A2D,
            tt_sell=Decimal('0.36'),
            caf_rate=Decimal('0.05')
        )
        
        # 500 PGK should become:
        # effective_rate = 0.36 * (1 - 0.05) = 0.342
        # fcy = 500 * 0.342 = 171.00
        result = engine._convert_pgk_to_fcy(Decimal('500'))
        self.assertEqual(result, Decimal('171.00'))


class ImportMarginTest(ImportEngineTestCase):
    """Test margin application."""
    
    def test_margin_applied_to_cost_plus(self):
        """Test margin is applied correctly to cost-plus calculation."""
        engine = ImportPricingEngine(
            quote_date=date.today(),
            origin='SYD',
            destination='POM',
            chargeable_weight_kg=Decimal('100'),
            payment_term=PaymentTerm.COLLECT,
            service_scope=ServiceScope.A2A,
            margin_rate=Decimal('0.20')
        )
        
        # 100 cost + 20% margin = 120
        result = engine._apply_margin(Decimal('100'))
        self.assertEqual(result, Decimal('120.00'))


class ImportFullQuoteTest(ImportEngineTestCase):
    """Test full quote calculation."""
    
    def setUp(self):
        """Create complete rate set for full quote test."""
        # Freight COGS
        ImportCOGS.objects.create(
            product_code=self.pc_freight,
            origin_airport='SYD',
            destination_airport='POM',
            agent=self.agent_efm,
            currency='AUD',
            rate_per_kg=Decimal('5.00'),
            min_charge=Decimal('100.00'),
            valid_from=self.valid_from,
            valid_until=self.valid_until
        )
        # Clearance COGS
        LocalCOGSRate.objects.create(
            product_code=self.pc_clearance,
            location='POM',
            direction='IMPORT',
            agent=self.agent_efm,
            currency='PGK',
            rate_type='FIXED',
            amount=Decimal('350.00'),
            valid_from=self.valid_from,
            valid_until=self.valid_until
        )
        # Clearance Sell
        LocalSellRate.objects.create(
            product_code=self.pc_clearance,
            location='POM',
            direction='IMPORT',
            payment_term='COLLECT',
            currency='PGK',
            rate_type='FIXED',
            amount=Decimal('500.00'),
            valid_from=self.valid_from,
            valid_until=self.valid_until
        )
        # Cartage COGS
        LocalCOGSRate.objects.create(
            product_code=self.pc_cartage,
            location='POM',
            direction='IMPORT',
            agent=self.agent_efm,
            currency='PGK',
            rate_type='FIXED',
            amount=Decimal('150.00'),
            valid_from=self.valid_from,
            valid_until=self.valid_until
        )
        # Cartage Sell
        LocalSellRate.objects.create(
            product_code=self.pc_cartage,
            location='POM',
            direction='IMPORT',
            payment_term='COLLECT',
            currency='PGK',
            rate_type='FIXED',
            amount=Decimal('200.00'),
            valid_from=self.valid_from,
            valid_until=self.valid_until
        )
    
    def test_a2d_collect_quote(self):
        """Test A2D Collect quote (destination only, PGK)."""
        engine = ImportPricingEngine(
            quote_date=date.today(),
            origin='SYD',
            destination='POM',
            chargeable_weight_kg=Decimal('50'),
            payment_term=PaymentTerm.COLLECT,
            service_scope=ServiceScope.A2D
        )
        result = engine.calculate_quote()
        
        # A2D = DESTINATION only
        self.assertEqual(result.quote_currency, 'PGK')
        self.assertEqual(len(result.origin_lines), 0)
        self.assertEqual(len(result.freight_lines), 0)
        # Should have clearance and cartage
        self.assertGreaterEqual(len(result.destination_lines), 1)
    
    def test_quote_result_structure(self):
        """Test quote result has correct structure."""
        engine = ImportPricingEngine(
            quote_date=date.today(),
            origin='SYD',
            destination='POM',
            chargeable_weight_kg=Decimal('50'),
            payment_term=PaymentTerm.COLLECT,
            service_scope=ServiceScope.A2D
        )
        result = engine.calculate_quote()
        
        # Verify result structure
        self.assertEqual(result.origin, 'SYD')
        self.assertEqual(result.destination, 'POM')
        self.assertEqual(result.direction, 'IMPORT')
        self.assertEqual(result.payment_term, 'COLLECT')
        self.assertEqual(result.service_scope, 'A2D')
        self.assertIsNotNone(result.fx_rate_used)
        self.assertIsNotNone(result.caf_rate)


class ImportD2DOriginLocalFallbackTest(ImportEngineTestCase):
    """
    Regression guard:
    Import ORIGIN local charges must be resolvable from LocalCOGSRate.
    """

    def setUp(self):
        self.pc_doc_origin = ProductCode.objects.create(
            id=2010,
            code='IMP-DOC-ORIGIN',
            description='Import Documentation Origin',
            domain='IMPORT',
            category='DOCUMENTATION',
            is_gst_applicable=True,
            gst_rate=Decimal('0.10'),
            gl_revenue_code='4200',
            gl_cost_code='5200',
            default_unit='SHIPMENT'
        )

        # Freight lane COGS exists for linehaul
        ImportCOGS.objects.create(
            product_code=self.pc_freight,
            origin_airport='BNE',
            destination_airport='POM',
            agent=self.agent_efm,
            currency='AUD',
            rate_per_kg=Decimal('5.00'),
            valid_from=self.valid_from,
            valid_until=self.valid_until
        )

        # Import ORIGIN local charge stored in LocalCOGSRate using destination location
        # (legacy migration compatibility shape).
        LocalCOGSRate.objects.create(
            product_code=self.pc_doc_origin,
            location='POM',
            direction='IMPORT',
            agent=self.agent_efm,
            currency='AUD',
            rate_type='FIXED',
            amount=Decimal('100.00'),
            valid_from=self.valid_from,
            valid_until=self.valid_until
        )

    def test_d2d_collect_does_not_mark_origin_local_as_missing(self):
        engine = ImportPricingEngine(
            quote_date=date.today(),
            origin='BNE',
            destination='POM',
            chargeable_weight_kg=Decimal('50'),
            payment_term=PaymentTerm.COLLECT,
            service_scope=ServiceScope.D2D,
        )
        result = engine.calculate_quote()

        doc_origin_lines = [l for l in result.origin_lines if l.product_code == 'IMP-DOC-ORIGIN']
        self.assertEqual(len(doc_origin_lines), 1)
        line = doc_origin_lines[0]
        self.assertFalse(getattr(line, 'is_rate_missing', False))


class ImportCommodityRuleSelectionTest(ImportEngineTestCase):
    def setUp(self):
        self.pc_special_dest = ProductCode.objects.create(
            id=2099,
            code='IMP-AVI-DEST-TEST',
            description='Import Live Animal Destination Handling',
            domain='IMPORT',
            category='HANDLING',
            is_gst_applicable=True,
            gst_rate=Decimal('0.10'),
            gl_revenue_code='4399',
            gl_cost_code='5399',
            default_unit='SHIPMENT'
        )
        CommodityChargeRule.objects.create(
            shipment_type='IMPORT',
            service_scope='A2D',
            commodity_code='AVI',
            product_code=self.pc_special_dest,
            leg='DESTINATION',
            trigger_mode='AUTO',
            origin_code='SYD',
            destination_code='POM',
            payment_term='COLLECT',
            effective_from=self.valid_from,
            effective_to=self.valid_until,
        )
        LocalCOGSRate.objects.create(
            product_code=self.pc_special_dest,
            location='POM',
            direction='IMPORT',
            agent=self.agent_efm,
            currency='PGK',
            rate_type='FIXED',
            amount=Decimal('250.00'),
            valid_from=self.valid_from,
            valid_until=self.valid_until
        )
        LocalSellRate.objects.create(
            product_code=self.pc_special_dest,
            location='POM',
            direction='IMPORT',
            payment_term='COLLECT',
            currency='PGK',
            rate_type='FIXED',
            amount=Decimal('320.00'),
            valid_from=self.valid_from,
            valid_until=self.valid_until
        )

    def test_import_engine_only_includes_matching_commodity_rule_products(self):
        engine = ImportPricingEngine(
            quote_date=date.today(),
            origin='SYD',
            destination='POM',
            chargeable_weight_kg=Decimal('25'),
            payment_term=PaymentTerm.COLLECT,
            service_scope=ServiceScope.A2D
        )

        general_result = engine.calculate_quote(commodity_code='GCR')
        commodity_result = engine.calculate_quote(commodity_code='AVI')

        general_codes = {line.product_code for line in general_result.destination_lines}
        commodity_codes = {line.product_code for line in commodity_result.destination_lines}

        self.assertNotIn('IMP-AVI-DEST-TEST', general_codes)
        self.assertIn('IMP-AVI-DEST-TEST', commodity_codes)
