from datetime import date

from django.core.exceptions import ValidationError
from django.test import TestCase

from core.commodity import COMMODITY_CODE_DG, DEFAULT_COMMODITY_CODE
from pricing_v4.models import CommodityChargeRule, ProductCode


class CommodityChargeRuleModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.export_product = ProductCode.objects.create(
            id=1070,
            code='EXP-DG',
            description='Dangerous Goods Acceptance',
            domain=ProductCode.DOMAIN_EXPORT,
            category=ProductCode.CATEGORY_SURCHARGE,
            is_gst_applicable=False,
            gst_rate='0.00',
            gst_treatment=ProductCode.GST_TREATMENT_ZERO_RATED,
            gl_revenue_code='4100',
            gl_cost_code='5100',
            default_unit=ProductCode.UNIT_SHIPMENT,
        )
        cls.import_product = ProductCode.objects.create(
            id=2070,
            code='IMP-DG',
            description='Dangerous Goods Destination Handling',
            domain=ProductCode.DOMAIN_IMPORT,
            category=ProductCode.CATEGORY_SURCHARGE,
            is_gst_applicable=True,
            gst_rate='0.10',
            gst_treatment=ProductCode.GST_TREATMENT_STANDARD,
            gl_revenue_code='4200',
            gl_cost_code='5200',
            default_unit=ProductCode.UNIT_SHIPMENT,
        )

    def test_rule_uses_shared_commodity_defaults_and_string_representation(self):
        rule = CommodityChargeRule(
            shipment_type=CommodityChargeRule.SHIPMENT_TYPE_EXPORT,
            service_scope=CommodityChargeRule.SERVICE_SCOPE_D2A,
            commodity_code=COMMODITY_CODE_DG,
            product_code=self.export_product,
            leg=CommodityChargeRule.LEG_ORIGIN,
            trigger_mode=CommodityChargeRule.TRIGGER_MODE_AUTO,
            origin_code='POM',
            destination_code='BNE',
            effective_from=date(2026, 1, 1),
        )
        rule.full_clean()

        self.assertEqual(rule.commodity_code, COMMODITY_CODE_DG)
        self.assertTrue(rule.is_active)
        self.assertEqual(str(rule), 'EXPORT D2A DG EXP-DG (AUTO) [POM -> BNE]')

        general_rule = CommodityChargeRule(
            shipment_type=CommodityChargeRule.SHIPMENT_TYPE_IMPORT,
            service_scope=CommodityChargeRule.SERVICE_SCOPE_A2D,
            product_code=self.import_product,
            leg=CommodityChargeRule.LEG_DESTINATION,
            trigger_mode=CommodityChargeRule.TRIGGER_MODE_REQUIRES_SPOT,
            effective_from=date(2026, 1, 1),
        )
        general_rule.full_clean()
        self.assertEqual(general_rule.commodity_code, DEFAULT_COMMODITY_CODE)

    def test_rule_rejects_product_code_from_wrong_domain(self):
        rule = CommodityChargeRule(
            shipment_type=CommodityChargeRule.SHIPMENT_TYPE_IMPORT,
            service_scope=CommodityChargeRule.SERVICE_SCOPE_A2D,
            commodity_code=COMMODITY_CODE_DG,
            product_code=self.export_product,
            leg=CommodityChargeRule.LEG_DESTINATION,
            trigger_mode=CommodityChargeRule.TRIGGER_MODE_AUTO,
            effective_from=date(2026, 1, 1),
        )

        with self.assertRaises(ValidationError) as exc:
            rule.full_clean()

        self.assertIn('product_code', exc.exception.message_dict)
