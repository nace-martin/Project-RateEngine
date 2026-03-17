# backend/pricing_v4/tests/test_export_engine.py
"""
Export Pricing Engine Tests

Tests the ExportPricingEngine for FCY margin reporting on PREPAID quotes.
"""
from decimal import Decimal
from datetime import date, timedelta
from django.test import TestCase

from pricing_v4.models import ProductCode, Agent, LocalCOGSRate, LocalSellRate
from pricing_v4.engine.export_engine import ExportPricingEngine, PaymentTerm


class ExportEngineTestCase(TestCase):
    """Base test case with common setup for Export Engine tests."""

    @classmethod
    def setUpTestData(cls):
        cls.pc_clearance = ProductCode.objects.create(
            id=1501,
            code='EXP-CLEAR-TEST',
            description='Export Clearance Test',
            domain='EXPORT',
            category='CLEARANCE',
            is_gst_applicable=False,
            gst_rate=Decimal('0.00'),
            gl_revenue_code='4300',
            gl_cost_code='5300',
            default_unit='SHIPMENT'
        )

        cls.agent = Agent.objects.create(
            code='TEST-AGENT',
            name='Test Agent',
            country_code='PG',
            agent_type='ORIGIN'
        )

        cls.valid_from = date.today() - timedelta(days=1)
        cls.valid_until = date.today() + timedelta(days=365)


class ExportPrepaidFcyMarginTest(ExportEngineTestCase):
    """Test margin reporting for PREPAID with FCY sell rates."""

    def setUp(self):
        LocalCOGSRate.objects.create(
            product_code=self.pc_clearance,
            location='POM',
            direction='EXPORT',
            agent=self.agent,
            currency='PGK',
            rate_type='FIXED',
            amount=Decimal('100.00'),
            valid_from=self.valid_from,
            valid_until=self.valid_until
        )

        LocalSellRate.objects.create(
            product_code=self.pc_clearance,
            location='POM',
            direction='EXPORT',
            payment_term='PREPAID',
            currency='USD',
            rate_type='FIXED',
            amount=Decimal('80.00'),
            valid_from=self.valid_from,
            valid_until=self.valid_until
        )

    def test_prepaid_fcy_margin_uses_converted_cost(self):
        engine = ExportPricingEngine(
            quote_date=date.today(),
            origin='POM',
            destination='BNE',
            chargeable_weight_kg=Decimal('1'),
            payment_term=PaymentTerm.PREPAID,
            tt_sell=Decimal('2.00'),
            caf_rate=Decimal('0.00'),
            destination_currency='USD'
        )

        result = engine.calculate_quote([self.pc_clearance.id])
        self.assertEqual(len(result.lines), 1)
        line = result.lines[0]

        # Cost remains PGK, sell is FCY (USD). Margin uses cost converted to FCY.
        self.assertEqual(line.sell_currency, 'USD')
        self.assertEqual(line.sell_amount, Decimal('80.00'))
        self.assertEqual(line.cost_amount, Decimal('100.00'))
        self.assertEqual(line.margin_amount, Decimal('30.00'))
        self.assertEqual(line.margin_percent, Decimal('60.00'))


class ExportLocalSellRateSelectionTest(ExportEngineTestCase):
    """Ensure local sell lookup respects both payment term and target currency."""

    def setUp(self):
        LocalCOGSRate.objects.create(
            product_code=self.pc_clearance,
            location='POM',
            direction='EXPORT',
            agent=self.agent,
            currency='PGK',
            rate_type='FIXED',
            amount=Decimal('100.00'),
            valid_from=self.valid_from,
            valid_until=self.valid_until
        )
        # Legacy-style row that should NOT win for non-AU prepaid quotes.
        LocalSellRate.objects.create(
            product_code=self.pc_clearance,
            location='POM',
            direction='EXPORT',
            payment_term='PREPAID',
            currency='PGK',
            rate_type='FIXED',
            amount=Decimal('250.00'),
            valid_from=self.valid_from,
            valid_until=self.valid_until
        )
        # Correct market-currency row that should be selected.
        LocalSellRate.objects.create(
            product_code=self.pc_clearance,
            location='POM',
            direction='EXPORT',
            payment_term='ANY',
            currency='USD',
            rate_type='FIXED',
            amount=Decimal('90.00'),
            valid_from=self.valid_from,
            valid_until=self.valid_until
        )

    def test_prepaid_non_au_prefers_market_currency_over_term_only_pgk(self):
        engine = ExportPricingEngine(
            quote_date=date.today(),
            origin='POM',
            destination='HKG',
            chargeable_weight_kg=Decimal('1'),
            payment_term=PaymentTerm.PREPAID,
            tt_sell=Decimal('2.50'),
            caf_rate=Decimal('0.00'),
            destination_currency='USD'
        )

        result = engine.calculate_quote([self.pc_clearance.id])
        self.assertEqual(len(result.lines), 1)
        line = result.lines[0]
        self.assertEqual(line.sell_currency, 'USD')
        self.assertEqual(line.sell_amount, Decimal('90.00'))


