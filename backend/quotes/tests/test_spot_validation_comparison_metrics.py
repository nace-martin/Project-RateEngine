import datetime
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from quotes.spot_models import (
    SpotPricingEnvelopeDB,
    SpotTemplateValidationSnapshot,
    SpotTemplateValidationEvent
)


class SpotTemplateValidationComparisonMetricsTests(APITestCase):
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

        self.envelope_1 = SpotPricingEnvelopeDB.objects.create(
            status="draft",
            shipment_context_json={"origin_country": "SG", "destination_country": "PG"},
            expires_at=timezone.now() + datetime.timedelta(days=2),
            spot_trigger_reason_code="MANUAL",
            spot_trigger_reason_text="Manual trigger",
            created_by=self.manager_user
        )
        self.envelope_2 = SpotPricingEnvelopeDB.objects.create(
            status="draft",
            shipment_context_json={"origin_country": "AU", "destination_country": "NZ"},
            expires_at=timezone.now() + datetime.timedelta(days=2),
            spot_trigger_reason_code="MANUAL",
            spot_trigger_reason_text="Manual trigger",
            created_by=self.manager_user
        )

        self.metrics_url = reverse("quotes:spot-validation-comparison-metrics")

    def _create_snapshot(
        self,
        envelope,
        trigger="envelope_created",
        validation_status="warnings",
        template_id=None,
        template_hash="thash",
        findings_hash="fhash",
        findings_json=None,
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
            findings_json=findings_json or [],
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
        """Verify sales role is blocked and manager/admin role is allowed."""
        self.client.force_authenticate(user=self.sales_user)
        response = self.client.get(self.metrics_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(user=self.manager_user)
        response = self.client.get(self.metrics_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_default_30_day_date_range(self):
        """Verify comparison counts filter records within default 30 days range."""
        self.client.force_authenticate(user=self.manager_user)
        now = timezone.now()

        # In range snapshot and event
        self._create_snapshot(
            self.envelope_1,
            finding_codes=["expected_charge_missing"],
            created_at=now - datetime.timedelta(days=10)
        )
        self._create_event(
            self.envelope_1,
            finding_code="expected_charge_missing",
            created_at=now - datetime.timedelta(days=10)
        )

        # Out of range snapshot and event (35 days ago)
        self._create_snapshot(
            self.envelope_2,
            finding_codes=["expected_charge_missing"],
            findings_hash="fhash_out",
            created_at=now - datetime.timedelta(days=35)
        )
        self._create_event(
            self.envelope_2,
            finding_code="expected_charge_missing",
            created_at=now - datetime.timedelta(days=35)
        )

        response = self.client.get(self.metrics_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Summary counts
        self.assertEqual(response.data["summary"]["total_envelopes_with_snapshots"], 1)
        self.assertEqual(response.data["summary"]["total_envelopes_with_reviews"], 1)
        self.assertEqual(response.data["summary"]["global_review_rate_percentage"], 100.0)

    def test_invalid_date_range_rejected(self):
        """Verify invalid formats and range inversions return 400."""
        self.client.force_authenticate(user=self.manager_user)

        # Inverted range
        response = self.client.get(f"{self.metrics_url}?start_date=2026-06-12&end_date=2026-06-01")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"], "end_date cannot be before start_date.")

        # Invalid format
        response = self.client.get(f"{self.metrics_url}?start_date=invalid-date")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_range_over_180_days_rejected(self):
        """Verify range exceeds limits check returns 400."""
        self.client.force_authenticate(user=self.manager_user)
        response = self.client.get(f"{self.metrics_url}?start_date=2026-01-01&end_date=2026-07-01")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"], "The maximum date range allowed is 180 days.")

    def test_filters(self):
        """Verify template_id, finding_code, canonical_type, and limit filters work."""
        self.client.force_authenticate(user=self.manager_user)
        now = timezone.now()

        # Envelope 1: template 1, code_A, cct_A
        self._create_snapshot(
            self.envelope_1,
            template_id=1,
            finding_codes=["code_A"],
            canonical_types=["cct_A"],
            created_at=now - datetime.timedelta(days=2)
        )
        self._create_event(
            self.envelope_1,
            finding_code="code_A",
            canonical_type="cct_A",
            created_at=now - datetime.timedelta(days=2)
        )

        # Envelope 2: template 2, code_B, cct_B
        self._create_snapshot(
            self.envelope_2,
            template_id=2,
            finding_codes=["code_B"],
            findings_hash="fhash_env2",
            canonical_types=["cct_B"],
            created_at=now - datetime.timedelta(days=2)
        )

        # Filter template_id=1
        response = self.client.get(f"{self.metrics_url}?template_id=1")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["summary"]["total_envelopes_with_snapshots"], 1)

        # Filter finding_code=code_B
        response = self.client.get(f"{self.metrics_url}?finding_code=code_B")
        self.assertEqual(response.data["summary"]["total_envelopes_with_snapshots"], 1)

        # Filter canonical_type=cct_A
        response = self.client.get(f"{self.metrics_url}?canonical_type=cct_A")
        self.assertEqual(response.data["summary"]["total_envelopes_with_snapshots"], 1)

        # Test limit filter
        # Create many comparison items
        for i in range(15):
            env = SpotPricingEnvelopeDB.objects.create(
                status="draft",
                shipment_context_json={"origin_country": "SG", "destination_country": "PG"},
                expires_at=timezone.now() + datetime.timedelta(days=2),
                spot_trigger_reason_code="MANUAL",
                spot_trigger_reason_text="Manual trigger",
                created_by=self.manager_user
            )
            self._create_snapshot(
                env,
                finding_codes=[f"code_{i}"],
                findings_hash=f"hash_{i}",
                created_at=now - datetime.timedelta(days=1)
            )

        response = self.client.get(f"{self.metrics_url}?limit=5")
        self.assertEqual(len(response.data["finding_code_comparison"]), 5)

    def test_aggregation_and_deduplication(self):
        """Verify envelope deduplication and accurate rate math calculation."""
        self.client.force_authenticate(user=self.manager_user)
        now = timezone.now()

        # Envelope 1 has multiple snapshots but identical finding code (deduplication check!)
        self._create_snapshot(
            self.envelope_1,
            template_id=1,
            finding_codes=["expected_charge_missing"],
            canonical_types=["AWB"],
            findings_hash="h1",
            created_at=now - datetime.timedelta(days=1)
        )
        self._create_snapshot(
            self.envelope_1,
            template_id=1,
            finding_codes=["expected_charge_missing"],
            canonical_types=["AWB"],
            findings_hash="h2", # Different findings_hash to bypass DB unique check
            template_hash="thash_diff",
            created_at=now - datetime.timedelta(days=2)
        )

        # Envelope 1 reviewed
        self._create_event(
            self.envelope_1,
            finding_code="expected_charge_missing",
            canonical_type="AWB",
            created_at=now - datetime.timedelta(days=1)
        )

        # Envelope 2 has snapshot with same finding but not reviewed
        self._create_snapshot(
            self.envelope_2,
            template_id=1,
            finding_codes=["expected_charge_missing"],
            canonical_types=["AWB"],
            findings_hash="h3",
            created_at=now - datetime.timedelta(days=3)
        )

        response = self.client.get(self.metrics_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Total unique envelopes should be 2, not 3 (even though envelope 1 had 2 snapshots)
        self.assertEqual(response.data["summary"]["total_envelopes_with_snapshots"], 2)
        self.assertEqual(response.data["summary"]["total_envelopes_with_reviews"], 1)
        self.assertEqual(response.data["summary"]["global_review_rate_percentage"], 50.0)

        # Finding code comparison
        finding_comp = response.data["finding_code_comparison"]
        self.assertEqual(len(finding_comp), 1)
        self.assertEqual(finding_comp[0]["finding_code"], "expected_charge_missing")
        self.assertEqual(finding_comp[0]["envelopes_generated_count"], 2)
        self.assertEqual(finding_comp[0]["envelopes_reviewed_count"], 1)
        self.assertEqual(finding_comp[0]["review_rate_percentage"], 50.0)

        # Canonical type comparison
        cct_comp = response.data["canonical_type_comparison"]
        self.assertEqual(len(cct_comp), 1)
        self.assertEqual(cct_comp[0]["canonical_type"], "AWB")
        self.assertEqual(cct_comp[0]["envelopes_generated_count"], 2)
        self.assertEqual(cct_comp[0]["envelopes_reviewed_count"], 1)
        self.assertEqual(cct_comp[0]["review_rate_percentage"], 50.0)

    def test_departmental_rbac_isolation(self):
        """Verify that a manager can only see comparison metrics for envelopes in their department."""
        User = get_user_model()
        
        manager_air = User.objects.create_user(
            username="manager_air",
            password="password123",
            email="manager_air@example.com",
            role="manager",
            department="Air"
        )
        manager_ocean = User.objects.create_user(
            username="manager_ocean",
            password="password123",
            email="manager_ocean@example.com",
            role="manager",
            department="Ocean"
        )
        
        sales_air = User.objects.create_user(
            username="sales_air",
            password="password123",
            email="sales_air@example.com",
            role="sales",
            department="Air"
        )
        sales_ocean = User.objects.create_user(
            username="sales_ocean",
            password="password123",
            email="sales_ocean@example.com",
            role="sales",
            department="Ocean"
        )
        
        envelope_air = SpotPricingEnvelopeDB.objects.create(
            status="draft",
            shipment_context_json={"origin_country": "SG", "destination_country": "PG"},
            expires_at=timezone.now() + datetime.timedelta(days=2),
            spot_trigger_reason_code="MANUAL",
            spot_trigger_reason_text="Manual trigger",
            created_by=sales_air
        )
        envelope_ocean = SpotPricingEnvelopeDB.objects.create(
            status="draft",
            shipment_context_json={"origin_country": "SG", "destination_country": "PG"},
            expires_at=timezone.now() + datetime.timedelta(days=2),
            spot_trigger_reason_code="MANUAL",
            spot_trigger_reason_text="Manual trigger",
            created_by=sales_ocean
        )
        
        self._create_snapshot(envelope_air, finding_codes=["expected_charge_missing"], canonical_types=["AWB"], findings_hash="fp_air")
        self._create_event(envelope_air, finding_code="expected_charge_missing", canonical_type="AWB")
        
        self._create_snapshot(envelope_ocean, finding_codes=["unexpected_charge_present"], canonical_types=["FUEL"], findings_hash="fp_ocean")
        self._create_event(envelope_ocean, finding_code="unexpected_charge_present", canonical_type="FUEL")
        
        self.client.force_authenticate(user=manager_air)
        response = self.client.get(self.metrics_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["summary"]["total_envelopes_with_snapshots"], 1)
        self.assertEqual(len(response.data["finding_code_comparison"]), 1)
        self.assertEqual(response.data["finding_code_comparison"][0]["finding_code"], "expected_charge_missing")
        
        self.client.force_authenticate(user=manager_ocean)
        response = self.client.get(self.metrics_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["summary"]["total_envelopes_with_snapshots"], 1)
        self.assertEqual(len(response.data["finding_code_comparison"]), 1)
        self.assertEqual(response.data["finding_code_comparison"][0]["finding_code"], "unexpected_charge_present")

    def test_disabled_flag_returns_503(self):
        """Verify the endpoint returns HTTP 503 if the operational toggle is disabled."""
        from django.test import override_settings
        self.client.force_authenticate(user=self.manager_user)
        with override_settings(SPOT_VALIDATION_METRICS_ENABLED=False):
            response = self.client.get(self.metrics_url)
            self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
            self.assertEqual(response.data, {"detail": "SPOT validation metrics are temporarily disabled."})

    def test_invalid_limit(self):
        """Verify invalid limit values are rejected with 400."""
        self.client.force_authenticate(user=self.manager_user)
        response = self.client.get(f"{self.metrics_url}?limit=-5")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"], "limit must be a positive integer.")

