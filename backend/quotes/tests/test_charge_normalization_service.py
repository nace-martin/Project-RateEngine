from django.test import TestCase

from pricing_v4.models import ChargeAlias, ProductCode
from quotes.services.charge_normalization import (
    NormalizationMethod,
    NormalizationStatus,
    resolve_charge_alias,
)


class ChargeNormalizationServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.export_terminal = ProductCode.objects.create(
            id=1092,
            code='EXP-TERMINAL',
            description='Export Terminal Handling',
            domain=ProductCode.DOMAIN_EXPORT,
            category=ProductCode.CATEGORY_HANDLING,
            is_gst_applicable=False,
            gst_rate='0.00',
            gst_treatment=ProductCode.GST_TREATMENT_ZERO_RATED,
            gl_revenue_code='4102',
            gl_cost_code='5102',
            default_unit=ProductCode.UNIT_SHIPMENT,
        )
        cls.export_fuel = ProductCode.objects.create(
            id=1093,
            code='EXP-FUEL',
            description='Export Fuel Surcharge',
            domain=ProductCode.DOMAIN_EXPORT,
            category=ProductCode.CATEGORY_SURCHARGE,
            is_gst_applicable=False,
            gst_rate='0.00',
            gst_treatment=ProductCode.GST_TREATMENT_ZERO_RATED,
            gl_revenue_code='4103',
            gl_cost_code='5103',
            default_unit=ProductCode.UNIT_SHIPMENT,
        )
        cls.import_terminal = ProductCode.objects.create(
            id=2092,
            code='IMP-TERMINAL',
            description='Import Terminal Handling',
            domain=ProductCode.DOMAIN_IMPORT,
            category=ProductCode.CATEGORY_HANDLING,
            is_gst_applicable=True,
            gst_rate='0.10',
            gst_treatment=ProductCode.GST_TREATMENT_STANDARD,
            gl_revenue_code='4202',
            gl_cost_code='5202',
            default_unit=ProductCode.UNIT_SHIPMENT,
        )
        cls.import_fuel = ProductCode.objects.create(
            id=2093,
            code='IMP-FUEL',
            description='Import Fuel Surcharge',
            domain=ProductCode.DOMAIN_IMPORT,
            category=ProductCode.CATEGORY_SURCHARGE,
            is_gst_applicable=True,
            gst_rate='0.10',
            gst_treatment=ProductCode.GST_TREATMENT_STANDARD,
            gl_revenue_code='4203',
            gl_cost_code='5203',
            default_unit=ProductCode.UNIT_SHIPMENT,
        )

    def test_exact_alias_resolution_runs_before_pattern_priority(self):
        ChargeAlias.objects.create(
            alias_text='handling',
            match_type=ChargeAlias.MatchType.CONTAINS,
            mode_scope=ChargeAlias.ModeScope.EXPORT,
            direction_scope=ChargeAlias.DirectionScope.ORIGIN,
            product_code=self.export_fuel,
            priority=1,
        )
        exact_alias = ChargeAlias.objects.create(
            alias_text='terminal handling',
            match_type=ChargeAlias.MatchType.EXACT,
            mode_scope=ChargeAlias.ModeScope.EXPORT,
            direction_scope=ChargeAlias.DirectionScope.ORIGIN,
            product_code=self.export_terminal,
            priority=100,
        )

        result = resolve_charge_alias(
            '  Terminal Handling  ',
            mode_scope='EXPORT',
            direction_scope='ORIGIN',
        )

        self.assertEqual(result.normalization_status, NormalizationStatus.MATCHED)
        self.assertEqual(result.normalization_method, NormalizationMethod.EXACT_ALIAS)
        self.assertEqual(result.normalized_label, 'terminal handling')
        self.assertEqual(result.resolved_charge_alias, exact_alias)
        self.assertEqual(result.resolved_product_code, self.export_terminal)

    def test_scope_filter_uses_current_phase_one_semantics(self):
        ChargeAlias.objects.create(
            alias_text='pickup fee',
            match_type=ChargeAlias.MatchType.EXACT,
            mode_scope=ChargeAlias.ModeScope.EXPORT,
            direction_scope=ChargeAlias.DirectionScope.ORIGIN,
            product_code=self.export_terminal,
            priority=10,
        )

        unresolved = resolve_charge_alias('pickup fee')
        scoped = resolve_charge_alias(
            'pickup fee',
            mode_scope=ChargeAlias.ModeScope.EXPORT,
            direction_scope=ChargeAlias.DirectionScope.ORIGIN,
        )

        self.assertEqual(unresolved.normalization_status, NormalizationStatus.UNMAPPED)
        self.assertEqual(scoped.normalization_status, NormalizationStatus.MATCHED)
        self.assertEqual(scoped.resolved_product_code, self.export_terminal)

    def test_pattern_resolution_uses_priority_order(self):
        lower_priority = ChargeAlias.objects.create(
            alias_text='terminal',
            match_type=ChargeAlias.MatchType.CONTAINS,
            mode_scope=ChargeAlias.ModeScope.IMPORT,
            direction_scope=ChargeAlias.DirectionScope.DESTINATION,
            product_code=self.import_terminal,
            priority=30,
        )
        higher_priority = ChargeAlias.objects.create(
            alias_text='terminal handling',
            match_type=ChargeAlias.MatchType.STARTS_WITH,
            mode_scope=ChargeAlias.ModeScope.IMPORT,
            direction_scope=ChargeAlias.DirectionScope.DESTINATION,
            product_code=self.import_fuel,
            priority=10,
        )

        result = resolve_charge_alias(
            'Terminal Handling Fee',
            mode_scope='IMPORT',
            direction_scope='DESTINATION',
        )

        self.assertEqual(result.normalization_status, NormalizationStatus.MATCHED)
        self.assertEqual(result.normalization_method, NormalizationMethod.PATTERN_ALIAS)
        self.assertEqual(result.resolved_charge_alias, higher_priority)
        self.assertEqual(result.resolved_product_code, self.import_fuel)
        self.assertNotEqual(result.resolved_charge_alias, lower_priority)

    def test_same_top_priority_same_product_is_not_ambiguous(self):
        first = ChargeAlias.objects.create(
            alias_text='Fuel Surcharge',
            match_type=ChargeAlias.MatchType.EXACT,
            mode_scope=ChargeAlias.ModeScope.EXPORT,
            direction_scope=ChargeAlias.DirectionScope.MAIN,
            product_code=self.export_fuel,
            priority=5,
        )
        ChargeAlias.objects.create(
            alias_text='fuel surcharge',
            match_type=ChargeAlias.MatchType.EXACT,
            mode_scope=ChargeAlias.ModeScope.EXPORT,
            direction_scope=ChargeAlias.DirectionScope.MAIN,
            product_code=self.export_fuel,
            priority=5,
        )

        result = resolve_charge_alias(
            'fuel surcharge',
            mode_scope='EXPORT',
            direction_scope='MAIN',
        )

        self.assertEqual(result.normalization_status, NormalizationStatus.MATCHED)
        self.assertEqual(result.resolved_product_code, self.export_fuel)
        self.assertEqual(result.resolved_charge_alias, first)
        self.assertEqual(result.candidate_count, 2)

    def test_different_top_priority_outcomes_are_ambiguous(self):
        first = ChargeAlias.objects.create(
            alias_text='terminal fee',
            match_type=ChargeAlias.MatchType.EXACT,
            mode_scope=ChargeAlias.ModeScope.EXPORT,
            direction_scope=ChargeAlias.DirectionScope.ORIGIN,
            product_code=self.export_terminal,
            priority=10,
        )
        second = ChargeAlias.objects.create(
            alias_text='terminal fee',
            match_type=ChargeAlias.MatchType.EXACT,
            mode_scope=ChargeAlias.ModeScope.EXPORT,
            direction_scope=ChargeAlias.DirectionScope.ORIGIN,
            product_code=self.export_fuel,
            priority=10,
        )

        result = resolve_charge_alias(
            'terminal fee',
            mode_scope='EXPORT',
            direction_scope='ORIGIN',
        )

        self.assertEqual(result.normalization_status, NormalizationStatus.AMBIGUOUS)
        self.assertEqual(result.normalization_method, NormalizationMethod.EXACT_ALIAS)
        self.assertIsNone(result.resolved_charge_alias)
        self.assertIsNone(result.resolved_product_code)
        self.assertEqual(result.matched_alias_ids, (first.id, second.id))
        self.assertEqual(result.candidate_count, 2)

    def test_unmapped_when_no_active_alias_matches(self):
        ChargeAlias.objects.create(
            alias_text='doc fee',
            match_type=ChargeAlias.MatchType.EXACT,
            mode_scope=ChargeAlias.ModeScope.ANY,
            direction_scope=ChargeAlias.DirectionScope.ANY,
            product_code=self.export_terminal,
            priority=10,
            is_active=False,
        )

        result = resolve_charge_alias('random line item')

        self.assertEqual(result.normalization_status, NormalizationStatus.UNMAPPED)
        self.assertEqual(result.normalization_method, NormalizationMethod.NONE)
        self.assertIsNone(result.resolved_charge_alias)
        self.assertIsNone(result.resolved_product_code)
