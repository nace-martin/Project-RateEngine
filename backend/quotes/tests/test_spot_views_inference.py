from django.test import SimpleTestCase
from quotes.spot_views import _infer_shipment_type

class SpotViewsInferenceTests(SimpleTestCase):
    def test_infer_shipment_type_domestic(self):
        self.assertEqual(_infer_shipment_type("PG", "PG"), "DOMESTIC")

    def test_infer_shipment_type_export(self):
        self.assertEqual(_infer_shipment_type("PG", "AU"), "EXPORT")

    def test_infer_shipment_type_import(self):
        self.assertEqual(_infer_shipment_type("AU", "PG"), "IMPORT")

    def test_infer_shipment_type_invalid_cross_border(self):
        with self.assertRaisesMessage(ValueError, "Out of scope"):
            _infer_shipment_type("AU", "NZ")

    def test_infer_shipment_type_missing_data(self):
        with self.assertRaisesMessage(ValueError, "Missing country data"):
            _infer_shipment_type(None, "PG")
