from datetime import date
from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from pricing_v4.models import Agent, ImportCOGS, LocalCOGSRate, ProductCode


class NormalizeImportOriginCOGSCommandTests(TestCase):
    def setUp(self):
        self.agent = Agent.objects.create(
            code="EFM-AU",
            name="EFM Australia",
            country_code="AU",
            agent_type="ORIGIN",
        )
        self.pc_freight = ProductCode.objects.create(
            id=29001,
            code="IMP-FRT-AIR-CMD",
            description="Import Freight Command Test",
            category="FREIGHT",
            domain="IMPORT",
            is_gst_applicable=False,
            gst_treatment="STANDARD",
            gl_revenue_code="4000",
            gl_cost_code="5000",
            default_unit="KG",
        )
        self.pc_doc_origin = ProductCode.objects.create(
            id=29010,
            code="IMP-DOC-ORIGIN",
            description="Import Documentation Origin",
            category="DOCUMENTATION",
            domain="IMPORT",
            is_gst_applicable=False,
            gst_treatment="STANDARD",
            gl_revenue_code="4200",
            gl_cost_code="5200",
            default_unit="SHIPMENT",
        )
        self.pc_pickup = ProductCode.objects.create(
            id=29050,
            code="IMP-PICKUP",
            description="Import Pickup",
            category="CARTAGE",
            domain="IMPORT",
            is_gst_applicable=False,
            gst_treatment="STANDARD",
            gl_revenue_code="4250",
            gl_cost_code="5250",
            default_unit="KG",
        )
        self.pc_pickup_fsc = ProductCode.objects.create(
            id=29060,
            code="IMP-FSC-PICKUP",
            description="Import Pickup FSC",
            category="SURCHARGE",
            domain="IMPORT",
            is_gst_applicable=False,
            gst_treatment="STANDARD",
            gl_revenue_code="4260",
            gl_cost_code="5260",
            default_unit="PERCENT",
        )

        for origin in ("BNE", "SYD"):
            ImportCOGS.objects.create(
                product_code=self.pc_freight,
                origin_airport=origin,
                destination_airport="POM",
                agent=self.agent,
                currency="AUD",
                min_charge="330.00",
                valid_from=date(2025, 1, 1),
                valid_until=date(2026, 12, 31),
            )

        self.source_doc = LocalCOGSRate.objects.create(
            product_code=self.pc_doc_origin,
            location="POM",
            direction="IMPORT",
            agent=self.agent,
            currency="AUD",
            rate_type="FIXED",
            amount="80.00",
            valid_from=date(2025, 1, 1),
            valid_until=date(2026, 12, 31),
        )
        self.source_pickup = LocalCOGSRate.objects.create(
            product_code=self.pc_pickup,
            location="POM",
            direction="IMPORT",
            agent=self.agent,
            currency="AUD",
            rate_type="PER_KG",
            amount="0.26",
            min_charge="85.00",
            valid_from=date(2025, 1, 1),
            valid_until=date(2026, 12, 31),
        )
        self.source_pickup_fsc = LocalCOGSRate.objects.create(
            product_code=self.pc_pickup_fsc,
            location="POM",
            direction="IMPORT",
            agent=self.agent,
            currency="AUD",
            rate_type="PERCENT",
            amount="20.00",
            valid_from=date(2025, 1, 1),
            valid_until=date(2026, 12, 31),
        )

    def test_dry_run_reports_move_without_mutating_rows(self):
        out = StringIO()

        call_command("normalize_import_origin_cogs", stdout=out)

        self.assertEqual(LocalCOGSRate.objects.filter(id__in=[
            self.source_doc.id,
            self.source_pickup.id,
            self.source_pickup_fsc.id,
        ]).count(), 3)
        self.assertEqual(
            ImportCOGS.objects.exclude(product_code=self.pc_freight).count(),
            0,
        )
        self.assertIn("Dry run complete.", out.getvalue())

    def test_apply_moves_rows_to_all_discovered_import_lanes(self):
        out = StringIO()

        call_command("normalize_import_origin_cogs", apply=True, stdout=out)

        self.assertFalse(LocalCOGSRate.objects.filter(id=self.source_doc.id).exists())
        self.assertFalse(LocalCOGSRate.objects.filter(id=self.source_pickup.id).exists())
        self.assertFalse(LocalCOGSRate.objects.filter(id=self.source_pickup_fsc.id).exists())

        doc_rows = list(
            ImportCOGS.objects.filter(product_code=self.pc_doc_origin)
            .order_by("origin_airport")
            .values_list("origin_airport", "destination_airport", "rate_per_shipment", "currency")
        )
        pickup_rows = list(
            ImportCOGS.objects.filter(product_code=self.pc_pickup)
            .order_by("origin_airport")
            .values_list("origin_airport", "destination_airport", "rate_per_kg", "min_charge")
        )
        fsc_rows = list(
            ImportCOGS.objects.filter(product_code=self.pc_pickup_fsc)
            .order_by("origin_airport")
            .values_list("origin_airport", "destination_airport", "percent_rate")
        )

        self.assertEqual(
            doc_rows,
            [("BNE", "POM", Decimal("80.00"), "AUD"), ("SYD", "POM", Decimal("80.00"), "AUD")],
        )
        self.assertEqual(
            pickup_rows,
            [("BNE", "POM", Decimal("0.2600"), Decimal("85.00")), ("SYD", "POM", Decimal("0.2600"), Decimal("85.00"))],
        )
        self.assertEqual(
            fsc_rows,
            [("BNE", "POM", Decimal("20.00")), ("SYD", "POM", Decimal("20.00"))],
        )
        self.assertIn("Applied complete.", out.getvalue())
