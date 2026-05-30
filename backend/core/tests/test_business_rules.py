from django.test import SimpleTestCase
from core.business_rules import classify_png_shipment, is_png_country

class BusinessRulesTests(SimpleTestCase):
    def test_is_png_country(self):
        self.assertTrue(is_png_country("PG"))
        self.assertTrue(is_png_country("pg "))
        self.assertFalse(is_png_country("AU"))
        self.assertFalse(is_png_country(None))

    def test_classify_png_shipment_matrix(self):
        self.assertEqual(classify_png_shipment("PG", "PG"), "DOMESTIC")
        self.assertEqual(classify_png_shipment("PG", "AU"), "EXPORT")
        self.assertEqual(classify_png_shipment("AU", "PG"), "IMPORT")

    def test_classify_png_shipment_unsupported(self):
        with self.assertRaisesMessage(ValueError, "Out of scope"):
            classify_png_shipment("AU", "NZ")

    def test_classify_png_shipment_missing_origin(self):
        with self.assertRaisesMessage(ValueError, "Missing country data"):
            classify_png_shipment(None, "PG")

    def test_classify_png_shipment_missing_destination(self):
        with self.assertRaisesMessage(ValueError, "Missing country data"):
            classify_png_shipment("PG", "")
