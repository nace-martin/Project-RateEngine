from datetime import date, timedelta
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from pricing_v4.models import Agent, ImportCOGS, ProductCode


class DedupeImportCOGSCommandTests(TestCase):
    def setUp(self):
        self.agent = Agent.objects.create(
            code="EFM-AU",
            name="EFM Australia",
            country_code="AU",
            agent_type="ORIGIN",
        )
        self.product_code = ProductCode.objects.create(
            id=2001,
            code="IMP-FRT-AIR",
            description="Import Air Freight",
            category="FREIGHT",
            domain="IMPORT",
            is_gst_applicable=False,
            gst_treatment="STANDARD",
            gl_revenue_code="4000",
            gl_cost_code="5000",
            default_unit="KG",
        )

    def test_dry_run_reports_duplicates_without_deleting(self):
        self._create_duplicate_rows()
        out = StringIO()

        call_command("dedupe_import_cogs", stdout=out)

        self.assertEqual(ImportCOGS.objects.count(), 2)
        self.assertIn("Dry run complete", out.getvalue())

    def test_apply_deletes_older_duplicate_and_keeps_latest_update(self):
        old_row, new_row = self._create_duplicate_rows()
        out = StringIO()

        call_command("dedupe_import_cogs", apply=True, stdout=out)

        remaining_ids = list(ImportCOGS.objects.values_list("id", flat=True))
        self.assertEqual(remaining_ids, [new_row.id])
        self.assertNotIn(old_row.id, remaining_ids)
        self.assertIn("Deleted 1 duplicate ImportCOGS row(s).", out.getvalue())

    def _create_duplicate_rows(self):
        old_row = ImportCOGS.objects.create(
            product_code=self.product_code,
            origin_airport="SYD",
            destination_airport="POM",
            agent=self.agent,
            currency="AUD",
            min_charge="400.00",
            valid_from=date(2025, 1, 1),
            valid_until=date(2030, 12, 31),
        )
        new_row = ImportCOGS.objects.create(
            product_code=self.product_code,
            origin_airport="SYD",
            destination_airport="POM",
            agent=self.agent,
            currency="AUD",
            min_charge="330.00",
            valid_from=date(2025, 1, 1),
            valid_until=date(2026, 12, 31),
        )
        ImportCOGS.objects.filter(id=old_row.id).update(updated_at=timezone.now() - timedelta(days=7))
        ImportCOGS.objects.filter(id=new_row.id).update(updated_at=timezone.now())
        old_row.refresh_from_db()
        new_row.refresh_from_db()
        return old_row, new_row
