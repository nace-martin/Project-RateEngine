from io import StringIO
from datetime import date

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

        pom_lae_cogs = DomesticCOGS.objects.get(
            product_code=freight_pc,
            origin_zone="POM",
            destination_zone="LAE",
            valid_from="2026-01-01",
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
        self.assertEqual(str(pom_lae_cogs.rate_per_kg), "6.1000")
        self.assertEqual(str(pom_lae_sell.rate_per_kg), "7.3000")
        self.assertEqual(str(lae_pom_sell.rate_per_kg), "7.1000")

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

        fuel_sell = Surcharge.objects.get(
            product_code__code="DOM-FSC",
            service_type="DOMESTIC_AIR",
            rate_side="SELL",
            valid_from="2026-01-01",
        )
        self.assertEqual(str(fuel_sell.amount), "0.3500")

        awb_sell = Surcharge.objects.get(
            product_code__code="DOM-AWB",
            service_type="DOMESTIC_AIR",
            rate_side="SELL",
            valid_from="2026-01-01",
        )
        self.assertTrue(awb_sell.is_active)
        self.assertEqual(awb_sell.rate_type, "FLAT")
        self.assertEqual(str(awb_sell.amount), "70.0000")

        dg_sell = Surcharge.objects.get(
            product_code__code="DOM-DG-HANDLING",
            service_type="DOMESTIC_AIR",
            rate_side="SELL",
            valid_from="2026-01-01",
        )
        self.assertTrue(dg_sell.is_active)
        self.assertEqual(str(dg_sell.amount), "195.0000")

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
                product_code__code="DOM-DOC",
                service_type="DOMESTIC_AIR",
                rate_side="SELL",
                is_active=True,
            ).exists()
        )
        self.assertFalse(
            Surcharge.objects.filter(
                product_code__code="DOM-TERMINAL",
                service_type="DOMESTIC_AIR",
                rate_side="SELL",
                is_active=True,
            ).exists()
        )

        self.assertIn("Domestic launch tariffs ready.", stdout.getvalue())

    def test_command_disables_overlapping_legacy_domestic_surcharges(self):
        doc_pc = ProductCode.objects.get(code="DOM-DOC")
        security_pc = ProductCode.objects.get(code="DOM-SECURITY")

        legacy_doc = Surcharge.objects.create(
            product_code=doc_pc,
            service_type="DOMESTIC_AIR",
            rate_side="COGS",
            rate_type="FLAT",
            amount="35.00",
            currency="PGK",
            valid_from=date(2025, 1, 1),
            valid_until=date(2026, 12, 31),
            is_active=True,
        )
        legacy_security = Surcharge.objects.create(
            product_code=security_pc,
            service_type="DOMESTIC_AIR",
            rate_side="SELL",
            rate_type="FLAT",
            amount="5.00",
            currency="PGK",
            valid_from=date(2025, 1, 1),
            valid_until=date(2026, 12, 31),
            is_active=True,
        )

        call_command("seed_launch_domestic_tariffs", year=2026, stdout=StringIO())

        legacy_doc.refresh_from_db()
        legacy_security.refresh_from_db()

        self.assertFalse(legacy_doc.is_active)
        self.assertFalse(legacy_security.is_active)
