from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from pricing_v4.models import ChargeAlias, ProductCode
from quotes.spot_models import SPEChargeLineDB, SPESourceBatchDB, SpotPricingEnvelopeDB


class SummarizeChargeAliasActivityCommandTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.manual_product = ProductCode.objects.create(
            id=2105,
            code="IMP-CUS-CLR-T",
            description="Import Customs Clearance Test",
            domain=ProductCode.DOMAIN_IMPORT,
            category=ProductCode.CATEGORY_CLEARANCE,
            is_gst_applicable=False,
            gst_rate="0.00",
            gst_treatment=ProductCode.GST_TREATMENT_ZERO_RATED,
            gl_revenue_code="4205",
            gl_cost_code="5205",
            default_unit=ProductCode.UNIT_SHIPMENT,
        )

    def test_command_surfaces_recurring_unmapped_and_manual_resolution_candidates(self):
        envelope, batch = self._create_import_source("China Agent")
        self._create_line(
            envelope=envelope,
            batch=batch,
            label="Odd Handling",
            normalized_label="odd handling",
            normalization_status=SPEChargeLineDB.NormalizationStatus.UNMAPPED,
        )
        self._create_line(
            envelope=envelope,
            batch=batch,
            label="Odd Handling",
            normalized_label="odd handling",
            normalization_status=SPEChargeLineDB.NormalizationStatus.UNMAPPED,
        )
        self._create_line(
            envelope=envelope,
            batch=batch,
            label="CUS",
            normalized_label="cus",
            normalization_status=SPEChargeLineDB.NormalizationStatus.UNMAPPED,
            manual_product_code=self.manual_product,
        )
        self._create_line(
            envelope=envelope,
            batch=batch,
            label="CUS",
            normalized_label="cus",
            normalization_status=SPEChargeLineDB.NormalizationStatus.UNMAPPED,
            manual_product_code=self.manual_product,
        )

        stdout = StringIO()
        call_command(
            "summarize_charge_alias_activity",
            "--limit=5",
            "--min-occurrences=2",
            stdout=stdout,
        )

        output = stdout.getvalue()
        self.assertIn("Top recurring unmapped labels", output)
        self.assertIn("'odd handling'", output)
        self.assertIn("Top recurring manually resolved labels", output)
        self.assertIn("targets=IMP-CUS-CLR-T", output)
        self.assertIn("Promotion candidates from repeated manual resolutions", output)
        self.assertIn("EXACT 'cus' | IMPORT/ORIGIN -> IMP-CUS-CLR-T", output)

    def test_existing_exact_alias_suppresses_candidate_promotion_row(self):
        envelope, batch = self._create_import_source("China Agent")
        self._create_line(
            envelope=envelope,
            batch=batch,
            label="CUS",
            normalized_label="cus",
            normalization_status=SPEChargeLineDB.NormalizationStatus.UNMAPPED,
            manual_product_code=self.manual_product,
        )
        self._create_line(
            envelope=envelope,
            batch=batch,
            label="CUS",
            normalized_label="cus",
            normalization_status=SPEChargeLineDB.NormalizationStatus.UNMAPPED,
            manual_product_code=self.manual_product,
        )
        ChargeAlias.objects.create(
            alias_text="CUS",
            match_type=ChargeAlias.MatchType.EXACT,
            mode_scope=ChargeAlias.ModeScope.IMPORT,
            direction_scope=ChargeAlias.DirectionScope.ORIGIN,
            product_code=self.manual_product,
            priority=10,
            is_active=True,
            alias_source=ChargeAlias.AliasSource.ADMIN,
            review_status=ChargeAlias.ReviewStatus.APPROVED,
        )

        stdout = StringIO()
        call_command(
            "summarize_charge_alias_activity",
            "--limit=5",
            "--min-occurrences=2",
            stdout=stdout,
        )

        output = stdout.getvalue()
        self.assertIn("Promotion candidates from repeated manual resolutions", output)
        self.assertNotIn("EXACT 'cus' | IMPORT/ORIGIN -> IMP-CUS-CLR-T", output)

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

    def _create_line(
        self,
        *,
        envelope: SpotPricingEnvelopeDB,
        batch: SPESourceBatchDB,
        label: str,
        normalized_label: str,
        normalization_status: str,
        manual_product_code: ProductCode | None = None,
    ):
        kwargs = {}
        if manual_product_code is not None:
            kwargs.update(
                manual_resolution_status=SPEChargeLineDB.ManualResolutionStatus.RESOLVED,
                manual_resolved_product_code=manual_product_code,
            )
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
            normalized_label=normalized_label,
            normalization_status=normalization_status,
            normalization_method=SPEChargeLineDB.NormalizationMethod.NONE,
            source_reference=batch.source_reference,
            entered_at=timezone.now(),
            **kwargs,
        )
