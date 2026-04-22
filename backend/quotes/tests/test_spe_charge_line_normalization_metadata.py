from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from pricing_v4.models import ChargeAlias, ProductCode
from quotes.spot_models import SPEChargeLineDB, SpotPricingEnvelopeDB


class SPEChargeLineNormalizationMetadataTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.product_code = ProductCode.objects.create(
            id=1094,
            code='EXP-HANDLING-SPOT',
            description='Export Handling Spot Charge',
            domain=ProductCode.DOMAIN_EXPORT,
            category=ProductCode.CATEGORY_HANDLING,
            is_gst_applicable=False,
            gst_rate='0.00',
            gst_treatment=ProductCode.GST_TREATMENT_ZERO_RATED,
            gl_revenue_code='4104',
            gl_cost_code='5104',
            default_unit=ProductCode.UNIT_SHIPMENT,
        )
        cls.charge_alias = ChargeAlias.objects.create(
            alias_text='terminal handling',
            match_type=ChargeAlias.MatchType.EXACT,
            mode_scope=ChargeAlias.ModeScope.EXPORT,
            direction_scope=ChargeAlias.DirectionScope.ORIGIN,
            product_code=cls.product_code,
            priority=10,
        )

    def _create_envelope(self):
        return SpotPricingEnvelopeDB.objects.create(
            status=SpotPricingEnvelopeDB.Status.DRAFT,
            shipment_context_json={
                'shipment_type': 'EXPORT',
                'service_scope': 'D2A',
                'origin_airport': 'POM',
                'destination_airport': 'BNE',
            },
            conditions_json={},
            spot_trigger_reason_code='TEST',
            spot_trigger_reason_text='Test envelope',
            expires_at=timezone.now() + timedelta(hours=4),
        )

    def test_existing_style_charge_line_can_save_without_normalization_metadata(self):
        line = SPEChargeLineDB.objects.create(
            envelope=self._create_envelope(),
            code='AIRFREIGHT_SPOT',
            description='Airfreight Spot',
            amount='100.00',
            currency='PGK',
            unit=SPEChargeLineDB.Unit.FLAT,
            bucket=SPEChargeLineDB.Bucket.AIRFREIGHT,
            source_reference='legacy-source',
            entered_at=timezone.now(),
        )

        self.assertEqual(line.source_label, '')
        self.assertEqual(line.normalized_label, '')
        self.assertIsNone(line.normalization_status)
        self.assertIsNone(line.normalization_method)
        self.assertIsNone(line.matched_alias)
        self.assertIsNone(line.resolved_product_code)

    def test_charge_line_can_persist_normalization_audit_metadata(self):
        line = SPEChargeLineDB.objects.create(
            envelope=self._create_envelope(),
            code='ORIGIN_LOCAL_SPOT',
            description='Terminal Handling',
            amount='25.00',
            currency='PGK',
            unit=SPEChargeLineDB.Unit.PER_SHIPMENT,
            bucket=SPEChargeLineDB.Bucket.ORIGIN_CHARGES,
            source_label='  Terminal Handling  ',
            normalized_label='terminal handling',
            normalization_status=SPEChargeLineDB.NormalizationStatus.MATCHED,
            normalization_method=SPEChargeLineDB.NormalizationMethod.EXACT_ALIAS,
            matched_alias=self.charge_alias,
            resolved_product_code=self.product_code,
            source_reference='agent-email',
            entered_at=timezone.now(),
        )

        refreshed = SPEChargeLineDB.objects.select_related(
            'matched_alias',
            'resolved_product_code',
        ).get(id=line.id)

        self.assertEqual(refreshed.source_label, '  Terminal Handling  ')
        self.assertEqual(refreshed.normalized_label, 'terminal handling')
        self.assertEqual(
            refreshed.normalization_status,
            SPEChargeLineDB.NormalizationStatus.MATCHED,
        )
        self.assertEqual(
            refreshed.normalization_method,
            SPEChargeLineDB.NormalizationMethod.EXACT_ALIAS,
        )
        self.assertEqual(refreshed.matched_alias, self.charge_alias)
        self.assertEqual(refreshed.resolved_product_code, self.product_code)
        self.assertEqual(refreshed.effective_resolved_product_code, self.product_code)
        self.assertEqual(
            refreshed.effective_resolution_status,
            SPEChargeLineDB.NormalizationStatus.MATCHED,
        )
        self.assertFalse(refreshed.requires_review)

    def test_unmapped_and_ambiguous_lines_require_review(self):
        unmapped = SPEChargeLineDB.objects.create(
            envelope=self._create_envelope(),
            code='DEST_LOCAL_SPOT',
            description='Destination fee',
            amount='15.00',
            currency='PGK',
            unit=SPEChargeLineDB.Unit.PER_SHIPMENT,
            bucket=SPEChargeLineDB.Bucket.DESTINATION_CHARGES,
            source_label='Destination fee',
            normalized_label='destination fee',
            normalization_status=SPEChargeLineDB.NormalizationStatus.UNMAPPED,
            normalization_method=SPEChargeLineDB.NormalizationMethod.NONE,
            source_reference='agent-email',
            entered_at=timezone.now(),
        )
        ambiguous = SPEChargeLineDB.objects.create(
            envelope=self._create_envelope(),
            code='DEST_LOCAL_SPOT',
            description='Destination handling',
            amount='15.00',
            currency='PGK',
            unit=SPEChargeLineDB.Unit.PER_SHIPMENT,
            bucket=SPEChargeLineDB.Bucket.DESTINATION_CHARGES,
            source_label='Destination handling',
            normalized_label='destination handling',
            normalization_status=SPEChargeLineDB.NormalizationStatus.AMBIGUOUS,
            normalization_method=SPEChargeLineDB.NormalizationMethod.EXACT_ALIAS,
            source_reference='agent-email',
            entered_at=timezone.now(),
        )

        self.assertEqual(
            unmapped.effective_resolution_status,
            SPEChargeLineDB.NormalizationStatus.UNMAPPED,
        )
        self.assertTrue(unmapped.requires_review)
        self.assertEqual(
            ambiguous.effective_resolution_status,
            SPEChargeLineDB.NormalizationStatus.AMBIGUOUS,
        )
        self.assertTrue(ambiguous.requires_review)

    def test_effective_resolved_product_code_prefers_manual_resolution_when_present(self):
        manual_product_code = ProductCode.objects.create(
            id=1096,
            code='EXP-HANDLING-MANUAL',
            description='Export Handling Manual Override',
            domain=ProductCode.DOMAIN_EXPORT,
            category=ProductCode.CATEGORY_HANDLING,
            is_gst_applicable=False,
            gst_rate='0.00',
            gst_treatment=ProductCode.GST_TREATMENT_ZERO_RATED,
            gl_revenue_code='4105',
            gl_cost_code='5105',
            default_unit=ProductCode.UNIT_SHIPMENT,
        )
        line = SPEChargeLineDB.objects.create(
            envelope=self._create_envelope(),
            code='ORIGIN_LOCAL_SPOT',
            description='Terminal Handling',
            amount='25.00',
            currency='PGK',
            unit=SPEChargeLineDB.Unit.PER_SHIPMENT,
            bucket=SPEChargeLineDB.Bucket.ORIGIN_CHARGES,
            source_label='Terminal Handling',
            normalized_label='terminal handling',
            normalization_status=SPEChargeLineDB.NormalizationStatus.MATCHED,
            normalization_method=SPEChargeLineDB.NormalizationMethod.EXACT_ALIAS,
            matched_alias=self.charge_alias,
            resolved_product_code=self.product_code,
            manual_resolution_status=SPEChargeLineDB.ManualResolutionStatus.RESOLVED,
            manual_resolved_product_code=manual_product_code,
            source_reference='agent-email',
            entered_at=timezone.now(),
        )

        refreshed = SPEChargeLineDB.objects.select_related(
            'resolved_product_code',
            'manual_resolved_product_code',
        ).get(id=line.id)

        self.assertEqual(refreshed.resolved_product_code, self.product_code)
        self.assertEqual(refreshed.manual_resolved_product_code, manual_product_code)
        self.assertEqual(refreshed.effective_resolved_product_code, manual_product_code)
        self.assertEqual(
            refreshed.effective_resolution_status,
            SPEChargeLineDB.ManualResolutionStatus.RESOLVED,
        )
        self.assertFalse(refreshed.requires_review)