class ExportPercentRateSelectionTest(ExportEngineTestCase):
    """Percent ProductCodes must not pick incompatible FIXED placeholder rows."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.pc_pickup = ProductCode.objects.create(
            id=1502,
            code='EXP-PICKUP-TEST',
            description='Export Pickup Test',
            domain='EXPORT',
            category='CARTAGE',
            is_gst_applicable=False,
            gst_rate=Decimal('0.00'),
            gl_revenue_code='4301',
            gl_cost_code='5301',
            default_unit=ProductCode.UNIT_KG,
        )
        cls.pc_fsc_pickup = ProductCode.objects.create(
            id=1503,
            code='EXP-FSC-PICKUP-TEST',
            description='Export Pickup Fuel Surcharge Test',
            domain='EXPORT',
            category='SURCHARGE',
            is_gst_applicable=False,
            gst_rate=Decimal('0.00'),
            gl_revenue_code='4302',
            gl_cost_code='5302',
            default_unit=ProductCode.UNIT_PERCENT,
            percent_of_product_code=cls.pc_pickup,
        )

    def setUp(self):
        LocalSellRate.objects.create(
            product_code=self.pc_pickup,
            location='POM',
            direction='EXPORT',
            payment_term='ANY',
            currency='USD',
            rate_type='PER_KG',
            amount=Decimal('0.25'),
            valid_from=self.valid_from,
            valid_until=self.valid_until
        )
        # Incompatible placeholder row that should be ignored for percent ProductCodes.
        LocalSellRate.objects.create(
            product_code=self.pc_fsc_pickup,
            location='POM',
            direction='EXPORT',
            payment_term='ANY',
            currency='USD',
            rate_type='FIXED',
            amount=Decimal('0.00'),
            valid_from=self.valid_from,
            valid_until=self.valid_until
        )
        # Compatible percent row that should be selected.
        LocalSellRate.objects.create(
            product_code=self.pc_fsc_pickup,
            location='POM',
            direction='EXPORT',
            payment_term='PREPAID',
            currency='PGK',
            rate_type='PERCENT',
            amount=Decimal('10.00'),
            percent_of_product_code=self.pc_pickup,
            valid_from=self.valid_from,
            valid_until=self.valid_until
        )

    def test_percent_product_uses_percent_rate_not_fixed_placeholder(self):
        engine = ExportPricingEngine(
            quote_date=date.today(),
            origin='POM',
            destination='SIN',
            chargeable_weight_kg=Decimal('100'),
            payment_term=PaymentTerm.PREPAID,
            tt_sell=Decimal('2.50'),
            caf_rate=Decimal('0.00'),
            destination_currency='USD'
        )

        result = engine.calculate_quote([self.pc_pickup.id, self.pc_fsc_pickup.id])
        by_code = {line.product_code: line for line in result.lines}

        self.assertIn(self.pc_pickup.code, by_code)
        self.assertIn(self.pc_fsc_pickup.code, by_code)
        self.assertEqual(by_code[self.pc_pickup.code].sell_amount, Decimal('25.00'))
        self.assertEqual(by_code[self.pc_fsc_pickup.code].sell_amount, Decimal('2.50'))


class ExportProductCodeSelectionTest(TestCase):
    def test_general_export_scope_does_not_auto_include_special_cargo_fees(self):
        codes = ExportPricingEngine.get_product_codes(is_dg=False, service_scope='D2A')

        self.assertIn(1020, codes)
        self.assertNotIn(1071, codes)
        self.assertNotIn(1072, codes)
