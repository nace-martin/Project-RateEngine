# backend/pricing_v4/tests/test_export_engine.py
"""
Export Pricing Engine Tests

Tests the ExportPricingEngine for FCY margin reporting on COLLECT quotes.
"""
from decimal import Decimal
from datetime import date, timedelta
from django.test import TestCase

from pricing_v4.models import ProductCode, Agent, ExportCOGS, ExportSellRate
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


class ExportCollectFcyMarginTest(ExportEngineTestCase):
    """Test margin reporting for COLLECT with FCY sell rates."""

    def setUp(self):
        ExportCOGS.objects.create(
            product_code=self.pc_clearance,
            origin_airport='POM',
            destination_airport='BNE',
            agent=self.agent,
            currency='PGK',
            rate_per_shipment=Decimal('100.00'),
            valid_from=self.valid_from,
            valid_until=self.valid_until
        )

        ExportSellRate.objects.create(
            product_code=self.pc_clearance,
            origin_airport='POM',
            destination_airport='BNE',
            currency='USD',
            rate_per_shipment=Decimal('80.00'),
            valid_from=self.valid_from,
            valid_until=self.valid_until
        )

    def test_collect_fcy_margin_uses_converted_cost(self):
        engine = ExportPricingEngine(
            quote_date=date.today(),
            origin='POM',
            destination='BNE',
            chargeable_weight_kg=Decimal('1'),
            payment_term=PaymentTerm.COLLECT,
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
