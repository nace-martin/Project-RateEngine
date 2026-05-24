# backend/pricing_v4/tests/test_export_engine.py
"""
Export Pricing Engine Tests

Tests the ExportPricingEngine for FCY margin reporting on PREPAID quotes.
"""
from decimal import Decimal
from datetime import date, timedelta
from dataclasses import fields
from django.test import TestCase

from core.charge_rules import (
    CALCULATION_LOOKUP_RATE,
    CALCULATION_PERCENT_OF_BASE,
    CALCULATION_PER_UNIT,
    CALCULATION_TIERED_BREAK,
)
from pricing_v4.models import (
    CommodityChargeRule,
    ProductCode,
    Agent,
    ExportCOGS,
    ExportSellRate,
    LocalCOGSRate,
    LocalSellRate,
    Surcharge,
)
from pricing_v4.engine.export_engine import ExportPricingEngine, PaymentTerm
from pricing_v4.engine.result_types import QuoteLineItem, QuoteResult


EXPECTED_QUOTE_RESULT_FIELDS = {field.name for field in fields(QuoteResult)}
EXPECTED_LINE_ITEM_FIELDS = {field.name for field in fields(QuoteLineItem)}


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
        cls.pc_dest_clearance = ProductCode.objects.create(
            id=1504,
            code='EXP-CLEAR-DEST-TEST',
            description='Export Destination Clearance Test',
            domain='EXPORT',
            category='CLEARANCE',
            is_gst_applicable=False,
            gst_rate=Decimal('0.00'),
            gl_revenue_code='4304',
            gl_cost_code='5304',
            default_unit='SHIPMENT',
        )
        cls.pc_freight = ProductCode.objects.create(
            id=1505,
            code='EXP-FRT-AIR-TEST',
            description='Export Air Freight Test',
            domain='EXPORT',
            category='FREIGHT',
            is_gst_applicable=False,
            gst_rate=Decimal('0.00'),
            gl_revenue_code='4305',
            gl_cost_code='5305',
            default_unit=ProductCode.UNIT_KG,
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
        self.assertEqual(len(result.line_items), 1)
        line = result.lines[0]

        # Cost remains PGK, sell is FCY (USD). Margin uses cost converted to FCY.
        self.assertEqual(line.sell_currency, 'USD')
        self.assertEqual(line.sell_amount, Decimal('80.00'))
        self.assertEqual(line.cost_amount, Decimal('100.00'))
        self.assertEqual(line.margin_amount, Decimal('30.00'))
        self.assertEqual(line.margin_percent, Decimal('60.00'))
        self.assertEqual(line.rule_family, CALCULATION_LOOKUP_RATE)
        self.assertGreater(result.total_cost_pgk, Decimal('0.00'))
        self.assertGreater(result.total_sell_pgk, Decimal('0.00'))
        self.assertFalse(result.fx_applied)
        self.assertEqual(set(result.__dict__.keys()), EXPECTED_QUOTE_RESULT_FIELDS)
        self.assertEqual(set(line.__dict__.keys()), EXPECTED_LINE_ITEM_FIELDS)


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

    def test_destination_local_export_rate_uses_destination_station(self):
        LocalSellRate.objects.create(
            product_code=self.pc_dest_clearance,
            location='SIN',
            direction='EXPORT',
            payment_term='PREPAID',
            currency='USD',
            rate_type='FIXED',
            amount=Decimal('135.00'),
            valid_from=self.valid_from,
            valid_until=self.valid_until,
        )

        engine = ExportPricingEngine(
            quote_date=date.today(),
            origin='POM',
            destination='SIN',
            chargeable_weight_kg=Decimal('1'),
            payment_term=PaymentTerm.PREPAID,
            tt_sell=Decimal('2.50'),
            caf_rate=Decimal('0.00'),
            destination_currency='USD'
        )

        result = engine.calculate_quote([self.pc_dest_clearance.id])
        self.assertEqual(len(result.lines), 1)
        line = result.lines[0]
        self.assertEqual(line.sell_currency, 'USD')
        self.assertEqual(line.sell_amount, Decimal('135.00'))


class ExportSellRateSelectionTest(ExportEngineTestCase):
    """Export freight sell lookup must not depend on database row order."""

    def setUp(self):
        ExportCOGS.objects.create(
            product_code=self.pc_freight,
            origin_airport='POM',
            destination_airport='SIN',
            agent=self.agent,
            currency='PGK',
            weight_breaks=[
                {"min_kg": 0, "rate": "9.00"},
                {"min_kg": 100, "rate": "8.50"},
            ],
            valid_from=self.valid_from,
            valid_until=self.valid_until,
        )
        # Insert an FCY row first to prove selection is not based on insertion order.
        ExportSellRate.objects.create(
            product_code=self.pc_freight,
            origin_airport='POM',
            destination_airport='SIN',
            currency='USD',
            weight_breaks=[
                {"min_kg": 0, "rate": "4.70"},
                {"min_kg": 100, "rate": "4.50"},
            ],
            min_charge=Decimal('60.00'),
            valid_from=self.valid_from,
            valid_until=self.valid_until,
        )
        ExportSellRate.objects.create(
            product_code=self.pc_freight,
            origin_airport='POM',
            destination_airport='SIN',
            currency='PGK',
            weight_breaks=[
                {"min_kg": 0, "rate": "17.65"},
                {"min_kg": 100, "rate": "13.25"},
            ],
            min_charge=Decimal('200.00'),
            valid_from=self.valid_from,
            valid_until=self.valid_until,
        )

    def test_prepaid_pgk_quote_prefers_exact_pgk_export_sell_rate(self):
        engine = ExportPricingEngine(
            quote_date=date.today(),
            origin='POM',
            destination='SIN',
            chargeable_weight_kg=Decimal('100'),
            payment_term=PaymentTerm.PREPAID,
            tt_sell=Decimal('2.78'),
            caf_rate=Decimal('0.05'),
            destination_currency='PGK',
        )

        result = engine.calculate_quote([self.pc_freight.id])
        self.assertEqual(len(result.lines), 1)
        line = result.lines[0]

        self.assertEqual(line.sell_currency, 'PGK')
        self.assertEqual(line.sell_amount, Decimal('1325.00'))
        self.assertEqual(line.rule_family, CALCULATION_TIERED_BREAK)


class ExportFxAndCollectCurrencyTest(ExportEngineTestCase):
    """Export PREPAID converts PGK sell rates to FCY; COLLECT stays PGK."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.pc_fx_freight = ProductCode.objects.create(
            id=1506,
            code='EXP-FRT-AIR-FX-TEST',
            description='Export Air Freight FX Test',
            domain='EXPORT',
            category='FREIGHT',
            is_gst_applicable=False,
            gst_rate=Decimal('0.00'),
            gl_revenue_code='4306',
            gl_cost_code='5306',
            default_unit=ProductCode.UNIT_KG,
        )

    def setUp(self):
        ExportCOGS.objects.create(
            product_code=self.pc_fx_freight,
            origin_airport='POM',
            destination_airport='SIN',
            agent=self.agent,
            currency='PGK',
            rate_per_shipment=Decimal('400.00'),
            valid_from=self.valid_from,
            valid_until=self.valid_until,
        )
        ExportSellRate.objects.create(
            product_code=self.pc_fx_freight,
            origin_airport='POM',
            destination_airport='SIN',
            currency='PGK',
            rate_per_shipment=Decimal('1000.00'),
            valid_from=self.valid_from,
            valid_until=self.valid_until,
        )

    def test_export_prepaid_fcy_quote_uses_tt_sell_with_caf_added(self):
        result = ExportPricingEngine(
            quote_date=date.today(),
            origin='POM',
            destination='SIN',
            chargeable_weight_kg=Decimal('1'),
            payment_term=PaymentTerm.PREPAID,
            tt_sell=Decimal('2.00'),
            caf_rate=Decimal('0.10'),
            margin_rate=Decimal('0.20'),
            destination_currency='USD',
        ).calculate_quote([self.pc_fx_freight.id])

        line = result.lines[0]
        self.assertEqual(result.quote_currency, 'USD')
        self.assertEqual(result.fx_rate_used, Decimal('2.00'))
        self.assertEqual(result.effective_fx_rate, Decimal('2.2000'))
        self.assertEqual(result.caf_rate, Decimal('0.10'))
        self.assertEqual(line.sell_currency, 'USD')
        self.assertEqual(line.sell_amount, Decimal('545.45'))
        self.assertTrue(line.fx_applied)
        self.assertTrue(line.caf_applied)
        self.assertTrue(line.margin_applied)

    def test_export_collect_pgk_quote_does_not_convert_to_destination_fcy(self):
        ExportSellRate.objects.create(
            product_code=self.pc_fx_freight,
            origin_airport='POM',
            destination_airport='SIN',
            currency='USD',
            rate_per_shipment=Decimal('99.00'),
            valid_from=self.valid_from,
            valid_until=self.valid_until,
        )

        result = ExportPricingEngine(
            quote_date=date.today(),
            origin='POM',
            destination='SIN',
            chargeable_weight_kg=Decimal('1'),
            payment_term=PaymentTerm.COLLECT,
            tt_sell=Decimal('2.00'),
            caf_rate=Decimal('0.10'),
            destination_currency='USD',
        ).calculate_quote([self.pc_fx_freight.id])

        line = result.lines[0]
        self.assertEqual(result.quote_currency, 'PGK')
        self.assertIsNone(result.fx_rate_used)
        self.assertIsNone(result.effective_fx_rate)
        self.assertIsNone(result.caf_rate)
        self.assertEqual(line.sell_currency, 'PGK')
        self.assertEqual(line.sell_amount, Decimal('1000.00'))
        self.assertFalse(line.fx_applied)
        self.assertFalse(line.caf_applied)


class ExportFallbackDefaultTest(TestCase):
    """Document the current hardcoded export defaults when sell rates are absent."""

    DEFAULT_PRODUCTS = [
        (1002, 'EXP-FSC-AIR', 'Airline Export Fuel Surcharge', 'SURCHARGE', ProductCode.UNIT_KG),
        (1020, 'EXP-CLEAR', 'Customs Clearance (Origin)', 'CLEARANCE', ProductCode.UNIT_SHIPMENT),
        (1030, 'EXP-TERM', 'Terminal Handling', 'HANDLING', ProductCode.UNIT_SHIPMENT),
        (1032, 'EXP-HANDLE', 'Handling Fee', 'HANDLING', ProductCode.UNIT_SHIPMENT),
        (1040, 'EXP-SCREEN', 'Security Screening', 'SCREENING', ProductCode.UNIT_KG),
    ]

    @classmethod
    def setUpTestData(cls):
        for pc_id, code, description, category, default_unit in cls.DEFAULT_PRODUCTS:
            ProductCode.objects.update_or_create(
                id=pc_id,
                defaults={
                    'code': code,
                    'description': description,
                    'domain': ProductCode.DOMAIN_EXPORT,
                    'category': category,
                    'is_gst_applicable': False,
                    'gst_rate': Decimal('0.00'),
                    'gl_revenue_code': '4300',
                    'gl_cost_code': '5300',
                    'default_unit': default_unit,
                },
            )

    def setUp(self):
        product_code_ids = [pc_id for pc_id, *_ in self.DEFAULT_PRODUCTS]
        ExportSellRate.objects.filter(product_code_id__in=product_code_ids).delete()
        LocalSellRate.objects.filter(product_code_id__in=product_code_ids).delete()
        Surcharge.objects.filter(product_code_id__in=product_code_ids).delete()

    def test_missing_export_sell_rates_use_current_hardcoded_defaults(self):
        result = ExportPricingEngine(
            quote_date=date.today(),
            origin='POM',
            destination='BNE',
            chargeable_weight_kg=Decimal('50'),
            payment_term=PaymentTerm.COLLECT,
            destination_currency='AUD',
        ).calculate_quote([1002, 1020, 1030, 1032, 1040])

        by_code = {line.product_code: line for line in result.lines}
        self.assertEqual(by_code['EXP-CLEAR'].sell_amount, Decimal('300.00'))
        self.assertEqual(by_code['EXP-FSC-AIR'].sell_amount, Decimal('40.00'))
        self.assertEqual(by_code['EXP-SCREEN'].sell_amount, Decimal('55.00'))
        self.assertEqual(by_code['EXP-TERM'].sell_amount, Decimal('150.00'))
        self.assertEqual(by_code['EXP-HANDLE'].sell_amount, Decimal('50.00'))
        self.assertEqual({line.sell_currency for line in result.lines}, {'PGK'})
        self.assertTrue(all('Default' in line.notes for line in result.lines))


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
        self.assertEqual(by_code[self.pc_pickup.code].rule_family, CALCULATION_PER_UNIT)
        self.assertEqual(by_code[self.pc_fsc_pickup.code].rule_family, CALCULATION_PERCENT_OF_BASE)


class ExportProductCodeSelectionTest(TestCase):
    def test_general_export_scope_does_not_auto_include_special_cargo_fees(self):
        codes = ExportPricingEngine.get_product_codes(is_dg=False, service_scope='D2A')

        self.assertIn(1020, codes)
        self.assertNotIn(1071, codes)
        self.assertNotIn(1072, codes)

    def test_matching_commodity_rule_auto_includes_product_code(self):
        product_code = ProductCode.objects.create(
            id=1510,
            code='EXP-AVI-TEST',
            description='Export Live Animal Handling',
            domain='EXPORT',
            category='HANDLING',
            is_gst_applicable=False,
            gst_rate=Decimal('0.00'),
            gl_revenue_code='4310',
            gl_cost_code='5310',
            default_unit='SHIPMENT',
        )
        CommodityChargeRule.objects.create(
            shipment_type='EXPORT',
            service_scope='D2A',
            commodity_code='AVI',
            product_code=product_code,
            leg='ORIGIN',
            trigger_mode='AUTO',
            origin_code='POM',
            destination_code='BNE',
            effective_from=date.today() - timedelta(days=1),
            effective_to=date.today() + timedelta(days=30),
        )

        general_codes = ExportPricingEngine.get_product_codes(
            is_dg=False,
            service_scope='D2A',
            commodity_code='GCR',
            origin='POM',
            destination='BNE',
            payment_term='PREPAID',
            quote_date=date.today(),
        )
        commodity_codes = ExportPricingEngine.get_product_codes(
            is_dg=False,
            service_scope='D2A',
            commodity_code='AVI',
            origin='POM',
            destination='BNE',
            payment_term='PREPAID',
            quote_date=date.today(),
        )

        self.assertNotIn(product_code.id, general_codes)
        self.assertIn(product_code.id, commodity_codes)
