from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from pricing_v4.models import CommodityChargeRule, ProductCode


class SeedLaunchCommodityRulesCommandTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls._create_product_code(
            id=1070,
            code="EXP-DG",
            description="Export DG Acceptance",
            domain=ProductCode.DOMAIN_EXPORT,
        )
        cls._create_product_code(
            id=1080,
            code="EXP-VCH",
            description="Export Valuable Cargo Handling",
            domain=ProductCode.DOMAIN_EXPORT,
        )
        cls._create_product_code(
            id=1081,
            code="EXP-LPC",
            description="Export Live Animal Processing",
            domain=ProductCode.DOMAIN_EXPORT,
        )
        cls._create_product_code(
            id=3102,
            code="DOM-LIVE-ANIMAL",
            description="Domestic Live Animal Surcharge",
            domain=ProductCode.DOMAIN_DOMESTIC,
        )
        cls._create_product_code(
            id=3101,
            code="DOM-VALUABLE",
            description="Domestic Valuable Cargo Surcharge",
            domain=ProductCode.DOMAIN_DOMESTIC,
        )

    @staticmethod
    def _create_product_code(*, id: int, code: str, description: str, domain: str):
        ProductCode.objects.create(
            id=id,
            code=code,
            description=description,
            domain=domain,
            category=ProductCode.CATEGORY_HANDLING,
            is_gst_applicable=(domain != ProductCode.DOMAIN_EXPORT),
            gst_rate="0.10" if domain != ProductCode.DOMAIN_EXPORT else "0.00",
            gst_treatment=(
                ProductCode.GST_TREATMENT_ZERO_RATED
                if domain == ProductCode.DOMAIN_EXPORT
                else ProductCode.GST_TREATMENT_STANDARD
            ),
            gl_revenue_code="4100",
            gl_cost_code="5100",
            default_unit=ProductCode.UNIT_SHIPMENT,
        )

    def test_dry_run_does_not_persist_changes(self):
        out = StringIO()

        call_command(
            "seed_launch_commodity_rules",
            "--effective-from",
            "2026-01-01",
            "--dry-run",
            stdout=out,
        )

        self.assertEqual(CommodityChargeRule.objects.count(), 0)
        self.assertFalse(ProductCode.objects.filter(code="IMP-DG-SPECIAL").exists())

    def test_command_seeds_launch_matrix_idempotently(self):
        out = StringIO()

        call_command(
            "seed_launch_commodity_rules",
            "--effective-from",
            "2026-01-01",
            stdout=out,
        )
        first_count = CommodityChargeRule.objects.count()
        self.assertGreater(first_count, 0)
        self.assertTrue(ProductCode.objects.filter(code="IMP-DG-SPECIAL").exists())

        export_dg = CommodityChargeRule.objects.get(
            shipment_type="EXPORT",
            service_scope="D2A",
            commodity_code="DG",
            product_code__code="EXP-DG",
        )
        self.assertEqual(export_dg.trigger_mode, CommodityChargeRule.TRIGGER_MODE_AUTO)

        import_avi = CommodityChargeRule.objects.get(
            shipment_type="IMPORT",
            service_scope="A2D",
            commodity_code="AVI",
            product_code__code="IMP-AVI-SPECIAL",
        )
        self.assertEqual(import_avi.trigger_mode, CommodityChargeRule.TRIGGER_MODE_AUTO)

        domestic_per = CommodityChargeRule.objects.get(
            shipment_type="DOMESTIC",
            service_scope="D2D",
            commodity_code="PER",
            product_code__code="DOM-PER-SPECIAL",
        )
        self.assertEqual(domestic_per.trigger_mode, CommodityChargeRule.TRIGGER_MODE_REQUIRES_SPOT)

        call_command(
            "seed_launch_commodity_rules",
            "--effective-from",
            "2026-01-01",
            stdout=StringIO(),
        )
        self.assertEqual(CommodityChargeRule.objects.count(), first_count)
