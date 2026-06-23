import json
from datetime import timedelta
from io import StringIO
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management import call_command, CommandError
from django.test import TestCase
from django.utils import timezone

from pricing_v4.models import ChargeAlias, ProductCode, ProductCodeCreationRequest
from quotes.spot_models import SPEChargeLineDB, SpotPricingEnvelopeDB
from quotes.management.commands.spot_productcode_remediation_apply import (
    APPLY_APPROVED_REQUEST,
    APPLY_EXISTING_PRODUCT_CODE,
    CREATE_ALIAS_MAPPING,
)


class SpotProductCodeRemediationApplyTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="spot-apply-user",
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
        self.plan_dir = Path("tmp")
        self.plan_dir.mkdir(exist_ok=True)
        self.plan_path = self.plan_dir / "test_remediation_plan.json"

    def tearDown(self):
        if self.plan_path.exists():
            self.plan_path.unlink()

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

    def _write_plan(self, plan_dict):
        with open(self.plan_path, "w", encoding="utf-8") as f:
            json.dump({"plan": plan_dict}, f)

    def test_requires_explicit_action_group(self):
        self._write_plan({})
        with self.assertRaises(CommandError) as ctx:
            call_command("spot_productcode_remediation_apply", "--plan", str(self.plan_path))
        self.assertIn("At least one explicit --action-group must be provided", str(ctx.exception))

    def test_dry_run_performs_no_writes(self):
        line = self._line("AWB Fee")
        pc = self._product_code(9011, "EXP-AWB", "AWB Fee")
        
        plan = {
            APPLY_APPROVED_REQUEST: [
                {
                    "normalized_label": "awb fee",
                    "recommended_product_code_id": pc.id,
                    "confidence": "HIGH",
                    "affected_charge_line_ids": [str(line.id)],
                }
            ]
        }
        self._write_plan(plan)

        stdout = StringIO()
        call_command(
            "spot_productcode_remediation_apply",
            "--plan",
            str(self.plan_path),
            "--action-group",
            APPLY_APPROVED_REQUEST,
            stdout=stdout,
        )
        payload = json.loads(stdout.getvalue())

        self.assertTrue(payload["dry_run"])
        self.assertEqual(payload["applied_count"], 1)
        self.assertEqual(payload["skipped_count"], 0)

        # Refresh from DB and verify no writes occurred
        line.refresh_from_db()
        self.assertNotEqual(line.manual_resolution_status, SPEChargeLineDB.ManualResolutionStatus.RESOLVED)
        self.assertIsNone(line.manual_resolved_product_code)

    def test_apply_performs_writes(self):
        line = self._line("AWB Fee")
        pc = self._product_code(9011, "EXP-AWB", "AWB Fee")
        
        plan = {
            APPLY_APPROVED_REQUEST: [
                {
                    "normalized_label": "awb fee",
                    "recommended_product_code_id": pc.id,
                    "confidence": "HIGH",
                    "affected_charge_line_ids": [str(line.id)],
                }
            ]
        }
        self._write_plan(plan)

        stdout = StringIO()
        call_command(
            "spot_productcode_remediation_apply",
            "--plan",
            str(self.plan_path),
            "--apply",
            "--action-group",
            APPLY_APPROVED_REQUEST,
            stdout=stdout,
        )
        payload = json.loads(stdout.getvalue())

        self.assertFalse(payload["dry_run"])
        self.assertEqual(payload["applied_count"], 1)

        # Verify DB is updated
        line.refresh_from_db()
        self.assertEqual(line.manual_resolution_status, SPEChargeLineDB.ManualResolutionStatus.RESOLVED)
        self.assertEqual(line.manual_resolved_product_code_id, pc.id)

    def test_apply_existing_product_code_requires_high_confidence(self):
        line = self._line("AWB Fee")
        pc = self._product_code(9011, "EXP-AWB", "AWB Fee")
        
        plan = {
            APPLY_EXISTING_PRODUCT_CODE: [
                {
                    "normalized_label": "awb fee",
                    "recommended_product_code_id": pc.id,
                    "confidence": "MEDIUM",
                    "affected_charge_line_ids": [str(line.id)],
                }
            ]
        }
        self._write_plan(plan)

        stdout = StringIO()
        call_command(
            "spot_productcode_remediation_apply",
            "--plan",
            str(self.plan_path),
            "--apply",
            "--action-group",
            APPLY_EXISTING_PRODUCT_CODE,
            stdout=stdout,
        )
        payload = json.loads(stdout.getvalue())

        self.assertEqual(payload["applied_count"], 0)
        self.assertEqual(payload["skipped_count"], 1)
        self.assertEqual(payload["per_action_results"][0]["reason"], "LOW_CONFIDENCE")

    def test_stale_label_mismatch_skipped(self):
        line = self._line("AWB Fee")
        pc = self._product_code(9011, "EXP-AWB", "AWB Fee")
        
        plan = {
            APPLY_APPROVED_REQUEST: [
                {
                    "normalized_label": "mismatched label",
                    "recommended_product_code_id": pc.id,
                    "confidence": "HIGH",
                    "affected_charge_line_ids": [str(line.id)],
                }
            ]
        }
        self._write_plan(plan)

        stdout = StringIO()
        call_command(
            "spot_productcode_remediation_apply",
            "--plan",
            str(self.plan_path),
            "--apply",
            "--action-group",
            APPLY_APPROVED_REQUEST,
            stdout=stdout,
        )
        payload = json.loads(stdout.getvalue())

        self.assertEqual(payload["applied_count"], 0)
        self.assertEqual(payload["skipped_count"], 1)
        self.assertEqual(payload["per_action_results"][0]["reason"], "STALE_LABEL_MISMATCH")

    def test_missing_charge_line_skipped_safely(self):
        pc = self._product_code(9011, "EXP-AWB", "AWB Fee")
        fake_uuid = "00000000-0000-0000-0000-000000000000"
        
        plan = {
            APPLY_APPROVED_REQUEST: [
                {
                    "normalized_label": "awb fee",
                    "recommended_product_code_id": pc.id,
                    "confidence": "HIGH",
                    "affected_charge_line_ids": [fake_uuid],
                }
            ]
        }
        self._write_plan(plan)

        stdout = StringIO()
        call_command(
            "spot_productcode_remediation_apply",
            "--plan",
            str(self.plan_path),
            "--apply",
            "--action-group",
            APPLY_APPROVED_REQUEST,
            stdout=stdout,
        )
        payload = json.loads(stdout.getvalue())

        self.assertEqual(payload["applied_count"], 0)
        self.assertEqual(payload["skipped_count"], 1)
        self.assertEqual(payload["per_action_results"][0]["reason"], "CHARGE_LINE_NOT_FOUND")

    def test_missing_product_code_skipped_safely(self):
        line = self._line("AWB Fee")
        
        plan = {
            APPLY_APPROVED_REQUEST: [
                {
                    "normalized_label": "awb fee",
                    "recommended_product_code_id": 9999,
                    "confidence": "HIGH",
                    "affected_charge_line_ids": [str(line.id)],
                }
            ]
        }
        self._write_plan(plan)

        stdout = StringIO()
        call_command(
            "spot_productcode_remediation_apply",
            "--plan",
            str(self.plan_path),
            "--apply",
            "--action-group",
            APPLY_APPROVED_REQUEST,
            stdout=stdout,
        )
        payload = json.loads(stdout.getvalue())

        self.assertEqual(payload["applied_count"], 0)
        self.assertEqual(payload["skipped_count"], 1)
        self.assertEqual(payload["per_action_results"][0]["reason"], "PRODUCT_CODE_NOT_FOUND")

    def test_create_alias_mapping_creates_alias_and_resolves_lines(self):
        line = self._line("AWB Fee")
        pc = self._product_code(9011, "EXP-AWB", "AWB Fee")

        plan = {
            CREATE_ALIAS_MAPPING: [
                {
                    "normalized_label": "awb fee",
                    "recommended_product_code_id": pc.id,
                    "confidence": "HIGH",
                    "affected_charge_line_ids": [str(line.id)],
                }
            ]
        }
        self._write_plan(plan)

        stdout = StringIO()
        call_command(
            "spot_productcode_remediation_apply",
            "--plan",
            str(self.plan_path),
            "--apply",
            "--action-group",
            CREATE_ALIAS_MAPPING,
            stdout=stdout,
        )
        payload = json.loads(stdout.getvalue())

        self.assertEqual(payload["applied_count"], 1)

        # Check ChargeAlias was created
        alias = ChargeAlias.objects.filter(normalized_alias_text="awb fee").first()
        self.assertIsNotNone(alias)
        self.assertEqual(alias.product_code, pc)

        # Check line was resolved
        line.refresh_from_db()
        self.assertEqual(line.manual_resolution_status, SPEChargeLineDB.ManualResolutionStatus.RESOLVED)
        self.assertEqual(line.manual_resolved_product_code, pc)
