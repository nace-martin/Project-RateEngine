from django.core.exceptions import ValidationError
from django.test import TestCase

from pricing_v4.models import ChargeAlias, ProductCode


class ChargeAliasModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.export_product = ProductCode.objects.create(
            id=1091,
            code='EXP-TERM-HANDLING',
            description='Export Terminal Handling',
            domain=ProductCode.DOMAIN_EXPORT,
            category=ProductCode.CATEGORY_HANDLING,
            is_gst_applicable=False,
            gst_rate='0.00',
            gst_treatment=ProductCode.GST_TREATMENT_ZERO_RATED,
            gl_revenue_code='4101',
            gl_cost_code='5101',
            default_unit=ProductCode.UNIT_SHIPMENT,
        )
        cls.import_product = ProductCode.objects.create(
            id=2091,
            code='IMP-TERM-HANDLING',
            description='Import Terminal Handling',
            domain=ProductCode.DOMAIN_IMPORT,
            category=ProductCode.CATEGORY_HANDLING,
            is_gst_applicable=True,
            gst_rate='0.10',
            gst_treatment=ProductCode.GST_TREATMENT_STANDARD,
            gl_revenue_code='4201',
            gl_cost_code='5201',
            default_unit=ProductCode.UNIT_SHIPMENT,
        )

    def test_full_clean_normalizes_alias_text_for_case_insensitive_matching(self):
        alias = ChargeAlias(
            alias_text='  Terminal Handling  ',
            normalized_alias_text='TeRmInAl HaNdLiNg',
            match_type=ChargeAlias.MatchType.EXACT,
            mode_scope=ChargeAlias.ModeScope.EXPORT,
            direction_scope=ChargeAlias.DirectionScope.ORIGIN,
            product_code=self.export_product,
            priority=10,
        )

        alias.full_clean()

        self.assertEqual(alias.normalized_alias_text, 'terminal handling')

    def test_mode_scope_must_align_with_product_code_domain_when_specific(self):
        alias = ChargeAlias(
            alias_text='Destination Fee',
            match_type=ChargeAlias.MatchType.CONTAINS,
            mode_scope=ChargeAlias.ModeScope.EXPORT,
            direction_scope=ChargeAlias.DirectionScope.DESTINATION,
            product_code=self.import_product,
            priority=50,
        )

        with self.assertRaises(ValidationError) as exc:
            alias.full_clean()

        self.assertIn('product_code', exc.exception.message_dict)

    def test_save_populates_normalized_alias_text_when_omitted(self):
        alias = ChargeAlias.objects.create(
            alias_text='Fuel Surcharge',
            match_type=ChargeAlias.MatchType.EXACT,
            mode_scope=ChargeAlias.ModeScope.ANY,
            direction_scope=ChargeAlias.DirectionScope.MAIN,
            product_code=self.export_product,
            priority=5,
        )

        self.assertEqual(alias.normalized_alias_text, 'fuel surcharge')
