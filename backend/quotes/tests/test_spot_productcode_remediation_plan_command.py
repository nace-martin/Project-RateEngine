import csv
import json
from datetime import timedelta
from io import StringIO
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from pricing_v4.models import ChargeAlias, ProductCode, ProductCodeCreationRequest
from quotes.management.commands.spot_productcode_remediation_plan import (
    APPLY_APPROVED_REQUEST,
    APPLY_EXISTING_PRODUCT_CODE,
    CREATE_ALIAS_MAPPING,
    CREATE_NEW_PRODUCT_CODE,
    MANUAL_REVIEW,
    build_remediation_plan,
)
from quotes.spot_models import SPEChargeLineDB, SpotPricingEnvelopeDB


class SpotProductCodeRemediationPlanTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="spot-plan-user",
            password="pass123",
            role="sales",
        )

    def setUp(self):
        self.envelope = SpotPricingEnvelopeDB.objects.create(
            status=SpotPricingEnvelopeDB.Status.DRAFT,
            shipment_context_json={"origin_code": "POM", "destination_code": "SYD"},
            conditions_json={},
            spot_trigger_reason_code="MISSING_SCOPE_RATES",
            spot_trigger_reason_text="Missing required rate components",
            created_by=self.user,
            expires_at=timezone.now() + timedelta(hours=4),
        )

    def _line(self, label):
        return SPEChargeLineDB.objects.create(
            envelope=self.envelope,
            code="UNMAPPED",
            description=label,
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

    def _product_code(self, pc_id, code, description, category=ProductCode.CATEGORY_DOCUMENTATION):
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

    def test_groups_duplicate_label_with_affected_ids(self):
        first = self._line("Fuel Surcharge")
        second = self._line(" fuel surcharge ")
        pc = self._product_code(9010, "EXP-FUEL", "Fuel Surcharge", ProductCode.CATEGORY_SURCHARGE)

        report = build_remediation_plan()
        item = report["plan"][CREATE_ALIAS_MAPPING][0]

        self.assertEqual(item["normalized_label"], "fuel surcharge")
        self.assertEqual(item["occurrence_count"], 2)
        self.assertCountEqual(item["affected_charge_line_ids"], [str(first.id), str(second.id)])
        self.assertEqual(item["recommended_product_code_id"], pc.id)

    def test_existing_alias_recommends_apply_existing_product_code(self):
        self._line("AWB Fee")
        pc = self._product_code(9011, "EXP-AWB", "AWB Fee")
        ChargeAlias.objects.create(alias_text="AWB Fee", product_code=pc, match_type="EXACT")

        item = build_remediation_plan()["plan"][APPLY_EXISTING_PRODUCT_CODE][0]

        self.assertEqual(item["recommended_product_code_code"], "EXP-AWB")
        self.assertEqual(item["confidence"], "HIGH")

    def test_approved_request_recommends_apply_approved_request(self):
        self._line("Admin Fee")
        pc = self._product_code(9012, "EXP-ADMIN", "Admin Fee")
        ProductCodeCreationRequest.objects.create(
            source_label="Admin Fee",
            suggested_name="Admin Fee",
            suggested_bucket="DOCUMENTATION",
            suggested_basis="SHIPMENT",
            status=ProductCodeCreationRequest.STATUS_APPROVED,
            approved_product_code=pc,
            approved_at=timezone.now(),
            created_by=self.user,
        )

        item = build_remediation_plan()["plan"][APPLY_APPROVED_REQUEST][0]

        self.assertEqual(item["recommended_product_code_id"], pc.id)
        self.assertEqual(item["approved_request_match"]["status"], "APPROVED")

    def test_new_product_code_and_manual_review_groups(self):
        self._line("Air Transfer Fee")
        self._line("Mystery One-Off")
        ProductCodeCreationRequest.objects.create(
            source_label="Air Transfer Fee",
            suggested_name="Air Transfer Fee",
            suggested_bucket="HANDLING",
            suggested_basis="SHIPMENT",
            created_by=self.user,
        )

        report = build_remediation_plan()

        self.assertEqual(report["plan"][CREATE_NEW_PRODUCT_CODE][0]["normalized_label"], "air transfer fee")
        self.assertIsNone(report["plan"][CREATE_NEW_PRODUCT_CODE][0]["recommended_product_code_id"])
        self.assertEqual(report["plan"][MANUAL_REVIEW][0]["normalized_label"], "mystery one-off")

    def test_command_json_output_shape(self):
        self._line("Unknown Local Fee")
        stdout = StringIO()

        call_command("spot_productcode_remediation_plan", "--format", "json", stdout=stdout)
        payload = json.loads(stdout.getvalue())

        self.assertFalse(payload["summary"]["writes_performed"])
        self.assertIn(MANUAL_REVIEW, payload["plan"])

    def test_command_csv_output_shape(self):
        self._line("Unknown Local Fee")
        output = Path("tmp/test_spot_productcode_remediation_plan.csv")
        output.parent.mkdir(exist_ok=True)

        call_command("spot_productcode_remediation_plan", "--format", "csv", "--output", str(output))

        with output.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(rows[0]["action_required"], MANUAL_REVIEW)
        self.assertEqual(rows[0]["normalized_label"], "unknown local fee")
