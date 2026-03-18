from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from pricing_v4.models import DomesticCOGS, DomesticSellRate, ProductCode, Surcharge


class SeedLaunchDomesticTariffsCommandTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_domestic_product_codes", stdout=StringIO())

    def test_command_seeds_launch_domestic_tariffs_idempotently(self):
        stdout = StringIO()

        call_command("seed_launch_domestic_tariffs", year=2026, stdout=stdout)
        call_command("seed_launch_domestic_tariffs", year=2026, stdout=StringIO())

        freight_pc = ProductCode.objects.get(code="DOM-FRT-AIR")

        self.assertEqual(
            DomesticCOGS.objects.filter(product_code=freight_pc, valid_from="2026-01-01").count(),
            47,
        )
        self.assertEqual(
            DomesticSellRate.objects.filter(product_code=freight_pc, valid_from="2026-01-01").count(),
            47,
        )

        pom_lae_sell = DomesticSellRate.objects.get(
            product_code=freight_pc,
            origin_zone="POM",
            destination_zone="LAE",
            valid_from="2026-01-01",
        )
        lae_pom_sell = DomesticSellRate.objects.get(
            product_code=freight_pc,
            origin_zone="LAE",
            destination_zone="POM",
            valid_from="2026-01-01",
        )
        self.assertEqual(str(pom_lae_sell.rate_per_kg), "6.1000")
        self.assertEqual(str(lae_pom_sell.rate_per_kg), "6.1000")

        security_sell = Surcharge.objects.get(
            product_code__code="DOM-SECURITY",
            service_type="DOMESTIC_AIR",
            rate_side="SELL",
            valid_from="2026-01-01",
        )
        self.assertEqual(security_sell.rate_type, "PER_KG")
        self.assertEqual(str(security_sell.amount), "0.2000")
        self.assertEqual(str(security_sell.min_charge), "5.00")

        fuel_cogs = Surcharge.objects.get(
            product_code__code="DOM-FSC",
            service_type="DOMESTIC_AIR",
            rate_side="COGS",
            valid_from="2026-01-01",
        )
        self.assertEqual(str(fuel_cogs.amount), "0.2500")

        valuable_sell = Surcharge.objects.get(
            product_code__code="DOM-VALUABLE",
            service_type="DOMESTIC_AIR",
            rate_side="SELL",
            valid_from="2026-01-01",
        )
        self.assertEqual(valuable_sell.rate_type, "PERCENT")
        self.assertEqual(str(valuable_sell.amount), "400.0000")

        self.assertFalse(
            Surcharge.objects.filter(
                product_code__code="DOM-AWB",
                service_type="DOMESTIC_AIR",
                rate_side="SELL",
                is_active=True,
            ).exists()
        )

        self.assertIn("Domestic launch tariffs ready.", stdout.getvalue())
