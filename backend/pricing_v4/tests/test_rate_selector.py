from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase

from pricing_v4.engine.import_engine import ImportPricingEngine, PaymentTerm, ServiceScope
from pricing_v4.models import Agent, Carrier, ExportSellRate, ImportCOGS, LocalSellRate, ProductCode
from pricing_v4.services.rate_selector import (
    RateAmbiguityError,
    RateNotFoundError,
    RateSelectionContext,
    select_export_sell_rate,
    select_import_cogs_rate,
    select_local_sell_rate,
)
from pricing_v4.tests.validated_factories import (
    create_validated_import_cogs,
    create_validated_export_sell,
    create_validated_local_sell,
    get_or_create_test_product
)


class RateSelectorTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.valid_from = date.today() - timedelta(days=1)
        cls.valid_until = date.today() + timedelta(days=30)
        cls.valid_until_next = date.today() + timedelta(days=60)

        cls.agent_a = Agent.objects.create(
            code='SEL-AG-A',
            name='Selector Agent A',
            country_code='AU',
            agent_type='ORIGIN',
        )
        cls.agent_b = Agent.objects.create(
            code='SEL-AG-B',
            name='Selector Agent B',
            country_code='AU',
            agent_type='ORIGIN',
        )
        cls.carrier = Carrier.objects.create(
            code='SEL-CAR',
            name='Selector Carrier',
            carrier_type='AIRLINE',
        )

        cls.pc_import_freight = get_or_create_test_product(
            id=2601,
            code='IMP-FRT-SELECTOR',
            domain='IMPORT',
            category='FREIGHT',
            is_gst_applicable=True,
        )
        cls.pc_export_freight = get_or_create_test_product(
            id=1601,
            code='EXP-FRT-SELECTOR',
            domain='EXPORT',
            category='FREIGHT',
            is_gst_applicable=False,
        )
        cls.pc_import_local = get_or_create_test_product(
            id=2602,
            code='IMP-CLEAR-SELECTOR',
            domain='IMPORT',
            category='CLEARANCE',
            is_gst_applicable=True,
        )

    def test_import_cogs_prefers_exact_counterparty_and_currency(self):
        row_a = create_validated_import_cogs(
            product_code=self.pc_import_freight,
            origin_airport='SYD',
            destination_airport='POM',
            agent=self.agent_a,
            currency='AUD',
            rate_per_kg=Decimal('5.00'),
            valid_from=self.valid_from,
            valid_until=self.valid_until,
        )
        create_validated_import_cogs(
            product_code=self.pc_import_freight,
            origin_airport='SYD',
            destination_airport='POM',
            agent=self.agent_b,
            currency='AUD',
            rate_per_kg=Decimal('5.20'),
            valid_from=self.valid_from,
            valid_until=self.valid_until,
        )

        result = select_import_cogs_rate(
            RateSelectionContext(
                product_code_id=self.pc_import_freight.id,
                quote_date=date.today(),
                origin_airport='SYD',
                destination_airport='POM',
                currency='AUD',
                agent_id=self.agent_a.id,
            )
        )

        self.assertEqual(result.record.id, row_a.id)
        self.assertEqual(result.match_type, 'exact_currency')

    def test_import_cogs_raises_ambiguity_without_counterparty_when_multiple_match(self):
        create_validated_import_cogs(
            product_code=self.pc_import_freight,
            origin_airport='SYD',
            destination_airport='POM',
            agent=self.agent_a,
            currency='AUD',
            rate_per_kg=Decimal('5.00'),
            valid_from=self.valid_from,
            valid_until=self.valid_until,
        )
        create_validated_import_cogs(
            product_code=self.pc_import_freight,
            origin_airport='SYD',
            destination_airport='POM',
            agent=self.agent_b,
            currency='AUD',
            rate_per_kg=Decimal('5.20'),
            valid_from=self.valid_from,
            valid_until=self.valid_until,
        )

        with self.assertRaises(RateAmbiguityError):
            select_import_cogs_rate(
                RateSelectionContext(
                    product_code_id=self.pc_import_freight.id,
                    quote_date=date.today(),
                    origin_airport='SYD',
                    destination_airport='POM',
                    currency='AUD',
                )
            )

    def test_local_sell_uses_pgk_fallback_when_explicit_currency_missing(self):
        create_validated_local_sell(
            product_code=self.pc_import_local,
            location='POM',
            direction='IMPORT',
            payment_term='PREPAID',
            currency='PGK',
            rate_type='FIXED',
            amount=Decimal('150.00'),
            valid_from=self.valid_from,
            valid_until=self.valid_until,
        )

        result = select_local_sell_rate(
            RateSelectionContext(
                product_code_id=self.pc_import_local.id,
                quote_date=date.today(),
                location='POM',
                direction='IMPORT',
                payment_term='PREPAID',
                currency='AUD',
            ),
            allow_pgk_fallback=True,
        )

        self.assertEqual(result.record.currency, 'PGK')
        self.assertTrue(result.fallback_applied)

    def test_export_sell_uses_latest_valid_from_tiebreak(self):
        """
        Tiebreak test needs overlapping rows. 
        Since our validator now BLOCKS overlaps, we must use raw ORM to create this specific test scenario
        OR adjust the test to use sequential non-overlapping rows if tiebreak logic is still applicable there.
        Actually, tiebreak is for when multiple valid rows match a date. 
        If we enforce no overlaps, tiebreak is only relevant during migrations or for specific exceptions.
        
        For this test, I will INTENTIONALLY bypass validation to test the selector's fallback behavior
        for any existing legacy data or edge cases.
        """
        older = ExportSellRate.objects.create(
            product_code=self.pc_export_freight,
            origin_airport='POM',
            destination_airport='SIN',
            currency='USD',
            rate_per_kg=Decimal('4.10'),
            valid_from=self.valid_from,
            valid_until=self.valid_until_next,
        )
        newer = ExportSellRate.objects.create(
            product_code=self.pc_export_freight,
            origin_airport='POM',
            destination_airport='SIN',
            currency='USD',
            rate_per_kg=Decimal('4.50'),
            valid_from=date.today(),
            valid_until=self.valid_until_next,
        )

        result = select_export_sell_rate(
            RateSelectionContext(
                product_code_id=self.pc_export_freight.id,
                quote_date=date.today(),
                origin_airport='POM',
                destination_airport='SIN',
                currency='USD',
            )
        )

        self.assertEqual(result.record.id, newer.id)
        self.assertNotEqual(result.record.id, older.id)

    def test_selector_raises_not_found_when_no_rate_exists(self):
        with self.assertRaises(RateNotFoundError):
            select_export_sell_rate(
                RateSelectionContext(
                    product_code_id=self.pc_export_freight.id,
                    quote_date=date.today(),
                    origin_airport='POM',
                    destination_airport='MNL',
                    currency='USD',
                )
            )

    def test_import_engine_raises_ambiguity_when_multiple_counterparties_exist(self):
        create_validated_import_cogs(
            product_code=self.pc_import_freight,
            origin_airport='SYD',
            destination_airport='POM',
            agent=self.agent_a,
            currency='AUD',
            rate_per_kg=Decimal('5.00'),
            valid_from=self.valid_from,
            valid_until=self.valid_until,
        )
        create_validated_import_cogs(
            product_code=self.pc_import_freight,
            origin_airport='SYD',
            destination_airport='POM',
            agent=self.agent_b,
            currency='AUD',
            rate_per_kg=Decimal('5.20'),
            valid_from=self.valid_from,
            valid_until=self.valid_until,
        )

        engine = ImportPricingEngine(
            quote_date=date.today(),
            origin='SYD',
            destination='POM',
            chargeable_weight_kg=Decimal('50'),
            payment_term=PaymentTerm.COLLECT,
            service_scope=ServiceScope.A2A,
        )

        with self.assertRaises(RateAmbiguityError):
            engine._get_cogs(self.pc_import_freight, 'FREIGHT')
