from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from pricing_v4.models import ChargeAlias, ProductCode
from quotes.spot_models import SPEChargeLineDB, SPESourceBatchDB, SpotPricingEnvelopeDB


class CreateChargeAliasCandidatesCommandTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.customs_product = ProductCode.objects.create(
            id=2110,
            code="IMP-CUS-CLR-CAND",
            description="Import Customs Clearance Candidate",
            domain=ProductCode.DOMAIN_IMPORT,
            category=ProductCode.CATEGORY_CLEARANCE,
            is_gst_applicable=False,
            gst_rate="0.00",
            gst_treatment=ProductCode.GST_TREATMENT_ZERO_RATED,
            gl_revenue_code="4210",
            gl_cost_code="5210",
            default_unit=ProductCode.UNIT_SHIPMENT,
        )
        cls.agency_product = ProductCode.objects.create(
            id=2111,
            code="IMP-AGENCY-CAND",
            description="Import Agency Candidate",
            domain=ProductCode.DOMAIN_IMPORT,
            category=ProductCode.CATEGORY_AGENCY,
            is_gst_applicable=False,
            gst_rate="0.00",
            gst_treatment=ProductCode.GST_TREATMENT_ZERO_RATED,
            gl_revenue_code="4211",
            gl_cost_code="5211",
            default_unit=ProductCode.UNIT_SHIPMENT,
        )

    def test_repeated_manual_resolutions_create_one_inactive_candidate_alias(self):
        envelope, batch = self._create_import_source("China Agent")
        self._create_manual_line(envelope=envelope, batch=batch, label="CUS", product_code=self.customs_product)
        self._create_manual_line(envelope=envelope, batch=batch, label="CUS", product_code=self.customs_product)

        stdout = StringIO()
        call_command("create_charge_alias_candidates", "--min-occurrences=2", stdout=stdout)

        alias = ChargeAlias.objects.get(
            normalized_alias_text="cus",
            match_type=ChargeAlias.MatchType.EXACT,
            mode_scope=ChargeAlias.ModeScope.IMPORT,
            direction_scope=ChargeAlias.DirectionScope.ORIGIN,
            product_code=self.customs_product,
        )
        self.assertEqual(alias.alias_text, "CUS")
        self.assertFalse(alias.is_active)
        self.assertEqual(alias.alias_source, ChargeAlias.AliasSource.MANUAL_REVIEW)
        self.assertEqual(alias.review_status, ChargeAlias.ReviewStatus.CANDIDATE)
        self.assertIn("Occurrences=2", alias.notes)
        self.assertIn("- Created: 1", stdout.getvalue())

    def test_unstable_mixed_targets_do_not_create_candidates(self):
        envelope, batch = self._create_import_source("China Agent")
        self._create_manual_line(envelope=envelope, batch=batch, label="CUS", product_code=self.customs_product)
        self._create_manual_line(envelope=envelope, batch=batch, label="CUS", product_code=self.customs_product)
        self._create_manual_line(envelope=envelope, batch=batch, label="CUS", product_code=self.agency_product)

        stdout = StringIO()
        call_command("create_charge_alias_candidates", "--min-occurrences=2", stdout=stdout)

        self.assertFalse(ChargeAlias.objects.filter(normalized_alias_text="cus").exists())
        output = stdout.getvalue()
        self.assertIn("- Created: 0", output)
        self.assertIn("- Unstable mixed-target groups: 1", output)

    def test_existing_approved_alias_prevents_candidate_creation(self):
        envelope, batch = self._create_import_source("China Agent")
        self._create_manual_line(envelope=envelope, batch=batch, label="CUS", product_code=self.customs_product)
        self._create_manual_line(envelope=envelope, batch=batch, label="CUS", product_code=self.customs_product)
        ChargeAlias.objects.create(
            alias_text="CUS",
            match_type=ChargeAlias.MatchType.EXACT,
            mode_scope=ChargeAlias.ModeScope.IMPORT,
            direction_scope=ChargeAlias.DirectionScope.ORIGIN,
            product_code=self.customs_product,
            priority=10,
            is_active=True,
            alias_source=ChargeAlias.AliasSource.ADMIN,
            review_status=ChargeAlias.ReviewStatus.APPROVED,
        )

        stdout = StringIO()
        call_command("create_charge_alias_candidates", "--min-occurrences=2", stdout=stdout)

        self.assertEqual(
            ChargeAlias.objects.filter(
                normalized_alias_text="cus",
                mode_scope=ChargeAlias.ModeScope.IMPORT,
                direction_scope=ChargeAlias.DirectionScope.ORIGIN,
            ).count(),
            1,
        )
        output = stdout.getvalue()
        self.assertIn("- Created: 0", output)
        self.assertIn("- Skipped (approved/active equivalent exists): 1", output)

    def _create_import_source(self, label: str):
        envelope = SpotPricingEnvelopeDB.objects.create(
            status=SpotPricingEnvelopeDB.Status.DRAFT,
            shipment_context_json={
                "origin_country": "CN",
                "destination_country": "PG",
                "origin_code": "CAN",
                "destination_code": "POM",
            },
            conditions_json={},
            spot_trigger_reason_code="TEST",
            spot_trigger_reason_text="Test envelope",
            expires_at=timezone.now() + timedelta(hours=4),
        )
        batch = SPESourceBatchDB.objects.create(
            envelope=envelope,
            source_kind=SPESourceBatchDB.SourceKind.AGENT,
            source_type=SPESourceBatchDB.SourceType.EMAIL,
            target_bucket=SPESourceBatchDB.TargetBucket.ORIGIN_CHARGES,
            label=label,
            source_reference=f"{label}.eml",
        )
        return envelope, batch

    def _create_manual_line(self, *, envelope, batch, label, product_code):
        return SPEChargeLineDB.objects.create(
            envelope=envelope,
            source_batch=batch,
            code="ORIGIN_LOCAL_SPOT",
            description=label,
            amount="25.00",
            currency="USD",
            unit=SPEChargeLineDB.Unit.PER_SHIPMENT,
            bucket=SPEChargeLineDB.Bucket.ORIGIN_CHARGES,
            source_label=label,
            normalized_label=label.lower(),
            normalization_status=SPEChargeLineDB.NormalizationStatus.UNMAPPED,
            normalization_method=SPEChargeLineDB.NormalizationMethod.NONE,
            manual_resolution_status=SPEChargeLineDB.ManualResolutionStatus.RESOLVED,
            manual_resolved_product_code=product_code,
            source_reference=batch.source_reference,
            entered_at=timezone.now(),
        )
