from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from pricing_v4.models import ProductCode


class SeedExportPomBneCommandTests(TestCase):
    def test_command_seeds_requested_export_product_codes(self):
        call_command("seed_export_pom_bne", year=2026, stdout=StringIO())

        self.assertEqual(ProductCode.objects.get(code="EXP-FSC-AIR").id, 1002)
        self.assertEqual(ProductCode.objects.get(code="EXP-CLEAR-DEST").id, 1080)
        self.assertEqual(ProductCode.objects.get(code="EXP-DELIVERY-DEST").id, 1081)

        fuel = ProductCode.objects.get(code="EXP-FSC-AIR")
        self.assertEqual(fuel.category, ProductCode.CATEGORY_SURCHARGE)
        self.assertEqual(fuel.default_unit, ProductCode.UNIT_KG)

        destination_clearance = ProductCode.objects.get(code="EXP-CLEAR-DEST")
        self.assertEqual(destination_clearance.gst_treatment, ProductCode.GST_TREATMENT_ZERO_RATED)


class SeedExportPomSydCommandTests(TestCase):
    def test_command_seeds_requested_export_product_codes(self):
        call_command("seed_export_pom_syd", year=2026, stdout=StringIO())

        self.assertEqual(ProductCode.objects.get(code="EXP-FSC-AIR").id, 1002)
        self.assertEqual(ProductCode.objects.get(code="EXP-CLEAR-DEST").id, 1080)
        self.assertEqual(ProductCode.objects.get(code="EXP-DELIVERY-DEST").id, 1081)

        destination_delivery = ProductCode.objects.get(code="EXP-DELIVERY-DEST")
        self.assertEqual(destination_delivery.category, ProductCode.CATEGORY_CARTAGE)
        self.assertEqual(destination_delivery.gst_treatment, ProductCode.GST_TREATMENT_ZERO_RATED)
