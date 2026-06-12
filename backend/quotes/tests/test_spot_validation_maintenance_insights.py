import datetime
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from quotes.spot_models import (
    SpotPricingEnvelopeDB,
    SpotTemplateValidationSnapshot,
    SpotTemplateValidationEvent,
    ExpectedChargeTemplate
)


class SpotTemplateValidationMaintenanceInsightsTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.manager_user = User.objects.create_user(
            username="manager_test",
            password="password123",
            email="manager@example.com",
            role="manager"
        )
        self.sales_user = User.objects.create_user(
            username="sales_test",
            password="password123",
            email="sales@example.com",
            role="sales"
        )

        self.envelope = SpotPricingEnvelopeDB.objects.create(
            status="draft",
            shipment_context_json={"origin_country": "SG", "destination_country": "PG"},
            expires_at=timezone.now() + datetime.timedelta(days=2),
            spot_trigger_reason_code="MANUAL",
            spot_trigger_reason_text="Manual trigger"
        )

        # Create 2 dummy templates
        self.template_1 = ExpectedChargeTemplate.objects.create(
            name="Template 1",
            mode="IMPORT",
            transport_mode="AIR",
            service_scope="A2D",
            origin_country="SG",
            destination_country="PG",
            is_active=True
        )
        self.template_2 = ExpectedChargeTemplate.objects.create(
            name="Template 2",
            mode="IMPORT",
            transport_mode="AIR",
            service_scope="A2D",
            origin_country="SG",
            destination_country="PG",
            is_active=True
        )

        self.metrics_url = reverse("quotes:spot-validation-maintenance-insights")

    def _create_snapshot(
        self,
        envelope,
        trigger="envelope_created",
        validation_status="warnings",
        template_id=None,
        template_hash="thash",
        findings_hash="fhash",
        finding_count=1,
        finding_codes=None,
        canonical_types=None,
        created_at=None
    ):
        snap = SpotTemplateValidationSnapshot.objects.create(
            envelope=envelope,
            trigger=trigger,
            validation_status=validation_status,
            template_id=template_id,
            template_hash=template_hash,
            findings_hash=findings_hash,
            findings_json=[],
            finding_count=finding_count,
            finding_codes=finding_codes or [],
            canonical_types=canonical_types or []
        )
        if created_at:
            SpotTemplateValidationSnapshot.objects.filter(id=snap.id).update(created_at=created_at)
        return snap

    def _create_event(
        self,
        envelope,
        event_type="finding_reviewed",
        finding_code="expected_charge_missing",
        canonical_type="AWB_DOCUMENTATION",
        fingerprint="fp1",
        created_at=None
    ):
        event = SpotTemplateValidationEvent.objects.create(
            envelope=envelope,
            event_type=event_type,
            finding_code=finding_code,
            canonical_type=canonical_type,
            template_line_id=123,
            charge_line_id=None,
            finding_fingerprint=fingerprint,
            validation_status=None,
            user=self.manager_user,
            metadata={"comment": "Comment text"}
        )
        if created_at:
            SpotTemplateValidationEvent.objects.filter(id=event.id).update(created_at=created_at)
        return event

    def test_manager_allowed_sales_blocked(self):
        """Verify only manager role is allowed and sales blocked."""
        self.client.force_authenticate(user=self.sales_user)
        response = self.client.get(self.metrics_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(user=self.manager_user)
        response = self.client.get(self.metrics_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_date_validation(self):
        """Verify invalid date formats, range limits and range inversions are rejected."""
        self.client.force_authenticate(user=self.manager_user)

        # Inverted date range
        response = self.client.get(f"{self.metrics_url}?start_date=2026-06-12&end_date=2026-06-01")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"], "end_date cannot be before start_date.")

        # Range > 180 days
        response = self.client.get(f"{self.metrics_url}?start_date=2026-01-01&end_date=2026-07-01")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"], "The maximum date range allowed is 180 days.")

        # Invalid format
        response = self.client.get(f"{self.metrics_url}?start_date=invalid-date")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_template_id_and_limit_filters(self):
        """Verify filtering by template_id and applying limits work correctly."""
        self.client.force_authenticate(user=self.manager_user)
        now = timezone.now()

        # Create snapshots for template 1 & 2 (using min_snapshots=1 to bypass sample size check)
        self._create_snapshot(self.envelope, template_id=self.template_1.id, template_hash="hash1", created_at=now - datetime.timedelta(days=2))
        self._create_snapshot(self.envelope, template_id=self.template_2.id, template_hash="hash2", findings_hash="fhash2", created_at=now - datetime.timedelta(days=2))

        # Filter by template_id
        response = self.client.get(f"{self.metrics_url}?template_id={self.template_1.id}&min_snapshots=1")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["insights"]), 1)
        self.assertEqual(response.data["insights"][0]["template_id"], self.template_1.id)

        # Test limit default and max
        response = self.client.get(f"{self.metrics_url}?limit=1&min_snapshots=1")
        self.assertEqual(len(response.data["insights"]), 1)

    def test_min_snapshots_default_and_custom(self):
        """Verify default min_snapshots=5 and custom value exclusions work."""
        self.client.force_authenticate(user=self.manager_user)
        now = timezone.now()

        # Create only 3 snapshots for template 1
        for i in range(3):
            self._create_snapshot(
                self.envelope,
                template_id=self.template_1.id,
                template_hash="h1",
                findings_hash=f"fh_{i}",
                created_at=now - datetime.timedelta(days=1)
            )

        # Default query (min_snapshots=5): template 1 should be excluded
        response = self.client.get(self.metrics_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["insights"]), 0)

        # Custom query (min_snapshots=2): template 1 should be included
        response = self.client.get(f"{self.metrics_url}?min_snapshots=2")
        self.assertEqual(len(response.data["insights"]), 1)
        self.assertTrue(response.data["insights"][0]["sample_warning"])  # < 5 snapshots warning should be true

    def test_score_and_metrics_calculation(self):
        """Verify priority score, ratios, breaks, and pressure signals calculation."""
        self.client.force_authenticate(user=self.manager_user)
        now = timezone.now()

        # Create 5 snapshots for template 1:
        # - 3 warnings, 2 passed (Issue ratio = 60%)
        # - Average findings = 12 findings total / 5 snapshots = 2.4 avg
        # - 3 warnings contain code "expected_charge_missing" (missing charge pressure should be True: 3/3 > 50%)
        # - 0 snapshots contain "unexpected_charge_present" (unexpected charge pressure should be False)
        # - 1 envelope with findings (envelope_1). We review it -> review rate = 100%, unreviewed ratio = 0%
        for i in range(3):
            self._create_snapshot(
                self.envelope,
                template_id=self.template_1.id,
                validation_status="warnings",
                finding_count=3,
                finding_codes=["expected_charge_missing"],
                canonical_types=["AWB"],
                findings_hash=f"hash_warn_{i}",
                created_at=now - datetime.timedelta(days=1)
            )
        for i in range(2):
            self._create_snapshot(
                self.envelope,
                template_id=self.template_1.id,
                validation_status="passed",
                finding_count=1, # Passed snapshots might have some low severity findings (like info), or let's keep it 1/0
                finding_codes=["expected_charge_missing"],
                findings_hash=f"hash_pass_{i}",
                created_at=now - datetime.timedelta(days=2)
            )

        # Create 1 review event to satisfy unreviewed ratio test
        self._create_event(
            self.envelope,
            finding_code="expected_charge_missing",
            created_at=now - datetime.timedelta(days=1)
        )

        response = self.client.get(f"{self.metrics_url}?min_snapshots=5")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        insights = response.data["insights"]
        self.assertEqual(len(insights), 1)

        t_insight = insights[0]
        self.assertEqual(t_insight["template_id"], self.template_1.id)
        self.assertEqual(t_insight["issue_ratio_percentage"], 60.0)
        self.assertEqual(t_insight["average_findings_per_snapshot"], 2.2)
        self.assertEqual(t_insight["review_rate_percentage"], 100.0)
        self.assertEqual(t_insight["unreviewed_ratio_percentage"], 0.0)

        # Score math: 
        # issue_ratio = 0.60 (weight 0.4 -> 24.0 points)
        # avg_findings = 2.2 / 5.0 = 0.44 (weight 0.3 -> 13.2 points)
        # unreviewed_ratio = 0.0 (weight 0.3 -> 0 points)
        # Expected Priority Score = 24.0 + 13.2 + 0.0 = 37.2
        self.assertEqual(t_insight["maintenance_priority_score"], 37.20)

        # Signals
        self.assertFalse(t_insight["maintenance_signals"]["high_maintenance_pressure"])
        self.assertTrue(t_insight["maintenance_signals"]["missing_charge_pressure"])
        self.assertFalse(t_insight["maintenance_signals"]["unexpected_charge_pressure"])

        # Ordered breakdowns
        self.assertEqual(t_insight["finding_codes_breakdown"][0]["code"], "expected_charge_missing")
        self.assertEqual(t_insight["finding_codes_breakdown"][0]["snapshot_count"], 5)
        self.assertEqual(t_insight["canonical_types_breakdown"][0]["canonical_type"], "AWB")
        self.assertEqual(t_insight["canonical_types_breakdown"][0]["snapshot_count"], 3)
