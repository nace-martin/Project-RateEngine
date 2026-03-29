from django.test import SimpleTestCase

from pricing_v4.management.commands.sync_v4_components import infer_component_leg
from pricing_v4.models import ProductCode


class InferComponentLegTests(SimpleTestCase):
    def make_product_code(self, **overrides):
        defaults = {
            "id": 2001,
            "code": "IMP-DOC-ORIGIN",
            "description": "Import Documentation Fee (Origin)",
            "domain": ProductCode.DOMAIN_IMPORT,
            "category": ProductCode.CATEGORY_DOCUMENTATION,
            "is_gst_applicable": True,
            "gl_revenue_code": "4000",
            "gl_cost_code": "5000",
            "default_unit": ProductCode.UNIT_SHIPMENT,
        }
        defaults.update(overrides)
        return ProductCode(**defaults)

    def test_import_origin_code_maps_to_origin_leg(self):
        product_code = self.make_product_code()
        self.assertEqual(infer_component_leg(product_code), "ORIGIN")

    def test_import_pickup_code_maps_to_origin_leg(self):
        product_code = self.make_product_code(
            id=2010,
            code="IMP-PICKUP",
            description="Pick-Up Fee (Origin)",
            category=ProductCode.CATEGORY_CARTAGE,
        )
        self.assertEqual(infer_component_leg(product_code), "ORIGIN")

    def test_import_destination_code_maps_to_destination_leg(self):
        product_code = self.make_product_code(
            id=2006,
            code="IMP-AGENCY-DEST",
            description="Agency Fee (Dest)",
            category=ProductCode.CATEGORY_AGENCY,
        )
        self.assertEqual(infer_component_leg(product_code), "DESTINATION")

    def test_import_clearance_defaults_to_destination_leg(self):
        product_code = self.make_product_code(
            id=2005,
            code="IMP-CLEAR",
            description="Customs Clearance (Dest)",
            category=ProductCode.CATEGORY_CLEARANCE,
        )
        self.assertEqual(infer_component_leg(product_code), "DESTINATION")

    def test_freight_maps_to_main_leg(self):
        product_code = self.make_product_code(
            id=2000,
            code="IMP-FRT-AIR",
            description="Import Air Freight",
            category=ProductCode.CATEGORY_FREIGHT,
        )
        self.assertEqual(infer_component_leg(product_code), "MAIN")
