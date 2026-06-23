import csv
import json
from datetime import timedelta
from io import StringIO
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management import call_command, CommandError
from django.test import TestCase
from django.utils import timezone

from pricing_v4.models import ChargeAlias, ProductCode
from quotes.spot_models import SPEChargeLineDB, SpotPricingEnvelopeDB
from quotes.management.commands.spot_productcode_close_loop_report import build_report as build_close_loop_report



class SpotProductCodeDecisionApplyTests(TestCase):
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
        self.csv_dir = Path("tmp")
        self.csv_dir.mkdir(exist_ok=True)
        self.csv_path = self.csv_dir / "test_decision_reviewed.csv"

    def tearDown(self):
        if self.csv_path.exists():
            self.csv_path.unlink()

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
            normalized_label=label.lower(),
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

    def _write_csv(self, rows):
        fieldnames = [
            "normalized_label",
            "approved_action",
            "approved_product_code_id",
            "approved_product_code_code",
            "approved_product_code_description",
            "approved_create_product_code_id",
            "approved_create_product_code_code",
            "approved_create_product_code_description",
            "approved_create_product_code_domain",
            "approved_create_product_code_category",
            "approved_create_product_code_basis",
            "confidence",
            "approved_by_human",
            "decision_notes",
        ]
        with open(self.csv_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for r in rows:
                row_dict = {k: r.get(k, "") for k in fieldnames}
                writer.writerow(row_dict)

    def test_dry_run_performs_no_writes(self):
        line = self._line("AWB Fee")
        pc = self._product_code(9011, "EXP-AWB", "AWB Fee")
        self._write_csv([{
            "normalized_label": "awb fee",
            "approved_action": "CREATE_ALIAS_MAPPING",
            "approved_product_code_id": pc.id,
            "confidence": "HIGH",
            "approved_by_human": "true",
        }])

        stdout = StringIO()
        call_command(
            "spot_productcode_decision_apply",
            "--csv",
            str(self.csv_path),
            "--format",
            "json",
            stdout=stdout,
        )
        payload = json.loads(stdout.getvalue())

        self.assertTrue(payload["dry_run"])
        self.assertEqual(payload["charge_lines_resolved"], 1)

        # Verify DB not changed
        line.refresh_from_db()
        self.assertNotEqual(line.manual_resolution_status, SPEChargeLineDB.ManualResolutionStatus.RESOLVED)
        self.assertIsNone(line.manual_resolved_product_code)

    def test_apply_performs_writes(self):
        line = self._line("AWB Fee")
        pc = self._product_code(9011, "EXP-AWB", "AWB Fee")
        self._write_csv([{
            "normalized_label": "awb fee",
            "approved_action": "CREATE_ALIAS_MAPPING",
            "approved_product_code_id": pc.id,
            "confidence": "HIGH",
            "approved_by_human": "true",
        }])

        stdout = StringIO()
        call_command(
            "spot_productcode_decision_apply",
            "--csv",
            str(self.csv_path),
            "--apply",
            "--format",
            "json",
            stdout=stdout,
        )
        payload = json.loads(stdout.getvalue())

        self.assertFalse(payload["dry_run"])
        self.assertEqual(payload["charge_lines_resolved"], 1)

        # Verify DB is updated
        line.refresh_from_db()
        self.assertEqual(line.manual_resolution_status, SPEChargeLineDB.ManualResolutionStatus.RESOLVED)
        self.assertEqual(line.manual_resolved_product_code, pc)

    def test_unapproved_rows_skipped(self):
        line = self._line("AWB Fee")
        pc = self._product_code(9011, "EXP-AWB", "AWB Fee")
        self._write_csv([{
            "normalized_label": "awb fee",
            "approved_action": "CREATE_ALIAS_MAPPING",
            "approved_product_code_id": pc.id,
            "confidence": "HIGH",
            "approved_by_human": "false",
        }])

        stdout = StringIO()
        call_command(
            "spot_productcode_decision_apply",
            "--csv",
            str(self.csv_path),
            "--apply",
            "--format",
            "json",
            stdout=stdout,
        )
        payload = json.loads(stdout.getvalue())

        self.assertEqual(payload["charge_lines_resolved"], 0)
        self.assertEqual(payload["skipped_count"], 1)

    def test_low_confidence_rows_skipped(self):
        line = self._line("AWB Fee")
        pc = self._product_code(9011, "EXP-AWB", "AWB Fee")
        self._write_csv([{
            "normalized_label": "awb fee",
            "approved_action": "CREATE_ALIAS_MAPPING",
            "approved_product_code_id": pc.id,
            "confidence": "LOW",
            "approved_by_human": "true",
        }])

        stdout = StringIO()
        call_command(
            "spot_productcode_decision_apply",
            "--csv",
            str(self.csv_path),
            "--apply",
            "--format",
            "json",
            stdout=stdout,
        )
        payload = json.loads(stdout.getvalue())

        self.assertEqual(payload["charge_lines_resolved"], 0)
        self.assertEqual(payload["skipped_count"], 1)

    def test_create_alias_mapping_creates_alias_and_resolves_lines(self):
        line = self._line("AWB Fee")
        pc = self._product_code(9011, "EXP-AWB", "AWB Fee")
        self._write_csv([{
            "normalized_label": "awb fee",
            "approved_action": "CREATE_ALIAS_MAPPING",
            "approved_product_code_id": pc.id,
            "confidence": "HIGH",
            "approved_by_human": "true",
        }])

        stdout = StringIO()
        call_command(
            "spot_productcode_decision_apply",
            "--csv",
            str(self.csv_path),
            "--apply",
            "--format",
            "json",
            stdout=stdout,
        )
        payload = json.loads(stdout.getvalue())

        self.assertEqual(payload["aliases_created"], 1)
        self.assertEqual(payload["charge_lines_resolved"], 1)

        # Check alias in DB
        alias = ChargeAlias.objects.filter(normalized_alias_text="awb fee").first()
        self.assertIsNotNone(alias)
        self.assertEqual(alias.product_code, pc)

    def test_duplicate_alias_handled_safely(self):
        pc = self._product_code(9011, "EXP-AWB", "AWB Fee")
        ChargeAlias.objects.create(
            alias_text="awb fee",
            product_code=pc,
            is_active=True,
        )

        self._write_csv([{
            "normalized_label": "awb fee",
            "approved_action": "CREATE_ALIAS_MAPPING",
            "approved_product_code_id": pc.id,
            "confidence": "HIGH",
            "approved_by_human": "true",
        }])

        stdout = StringIO()
        call_command(
            "spot_productcode_decision_apply",
            "--csv",
            str(self.csv_path),
            "--apply",
            "--format",
            "json",
            stdout=stdout,
        )
        payload = json.loads(stdout.getvalue())

        self.assertEqual(payload["aliases_existing"], 1)
        self.assertEqual(payload["aliases_created"], 0)

    def test_missing_product_code_skips_safely(self):
        self._write_csv([{
            "normalized_label": "awb fee",
            "approved_action": "CREATE_ALIAS_MAPPING",
            "approved_product_code_id": 9999,
            "confidence": "HIGH",
            "approved_by_human": "true",
        }])

        stdout = StringIO()
        call_command(
            "spot_productcode_decision_apply",
            "--csv",
            str(self.csv_path),
            "--apply",
            "--format",
            "json",
            stdout=stdout,
        )
        payload = json.loads(stdout.getvalue())

        self.assertEqual(payload["error_count"], 1)
        self.assertEqual(payload["per_row_results"][0]["reason"], "PRODUCT_CODE_NOT_FOUND")

    def test_create_new_product_code_creates_product_code_and_resolves_lines(self):
        line = self._line("Air Transfer Fee")
        self._write_csv([{
            "normalized_label": "air transfer fee",
            "approved_action": "CREATE_NEW_PRODUCT_CODE",
            "approved_create_product_code_id": "2073",
            "approved_create_product_code_code": "IMP-AIR-TRANSFER",
            "approved_create_product_code_description": "Import Air Transfer Fee",
            "approved_create_product_code_domain": "IMPORT",
            "approved_create_product_code_category": "HANDLING",
            "approved_create_product_code_basis": "SHIPMENT",
            "confidence": "HIGH",
            "approved_by_human": "true",
        }])

        stdout = StringIO()
        call_command(
            "spot_productcode_decision_apply",
            "--csv",
            str(self.csv_path),
            "--apply",
            "--format",
            "json",
            stdout=stdout,
        )
        payload = json.loads(stdout.getvalue())

        self.assertEqual(payload["product_codes_created"], 1)
        self.assertEqual(payload["aliases_created"], 1)
        self.assertEqual(payload["charge_lines_resolved"], 1)

        # Verify created product code
        pc = ProductCode.objects.filter(id=2073).first()
        self.assertIsNotNone(pc)
        self.assertEqual(pc.code, "IMP-AIR-TRANSFER")
        self.assertEqual(pc.domain, "IMPORT")
        self.assertEqual(pc.category, "HANDLING")
        self.assertEqual(pc.default_unit, "SHIPMENT")

    def test_duplicate_product_code_skips_safely(self):
        self._product_code(2073, "IMP-AIR-TRANSFER", "Existing")
        self._write_csv([{
            "normalized_label": "air transfer fee",
            "approved_action": "CREATE_NEW_PRODUCT_CODE",
            "approved_create_product_code_id": "2073",
            "approved_create_product_code_code": "IMP-AIR-TRANSFER",
            "approved_create_product_code_description": "Import Air Transfer Fee",
            "approved_create_product_code_domain": "IMPORT",
            "approved_create_product_code_category": "HANDLING",
            "approved_create_product_code_basis": "SHIPMENT",
            "confidence": "HIGH",
            "approved_by_human": "true",
        }])

        stdout = StringIO()
        call_command(
            "spot_productcode_decision_apply",
            "--csv",
            str(self.csv_path),
            "--apply",
            "--format",
            "json",
            stdout=stdout,
        )
        payload = json.loads(stdout.getvalue())

        self.assertEqual(payload["error_count"], 1)
        self.assertEqual(payload["per_row_results"][0]["reason"], "DUPLICATE_PRODUCT_CODE_ID_OR_CODE")

    def test_leave_for_manual_review_does_not_resolve(self):
        line = self._line("Service Fee")
        self._write_csv([{
            "normalized_label": "service fee",
            "approved_action": "LEAVE_FOR_MANUAL_REVIEW",
            "confidence": "HIGH",
            "approved_by_human": "true",
        }])

        stdout = StringIO()
        call_command(
            "spot_productcode_decision_apply",
            "--csv",
            str(self.csv_path),
            "--apply",
            "--format",
            "json",
            stdout=stdout,
        )
        payload = json.loads(stdout.getvalue())

        self.assertEqual(payload["manual_review_deferred"], 1)
        self.assertEqual(payload["charge_lines_resolved"], 0)

        # Check not resolved
        line.refresh_from_db()
        self.assertNotEqual(line.manual_resolution_status, SPEChargeLineDB.ManualResolutionStatus.RESOLVED)

    def test_robust_matching_with_en_dash(self):
        line1 = self._line("airfreight akl – pom via px(bne)")
        line2 = self._line("airfreight akl - pom via px(bne)")
        pc = self._product_code(2001, "IMP-FRT-AIR", "Import Air Freight")

        self._write_csv([{
            "normalized_label": "airfreight akl – pom via px(bne)",
            "approved_action": "CREATE_ALIAS_MAPPING",
            "approved_product_code_id": pc.id,
            "confidence": "HIGH",
            "approved_by_human": "true",
        }])

        stdout = StringIO()
        call_command(
            "spot_productcode_decision_apply",
            "--csv",
            str(self.csv_path),
            "--apply",
            "--format",
            "json",
            stdout=stdout,
        )
        payload = json.loads(stdout.getvalue())

        self.assertEqual(payload["charge_lines_resolved"], 2)

        line1.refresh_from_db()
        line2.refresh_from_db()
        self.assertEqual(line1.manual_resolution_status, SPEChargeLineDB.ManualResolutionStatus.RESOLVED)
        self.assertEqual(line2.manual_resolution_status, SPEChargeLineDB.ManualResolutionStatus.RESOLVED)

    def test_json_output_shape(self):
        self._write_csv([])
        stdout = StringIO()
        call_command(
            "spot_productcode_decision_apply",
            "--csv",
            str(self.csv_path),
            "--format",
            "json",
            stdout=stdout,
        )
        payload = json.loads(stdout.getvalue())

        expected_keys = {
            "dry_run",
            "writes_performed",
            "approved_rows_seen",
            "aliases_created",
            "aliases_existing",
            "product_codes_created",
            "charge_lines_resolved",
            "manual_review_deferred",
            "skipped_count",
            "error_count",
            "readiness_before",
            "readiness_after",
            "unique_charge_lines_selected",
            "duplicate_charge_line_matches",
            "charge_line_ids_selected",
            "per_row_results",
        }
        self.assertTrue(expected_keys.issubset(payload.keys()))

    def test_duplicate_charge_line_de_duplication(self):
        line = self._line("AWB Fee")
        pc = self._product_code(9011, "EXP-AWB", "AWB Fee")
        # Define two rows that both match the same normalized_label
        self._write_csv([
            {
                "normalized_label": "awb fee",
                "approved_action": "CREATE_ALIAS_MAPPING",
                "approved_product_code_id": pc.id,
                "confidence": "HIGH",
                "approved_by_human": "true",
            },
            {
                "normalized_label": "awb fee",
                "approved_action": "CREATE_ALIAS_MAPPING",
                "approved_product_code_id": pc.id,
                "confidence": "HIGH",
                "approved_by_human": "true",
            }
        ])

        stdout = StringIO()
        call_command(
            "spot_productcode_decision_apply",
            "--csv",
            str(self.csv_path),
            "--apply",
            "--format",
            "json",
            stdout=stdout,
        )
        payload = json.loads(stdout.getvalue())

        self.assertEqual(payload["charge_lines_resolved"], 1)
        self.assertEqual(payload["unique_charge_lines_selected"], 1)
        self.assertEqual(payload["duplicate_charge_line_matches"], 1)

    def test_safety_check_fails_when_exceeding_baseline(self):
        self._line("AWB Fee")
        self._line("Doc Fee")
        pc = self._product_code(9011, "EXP-AWB", "AWB Fee")
        self._write_csv([
            {
                "normalized_label": "awb fee",
                "approved_action": "CREATE_ALIAS_MAPPING",
                "approved_product_code_id": pc.id,
                "confidence": "HIGH",
                "approved_by_human": "true",
            },
            {
                "normalized_label": "doc fee",
                "approved_action": "CREATE_ALIAS_MAPPING",
                "approved_product_code_id": pc.id,
                "confidence": "HIGH",
                "approved_by_human": "true",
            }
        ])

        # We mock build_close_loop_report to return baseline unresolved lines = 1
        # but our CSV will resolve 2 lines. This should fail the safety check.
        original_build = build_close_loop_report
        try:
            # Overwrite global function mock
            import quotes.management.commands.spot_productcode_decision_apply as target_module
            target_module.build_close_loop_report = lambda: {
                "readiness_status": "NOT_READY_FOR_LAUNCH",
                "blocking_counts": {
                    "unresolved_product_code_review_lines": 1
                }
            }

            with self.assertRaises(CommandError):
                call_command(
                    "spot_productcode_decision_apply",
                    "--csv",
                    str(self.csv_path),
                    "--apply",
                    "--format",
                    "json",
                )
        finally:
            import quotes.management.commands.spot_productcode_decision_apply as target_module
            target_module.build_close_loop_report = original_build
