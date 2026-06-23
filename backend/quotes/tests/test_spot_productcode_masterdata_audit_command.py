import json
from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone

from pricing_v4.models import ProductCode, ProductCodeCreationRequest
from quotes.management.commands.spot_productcode_masterdata_audit import (
    CATEGORY_ALIAS_REQUIRED,
    CATEGORY_NEW_PRODUCT_CODE,
    NOT_READY,
    READY,
    build_masterdata_audit,
)
from quotes.spot_models import SPEChargeLineDB, SpotPricingEnvelopeDB


class SpotProductCodeMasterDataAuditTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="spot-audit-user",
            password="pass123",
            role="sales",
        )

    def setUp(self):
        self.envelope = SpotPricingEnvelopeDB.objects.create(
            status=SpotPricingEnvelopeDB.Status.DRAFT,
            shipment_context_json={
                "origin_country": "PG",
                "destination_country": "AU",
                "origin_code": "POM",
                "destination_code": "SYD",
            },
            conditions_json={},
            spot_trigger_reason_code="MISSING_SCOPE_RATES",
            spot_trigger_reason_text="Missing required rate components",
            created_by=self.user,
            expires_at=timezone.now() + timedelta(hours=4),
        )

    def _line(self, *, label: str, description: str | None = None):
        return SPEChargeLineDB.objects.create(
            envelope=self.envelope,
            code="UNMAPPED",
            description=description or label,
            amount="10.00",
            currency="PGK",
            unit=SPEChargeLineDB.Unit.PER_SHIPMENT,
            bucket=SPEChargeLineDB.Bucket.ORIGIN_CHARGES,
            source_label=label,
            normalized_label=ProductCodeCreationRequest.normalize_label(label),
            normalization_status=SPEChargeLineDB.NormalizationStatus.UNMAPPED,
            source_reference="test",
            entered_by=self.user,
            entered_at=timezone.now(),
        )

    def _product_code(self, *, pc_id: int, code: str, description: str, category: str):
        return ProductCode.objects.create(
            id=pc_id,
            code=code,
            description=description,
            domain=ProductCode.DOMAIN_EXPORT,
            category=category,
            is_gst_applicable=False,
            gst_rate="0.00",
            gst_treatment=ProductCode.GST_TREATMENT_ZERO_RATED,
            gl_revenue_code="4100",
            gl_cost_code="5100",
            default_unit=ProductCode.UNIT_SHIPMENT,
        )

    def test_empty_dataset_is_ready(self):
        report = build_masterdata_audit()

        self.assertEqual(report["readiness_status"], READY)
        self.assertEqual(report["readiness_summary"]["unique_unresolved_labels"], 0)
        self.assertEqual(report["labels"], [])

    def test_aggregates_duplicate_normalized_labels_and_reports_counts(self):
        self._line(label="Fuel Surcharge")
        self._line(label="  fuel   surcharge  ", description="Fuel surcharge")
        self._product_code(
            pc_id=1097,
            code="EXP-FUEL-SUR",
            description="Fuel Surcharge",
            category=ProductCode.CATEGORY_SURCHARGE,
        )

        report = build_masterdata_audit()

        self.assertEqual(report["readiness_status"], NOT_READY)
        self.assertEqual(report["readiness_summary"]["unique_unresolved_labels"], 1)
        self.assertEqual(report["readiness_summary"]["unresolved_charge_lines"], 2)
        label = report["labels"][0]
        self.assertEqual(label["normalized_label"], "fuel surcharge")
        self.assertEqual(label["occurrence_count"], 2)
        self.assertEqual(label["remediation_category"], CATEGORY_ALIAS_REQUIRED)
        self.assertEqual(len(label["existing_product_code_matches"]), 1)

    def test_pending_request_counts_as_new_product_code_required(self):
        self._line(label="Air Transfer Fee")
        ProductCodeCreationRequest.objects.create(
            source_label="Air Transfer Fee",
            suggested_name="Air Transfer Fee",
            suggested_bucket="HANDLING",
            suggested_basis="SHIPMENT",
            created_by=self.user,
        )

        report = build_masterdata_audit()
        label = report["labels"][0]

        self.assertEqual(label["normalized_label"], "air transfer fee")
        self.assertEqual(label["remediation_category"], CATEGORY_NEW_PRODUCT_CODE)
        self.assertEqual(label["pending_product_code_request_matches"][0]["status"], "PENDING")
        self.assertEqual(report["readiness_summary"]["category_counts"][CATEGORY_NEW_PRODUCT_CODE], 1)

    def test_command_json_output_includes_readiness_summary(self):
        self._line(label="Unknown Local Fee")

        stdout = StringIO()
        call_command("spot_productcode_masterdata_audit", "--format", "json", stdout=stdout)
        payload = json.loads(stdout.getvalue())

        self.assertEqual(payload["readiness_status"], NOT_READY)
        self.assertEqual(payload["readiness_summary"]["unique_unresolved_labels"], 1)
        self.assertIn("category_counts", payload["readiness_summary"])
