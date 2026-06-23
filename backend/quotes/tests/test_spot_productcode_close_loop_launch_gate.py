import json
from datetime import timedelta
from io import StringIO
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from pricing_v4.models import ProductCode, ProductCodeCreationRequest, ChargeAlias
from quotes.spot_models import SPEChargeLineDB, SpotPricingEnvelopeDB
from quotes.management.commands.spot_productcode_close_loop_report import (
    READY,
    READY_EXCEPTIONS,
    NOT_READY,
)


class SpotProductCodeCloseLoopLaunchGateTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="spot-report-user",
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

    def _line(self, label, status=SPEChargeLineDB.NormalizationStatus.UNMAPPED):
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
            normalization_status=status,
            source_reference="test",
            entered_by=self.user,
            entered_at=timezone.now(),
        )

    def test_no_blockers_or_exceptions_reports_ready(self):
        stdout = StringIO()
        call_command("spot_productcode_close_loop_report", "--format", "json", stdout=stdout)
        payload = json.loads(stdout.getvalue())

        self.assertEqual(payload["readiness_status"], READY)
        self.assertEqual(payload["hard_blocker_count"], 0)
        self.assertEqual(payload["manual_review_exception_count"], 0)

    def test_only_manual_review_exceptions_reports_ready_exceptions(self):
        # "service fee" defaults to manual review exception (AMBIGUOUS_MANUAL_REVIEW_REQUIRED)
        self._line("Service Fee")

        stdout = StringIO()
        call_command("spot_productcode_close_loop_report", "--format", "json", stdout=stdout)
        payload = json.loads(stdout.getvalue())

        self.assertEqual(payload["readiness_status"], READY_EXCEPTIONS)
        self.assertEqual(payload["hard_blocker_count"], 0)
        self.assertEqual(payload["manual_review_exception_count"], 1)
        self.assertEqual(payload["manual_review_exceptions"][0]["source_label"], "Service Fee")

    def test_hard_blocker_unmapped_alias_reports_not_ready(self):
        # "awb fee" has canonical hint and will classify as ALIAS_MAPPING_REQUIRED (hard blocker)
        self._line("AWB Fee")

        stdout = StringIO()
        call_command("spot_productcode_close_loop_report", "--format", "json", stdout=stdout)
        payload = json.loads(stdout.getvalue())

        self.assertEqual(payload["readiness_status"], NOT_READY)
        self.assertEqual(payload["hard_blocker_count"], 1)

    def test_active_pending_request_blocks_launch(self):
        line = self._line("Service Fee")
        ProductCodeCreationRequest.objects.create(
            status=ProductCodeCreationRequest.STATUS_PENDING,
            source_envelope=self.envelope,
            source_charge_line=line,
            source_label="Service Fee",
            suggested_name="Service Fee",
            created_by=self.user,
        )


        stdout = StringIO()
        call_command("spot_productcode_close_loop_report", "--format", "json", stdout=stdout)
        payload = json.loads(stdout.getvalue())

        self.assertEqual(payload["readiness_status"], NOT_READY)
        self.assertEqual(payload["hard_blocker_count"], 2)
        self.assertEqual(payload["active_pending_product_code_request_count"], 1)
        self.assertEqual(payload["stale_pending_product_code_request_count"], 0)


    def test_stale_pending_request_does_not_block_launch(self):
        # Pending request exists, but the related line is already resolved
        line = self._line("Service Fee")
        line.manual_resolution_status = SPEChargeLineDB.ManualResolutionStatus.RESOLVED
        pc = ProductCode.objects.create(
            id=2099,
            code="IMP-SERV",
            description="Service",
            is_gst_applicable=False,
        )
        line.manual_resolved_product_code = pc
        line.save()

        ProductCodeCreationRequest.objects.create(
            status=ProductCodeCreationRequest.STATUS_PENDING,
            source_envelope=self.envelope,
            source_charge_line=line,
            source_label="Service Fee",
            suggested_name="Service Fee",
            created_by=self.user,
        )


        stdout = StringIO()
        call_command("spot_productcode_close_loop_report", "--format", "json", stdout=stdout)
        payload = json.loads(stdout.getvalue())

        self.assertEqual(payload["readiness_status"], READY)
        self.assertEqual(payload["hard_blocker_count"], 0)
        self.assertEqual(payload["active_pending_product_code_request_count"], 0)
        self.assertEqual(payload["stale_pending_product_code_request_count"], 1)
        self.assertEqual(payload["stale_pending_product_code_requests"][0]["source_label"], "Service Fee")

    def test_only_manual_review_exceptions_with_stale_pending_request(self):
        # One manual review line (unresolved)
        self._line("Labour Charge")

        # One resolved line with a pending request (stale request)
        line = self._line("Service Fee")
        line.manual_resolution_status = SPEChargeLineDB.ManualResolutionStatus.RESOLVED
        pc = ProductCode.objects.create(
            id=2099,
            code="IMP-SERV",
            description="Service",
            is_gst_applicable=False,
        )
        line.manual_resolved_product_code = pc
        line.save()

        ProductCodeCreationRequest.objects.create(
            status=ProductCodeCreationRequest.STATUS_PENDING,
            source_envelope=self.envelope,
            source_charge_line=line,
            source_label="Service Fee",
            suggested_name="Service Fee",
            created_by=self.user,
        )


        stdout = StringIO()
        call_command("spot_productcode_close_loop_report", "--format", "json", stdout=stdout)
        payload = json.loads(stdout.getvalue())

        self.assertEqual(payload["readiness_status"], READY_EXCEPTIONS)
        self.assertEqual(payload["hard_blocker_count"], 0)
        self.assertEqual(payload["manual_review_exception_count"], 1)
        self.assertEqual(payload["stale_pending_product_code_request_count"], 1)
