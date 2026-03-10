from datetime import date
from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from pricing_v4.models import LocalSellRate, ProductCode


class RolloverLocalSellRatesCommandTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.pc_export = ProductCode.objects.create(
            id=1901,
            code="EXP-ROLL-DOC",
            description="Export rollover doc",
            domain="EXPORT",
            category="DOCUMENTATION",
            is_gst_applicable=True,
            gl_revenue_code="4100",
            gl_cost_code="5100",
            default_unit="SHIPMENT",
        )
        cls.pc_import = ProductCode.objects.create(
            id=2901,
            code="IMP-ROLL-CLEAR",
            description="Import rollover clearance",
            domain="IMPORT",
            category="CLEARANCE",
            is_gst_applicable=True,
            gl_revenue_code="4200",
            gl_cost_code="5200",
            default_unit="SHIPMENT",
        )

    def _seed_expired_baseline(self):
        LocalSellRate.objects.create(
            product_code=self.pc_export,
            location="POM",
            direction="EXPORT",
            payment_term="ANY",
            currency="PGK",
            rate_type="FIXED",
            amount=Decimal("50.00"),
            valid_from=date(2025, 1, 1),
            valid_until=date(2025, 12, 31),
        )
        LocalSellRate.objects.create(
            product_code=self.pc_import,
            location="POM",
            direction="IMPORT",
            payment_term="PREPAID",
            currency="USD",
            rate_type="FIXED",
            amount=Decimal("75.00"),
            valid_from=date(2025, 1, 1),
            valid_until=date(2025, 12, 31),
        )

    def test_rollover_creates_missing_export_and_import_rows(self):
        self._seed_expired_baseline()

        call_command("rollover_local_sell_rates", year=2026)

        self.assertTrue(
            LocalSellRate.objects.filter(
                product_code=self.pc_export,
                location="POM",
                direction="EXPORT",
                payment_term="ANY",
                currency="PGK",
                valid_from=date(2026, 1, 1),
                valid_until=date(2026, 12, 31),
            ).exists()
        )
        self.assertTrue(
            LocalSellRate.objects.filter(
                product_code=self.pc_import,
                location="POM",
                direction="IMPORT",
                payment_term="PREPAID",
                currency="USD",
                valid_from=date(2026, 1, 1),
                valid_until=date(2026, 12, 31),
            ).exists()
        )

    def test_rollover_is_idempotent(self):
        self._seed_expired_baseline()

        call_command("rollover_local_sell_rates", year=2026)
        count_after_first = LocalSellRate.objects.count()
        call_command("rollover_local_sell_rates", year=2026)
        count_after_second = LocalSellRate.objects.count()

        self.assertEqual(count_after_first, count_after_second)

    def test_rollover_skips_keys_with_existing_target_year_coverage(self):
        self._seed_expired_baseline()
        LocalSellRate.objects.create(
            product_code=self.pc_export,
            location="POM",
            direction="EXPORT",
            payment_term="ANY",
            currency="PGK",
            rate_type="FIXED",
            amount=Decimal("55.00"),
            valid_from=date(2026, 1, 1),
            valid_until=date(2026, 12, 31),
        )

        call_command("rollover_local_sell_rates", year=2026)

        export_rows_2026 = LocalSellRate.objects.filter(
            product_code=self.pc_export,
            location="POM",
            direction="EXPORT",
            payment_term="ANY",
            currency="PGK",
            valid_from=date(2026, 1, 1),
            valid_until=date(2026, 12, 31),
        ).count()
        import_rows_2026 = LocalSellRate.objects.filter(
            product_code=self.pc_import,
            location="POM",
            direction="IMPORT",
            payment_term="PREPAID",
            currency="USD",
            valid_from=date(2026, 1, 1),
            valid_until=date(2026, 12, 31),
        ).count()

        self.assertEqual(export_rows_2026, 1)
        self.assertEqual(import_rows_2026, 1)

    def test_dry_run_does_not_write(self):
        self._seed_expired_baseline()
        out = StringIO()

        call_command("rollover_local_sell_rates", year=2026, dry_run=True, stdout=out)

        self.assertFalse(
            LocalSellRate.objects.filter(
                valid_from=date(2026, 1, 1),
                valid_until=date(2026, 12, 31),
            ).exists()
        )
