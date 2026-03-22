from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from pricing_v4.models import LocalSellRate, ProductCode


class SeedImportSpecialLocalSellRatesCommandTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        for id_, code, description in (
            (2091, "IMP-DG-SPECIAL", "Import Dangerous Goods Handling"),
            (2092, "IMP-AVI-SPECIAL", "Import Live Animal Handling"),
            (2093, "IMP-HVC-SPECIAL", "Import High Value Handling"),
        ):
            ProductCode.objects.create(
                id=id_,
                code=code,
                description=description,
                domain="IMPORT",
                category="HANDLING",
                is_gst_applicable=True,
                gst_rate="0.10",
                gst_treatment=ProductCode.GST_TREATMENT_STANDARD,
                gl_revenue_code="4490",
                gl_cost_code="5490",
                default_unit=ProductCode.UNIT_SHIPMENT,
            )

    def test_command_seeds_expected_tariffs(self):
        out = StringIO()

        call_command(
            "seed_import_special_local_sell_rates",
            "--year",
            "2026",
            "--location",
            "POM",
            stdout=out,
        )

        self.assertEqual(
            LocalSellRate.objects.filter(
                product_code__code="IMP-DG-SPECIAL",
                location="POM",
                direction="IMPORT",
                payment_term="COLLECT",
                currency="PGK",
            ).get().amount,
            250,
        )
        self.assertEqual(
            LocalSellRate.objects.filter(
                product_code__code="IMP-AVI-SPECIAL",
                location="POM",
                direction="IMPORT",
                payment_term="PREPAID",
                currency="AUD",
            ).get().amount,
            60,
        )
        self.assertEqual(
            LocalSellRate.objects.filter(
                product_code__code="IMP-HVC-SPECIAL",
                location="POM",
                direction="IMPORT",
                payment_term="PREPAID",
                currency="USD",
            ).get().amount,
            50,
        )

        call_command(
            "seed_import_special_local_sell_rates",
            "--year",
            "2026",
            "--location",
            "POM",
            stdout=StringIO(),
        )
        self.assertEqual(LocalSellRate.objects.count(), 9)
