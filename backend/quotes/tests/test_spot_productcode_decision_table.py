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
from quotes.spot_models import SPEChargeLineDB, SpotPricingEnvelopeDB
from quotes.management.commands.spot_productcode_remediation_plan import (
    APPLY_APPROVED_REQUEST,
    APPLY_EXISTING_PRODUCT_CODE,
    CREATE_ALIAS_MAPPING,
    CREATE_NEW_PRODUCT_CODE,
    MANUAL_REVIEW,
)


class SpotProductCodeDecisionTableTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="spot-decision-user",
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
        self.output_dir = Path("tmp")
        self.output_dir.mkdir(exist_ok=True)
        self.output_path = self.output_dir / "test_decision_table.csv"

    def tearDown(self):
        if self.output_path.exists():
            self.output_path.unlink()

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

    def _product_code(self, pc_id, code, description):
        return ProductCode.objects.create(
            id=pc_id,
            code=code,
            description=description,
            domain=ProductCode.DOMAIN_EXPORT,
            category=ProductCode.CATEGORY_DOCUMENTATION,
            is_gst_applicable=False,
            gst_rate="0.00",
            gst_treatment=ProductCode.GST_TREATMENT_ZERO_RATED,
            gl_revenue_code="4100",
            gl_cost_code="5100",
            default_unit=ProductCode.UNIT_SHIPMENT,
        )

    def test_one_row_per_unique_normalized_label(self):
        self._line("Fuel Surcharge")
        self._line(" fuel surcharge ")
        self._line("AWB Fee")

        call_command(
            "spot_productcode_decision_table",
            "--format",
            "csv",
            "--output",
            str(self.output_path),
        )

        with open(self.output_path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))

        self.assertEqual(len(rows), 2)
        labels = {row["normalized_label"] for row in rows}
        self.assertEqual(labels, {"fuel surcharge", "awb fee"})

    def test_exact_match_recommendation(self):
        self._line("AWB Fee")
        pc = self._product_code(9011, "EXP-AWB", "AWB Fee")
        ChargeAlias.objects.create(alias_text="AWB Fee", product_code=pc, match_type="EXACT")

        call_command(
            "spot_productcode_decision_table",
            "--format",
            "csv",
            "--output",
            str(self.output_path),
        )

        with open(self.output_path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))

        row = rows[0]
        self.assertEqual(row["recommended_action"], APPLY_EXISTING_PRODUCT_CODE)
        self.assertEqual(row["confidence"], "HIGH")
        self.assertEqual(row["requires_human_approval"], "false")
        self.assertEqual(row["recommended_product_code_id"], str(pc.id))

    def test_fuzzy_match_marked_human_approval(self):
        self._line("AWB Fee")
        pc = self._product_code(9011, "EXP-AWB", "AWB Fee")

        call_command(
            "spot_productcode_decision_table",
            "--format",
            "csv",
            "--output",
            str(self.output_path),
        )

        with open(self.output_path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))

        row = rows[0]
        self.assertEqual(row["recommended_action"], CREATE_ALIAS_MAPPING)
        self.assertEqual(row["confidence"], "MEDIUM")
        self.assertEqual(row["requires_human_approval"], "true")

    def test_new_product_code_candidates_left_blank(self):
        self._line("Air Transfer Fee")
        ProductCodeCreationRequest.objects.create(
            source_label="Air Transfer Fee",
            suggested_name="Air Transfer Fee",
            suggested_bucket="HANDLING",
            suggested_basis="SHIPMENT",
            created_by=self.user,
        )

        call_command(
            "spot_productcode_decision_table",
            "--format",
            "csv",
            "--output",
            str(self.output_path),
        )

        with open(self.output_path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))

        row = rows[0]
        self.assertEqual(row["recommended_action"], CREATE_NEW_PRODUCT_CODE)
        self.assertEqual(row["recommended_product_code_id"], "")
        self.assertEqual(row["requires_human_approval"], "true")

    def test_manual_review_rows_preserved(self):
        self._line("Mystery Fee")

        call_command(
            "spot_productcode_decision_table",
            "--format",
            "csv",
            "--output",
            str(self.output_path),
        )

        with open(self.output_path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))

        row = rows[0]
        self.assertEqual(row["recommended_action"], MANUAL_REVIEW)
        self.assertEqual(row["requires_human_approval"], "true")

    def test_csv_output_shape(self):
        self._line("Fuel Surcharge")

        call_command(
            "spot_productcode_decision_table",
            "--format",
            "csv",
            "--output",
            str(self.output_path),
        )

        with open(self.output_path, newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            header = next(reader)

        expected_columns = [
            "normalized_label",
            "display_labels_seen",
            "occurrence_count",
            "current_category",
            "current_action",
            "existing_matches",
            "fuzzy_matches",
            "recommended_action",
            "recommended_product_code_id",
            "recommended_product_code_code",
            "recommended_product_code_description",
            "confidence",
            "requires_human_approval",
            "decision_notes",
        ]
        self.assertEqual(header, expected_columns)
