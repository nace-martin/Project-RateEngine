import datetime
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from quotes.spot_models import SpotPricingEnvelopeDB, SpotTemplateValidationEvent


class SpotTemplateValidationReviewMetricsTests(APITestCase):
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
            spot_trigger_reason_text="Manual trigger",
            created_by=self.manager_user
        )

        self.metrics_url = reverse("quotes:spot-validation-review-metrics")

    def _create_event(self, created_at, event_type="finding_reviewed", finding_code="expected_charge_missing", canonical_type="AWB_DOCUMENTATION", fingerprint="fp1"):
        event = SpotTemplateValidationEvent.objects.create(
            envelope=self.envelope,
            event_type=event_type,
            finding_code=finding_code,
            canonical_type=canonical_type,
            template_line_id=123,
            charge_line_id=None,
            finding_fingerprint=fingerprint,
            validation_status=None,
            user=self.manager_user,
            metadata={"comment": "Event comment"}
        )
        if created_at:
            # Override auto_now_add
            SpotTemplateValidationEvent.objects.filter(id=event.id).update(created_at=created_at)
        return event

    def test_manager_allowed_sales_user_blocked(self):
        """Verify only manager/admin role can access validation metrics."""
        # Authenticate sales user
        self.client.force_authenticate(user=self.sales_user)
        response = self.client.get(self.metrics_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # Authenticate manager
        self.client.force_authenticate(user=self.manager_user)
        response = self.client.get(self.metrics_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_metrics_filtering_and_counts(self):
        """Verify metrics count only finding_reviewed events and group correctly."""
        self.client.force_authenticate(user=self.manager_user)
        now = timezone.now()

        # 1. Create finding_reviewed event (within 30 days)
        self._create_event(created_at=now - datetime.timedelta(days=2), finding_code="expected_charge_missing", canonical_type="AWB")
        
        # 2. Create another finding_reviewed event (within 30 days, different code)
        self._create_event(created_at=now - datetime.timedelta(days=5), finding_code="unexpected_charge_present", canonical_type="AWB")
        
        # 3. Create another event with same code to test count aggregates
        self._create_event(created_at=now - datetime.timedelta(days=10), finding_code="expected_charge_missing", canonical_type="FUEL")

        # 4. Create non-reviewed event (should not be counted)
        self._create_event(created_at=now - datetime.timedelta(days=1), event_type="finding_generated")

        # 5. Create event outside default 30-day filter (35 days ago)
        self._create_event(created_at=now - datetime.timedelta(days=35), finding_code="expected_charge_missing")

        # Run with default 30 day filter
        response = self.client.get(self.metrics_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.data
        self.assertEqual(data["total_reviewed_events"], 3)  # Only the 3 reviews within 30 days
        self.assertEqual(data["reviewed_by_finding_code"]["expected_charge_missing"], 2)
        self.assertEqual(data["reviewed_by_finding_code"]["unexpected_charge_present"], 1)
        self.assertEqual(data["reviewed_by_canonical_type"]["AWB"], 2)
        self.assertEqual(data["reviewed_by_canonical_type"]["FUEL"], 1)
        self.assertEqual(data["reviewed_by_user"]["manager_test"], 3)

        # Shape assertions
        self.assertEqual(len(data["latest_events"]), 3)
        self.assertEqual(data["latest_events"][0]["user"], "manager_test")
        self.assertEqual(data["latest_events"][0]["comment"], "Event comment")
        self.assertEqual(len(data["top_reviewed_fingerprints"]), 3)

    def test_explicit_date_filtering(self):
        """Verify query parameters start_date and end_date filter metrics properly."""
        self.client.force_authenticate(user=self.manager_user)
        now = timezone.now()

        # Event 1: 45 days ago
        self._create_event(created_at=now - datetime.timedelta(days=45), finding_code="code_A")
        # Event 2: 15 days ago
        self._create_event(created_at=now - datetime.timedelta(days=15), finding_code="code_B")

        # Query range from 50 days ago to 30 days ago
        start = (now - datetime.timedelta(days=50)).date().isoformat()
        end = (now - datetime.timedelta(days=30)).date().isoformat()

        response = self.client.get(f"{self.metrics_url}?start_date={start}&end_date={end}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["total_reviewed_events"], 1)
        self.assertIn("code_A", response.data["reviewed_by_finding_code"])
        self.assertNotIn("code_B", response.data["reviewed_by_finding_code"])

    def test_rejects_range_over_180_days(self):
        """Verify range checks reject queries spanning more than 180 days."""
        self.client.force_authenticate(user=self.manager_user)
        now = timezone.now()

        start = (now - datetime.timedelta(days=190)).date().isoformat()
        end = now.date().isoformat()

        response = self.client.get(f"{self.metrics_url}?start_date={start}&end_date={end}")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"], "The maximum date range allowed is 180 days.")

    def test_rejects_end_date_before_start_date(self):
        """Verify rejecting start date that exceeds end date."""
        self.client.force_authenticate(user=self.manager_user)
        now = timezone.now()

        start = now.date().isoformat()
        end = (now - datetime.timedelta(days=10)).date().isoformat()

        response = self.client.get(f"{self.metrics_url}?start_date={start}&end_date={end}")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"], "end_date cannot be before start_date.")

    def test_departmental_rbac_isolation(self):
        """Verify that a manager can only see review metrics for envelopes in their department."""
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
        
        SpotTemplateValidationEvent.objects.create(
            envelope=envelope_air,
            event_type="finding_reviewed",
            finding_code="expected_charge_missing",
            finding_fingerprint="fp_air",
            user=sales_air
        )
        SpotTemplateValidationEvent.objects.create(
            envelope=envelope_ocean,
            event_type="finding_reviewed",
            finding_code="unexpected_charge_present",
            finding_fingerprint="fp_ocean",
            user=sales_ocean
        )
        
        self.client.force_authenticate(user=manager_air)
        response = self.client.get(self.metrics_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["total_reviewed_events"], 1)
        self.assertIn("expected_charge_missing", response.data["reviewed_by_finding_code"])
        self.assertNotIn("unexpected_charge_present", response.data["reviewed_by_finding_code"])
        
        self.client.force_authenticate(user=manager_ocean)
        response = self.client.get(self.metrics_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["total_reviewed_events"], 1)
        self.assertIn("unexpected_charge_present", response.data["reviewed_by_finding_code"])
        self.assertNotIn("expected_charge_missing", response.data["reviewed_by_finding_code"])

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

