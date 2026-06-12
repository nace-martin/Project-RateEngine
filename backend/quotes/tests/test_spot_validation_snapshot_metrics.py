import datetime
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from quotes.spot_models import SpotPricingEnvelopeDB, SpotTemplateValidationSnapshot


class SpotTemplateValidationSnapshotMetricsTests(APITestCase):
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
            spot_trigger_reason_text="Manual trigger"
        )
        self.envelope_2 = SpotPricingEnvelopeDB.objects.create(
            status="draft",
            shipment_context_json={"origin_country": "AU", "destination_country": "NZ"},
            expires_at=timezone.now() + datetime.timedelta(days=2),
            spot_trigger_reason_code="MANUAL",
            spot_trigger_reason_text="Manual trigger"
        )

        self.metrics_url = reverse("quotes:spot-validation-snapshot-metrics")

    def _create_snapshot(
        self,
        envelope,
        trigger="envelope_created",
        validation_status="passed",
        template_id=None,
        template_hash="thash",
        findings_hash="fhash",
        findings_json=None,
        finding_count=0,
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

    def test_manager_allowed_sales_user_blocked(self):
        """Verify only manager/admin role can access snapshot metrics."""
        self.client.force_authenticate(user=self.sales_user)
        response = self.client.get(self.metrics_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(user=self.manager_user)
        response = self.client.get(self.metrics_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_default_30_day_date_range(self):
        """Verify snapshots are filtered by default to the last 30 days."""
        self.client.force_authenticate(user=self.manager_user)
        now = timezone.now()

        # In range (10 days ago)
        self._create_snapshot(self.envelope_1, created_at=now - datetime.timedelta(days=10), findings_hash="hash1")
        # Out of range (35 days ago)
        self._create_snapshot(self.envelope_2, created_at=now - datetime.timedelta(days=35), findings_hash="hash2")

        response = self.client.get(self.metrics_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["total_snapshots"], 1)

    def test_invalid_date_range_rejected(self):
        """Verify invalid date formats and inverted ranges return clear 400s."""
        self.client.force_authenticate(user=self.manager_user)

        # Inverted range
        response = self.client.get(f"{self.metrics_url}?start_date=2026-06-12&end_date=2026-06-01")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"], "end_date cannot be before start_date.")

        # Invalid format
        response = self.client.get(f"{self.metrics_url}?start_date=invalid-date")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_range_over_180_days_rejected(self):
        """Verify ranges exceeding 180 days return a 400."""
        self.client.force_authenticate(user=self.manager_user)
        response = self.client.get(f"{self.metrics_url}?start_date=2026-01-01&end_date=2026-07-01")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"], "The maximum date range allowed is 180 days.")

    def test_filters(self):
        """Verify trigger, status, template, finding_code, and canonical_type filters work."""
        self.client.force_authenticate(user=self.manager_user)
        now = timezone.now()

        # Created 3 distinct snapshots for testing filters
        self._create_snapshot(
            self.envelope_1,
            trigger="envelope_created",
            validation_status="passed",
            template_id=1,
            finding_codes=["code_A"],
            canonical_types=["c_A"],
            created_at=now - datetime.timedelta(days=2)
        )
        self._create_snapshot(
            self.envelope_1,
            trigger="envelope_updated",
            validation_status="warnings",
            template_id=2,
            finding_codes=["code_B"],
            canonical_types=["c_B"],
            created_at=now - datetime.timedelta(days=3)
        )

        # Filter by trigger
        response = self.client.get(f"{self.metrics_url}?trigger=envelope_updated")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["total_snapshots"], 1)
        self.assertEqual(response.data["filters_applied"]["trigger"], "envelope_updated")

        # Filter by validation_status
        response = self.client.get(f"{self.metrics_url}?validation_status=passed")
        self.assertEqual(response.data["total_snapshots"], 1)

        # Filter by template_id
        response = self.client.get(f"{self.metrics_url}?template_id=2")
        self.assertEqual(response.data["total_snapshots"], 1)

        # Filter by finding_code
        response = self.client.get(f"{self.metrics_url}?finding_code=code_A")
        self.assertEqual(response.data["total_snapshots"], 1)

        # Filter by canonical_type
        response = self.client.get(f"{self.metrics_url}?canonical_type=c_B")
        self.assertEqual(response.data["total_snapshots"], 1)

    def test_limit_query_param(self):
        """Verify limit query param default and max cap of 50."""
        self.client.force_authenticate(user=self.manager_user)
        now = timezone.now()

        # Create 15 distinct finding codes using separate snapshots
        for i in range(15):
            self._create_snapshot(
                self.envelope_1,
                finding_codes=[f"code_{i}"],
                findings_hash=f"hash_{i}",
                created_at=now - datetime.timedelta(days=1)
            )

        # Default limit is 10
        response = self.client.get(self.metrics_url)
        self.assertEqual(len(response.data["top_finding_codes"]), 10)

        # Specific limit 5
        response = self.client.get(f"{self.metrics_url}?limit=5")
        self.assertEqual(len(response.data["top_finding_codes"]), 5)

        # Max cap 50 (request 60, should cap at 15 since 15 exist)
        response = self.client.get(f"{self.metrics_url}?limit=60")
        self.assertEqual(len(response.data["top_finding_codes"]), 15)

    def test_metrics_calculations(self):
        """Verify total_snapshots, unique_envelopes_count, snapshots_without_template, and warning percentage."""
        self.client.force_authenticate(user=self.manager_user)
        now = timezone.now()

        # Snapshot 1: Envelope 1, warning, no template
        self._create_snapshot(
            self.envelope_1,
            validation_status="warnings",
            template_id=None,
            findings_hash="h1",
            created_at=now - datetime.timedelta(days=1)
        )
        # Snapshot 2: Envelope 1, review, template 1
        self._create_snapshot(
            self.envelope_1,
            validation_status="review",
            template_id=1,
            findings_hash="h2",
            created_at=now - datetime.timedelta(days=2)
        )
        # Snapshot 3: Envelope 2, passed, template 1
        self._create_snapshot(
            self.envelope_2,
            validation_status="passed",
            template_id=1,
            findings_hash="h3",
            created_at=now - datetime.timedelta(days=3)
        )

        response = self.client.get(self.metrics_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        self.assertEqual(response.data["total_snapshots"], 3)
        self.assertEqual(response.data["unique_envelopes_count"], 2)
        self.assertEqual(response.data["snapshots_without_template"], 1)
        self.assertEqual(response.data["review_or_warning_snapshot_count"], 2)
        self.assertEqual(response.data["review_or_warning_percentage"], 66.67)

    def test_templates_requiring_attention(self):
        """Verify templates_requiring_attention aggregation and sorting."""
        self.client.force_authenticate(user=self.manager_user)
        now = timezone.now()

        # Template 1: 2 warning snapshots
        self._create_snapshot(self.envelope_1, template_id=1, template_hash="hash1", validation_status="warnings", findings_hash="ha", created_at=now - datetime.timedelta(days=1))
        self._create_snapshot(self.envelope_1, template_id=1, template_hash="hash1", validation_status="warnings", findings_hash="hb", created_at=now - datetime.timedelta(days=2))

        # Template 2: 1 warning snapshot, 1 passed snapshot (50% issue rate)
        self._create_snapshot(self.envelope_1, template_id=2, template_hash="hash2", validation_status="warnings", findings_hash="hc", created_at=now - datetime.timedelta(days=3))
        self._create_snapshot(self.envelope_1, template_id=2, template_hash="hash2", validation_status="passed", findings_hash="hd", created_at=now - datetime.timedelta(days=4))

        response = self.client.get(self.metrics_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        req_attention = response.data["templates_requiring_attention"]
        self.assertEqual(len(req_attention), 2)
        
        # Sorted by issue percentage desc
        self.assertEqual(req_attention[0]["template_id"], 1)
        self.assertEqual(req_attention[0]["review_or_warning_percentage"], 100.0)
        self.assertEqual(req_attention[1]["template_id"], 2)
        self.assertEqual(req_attention[1]["review_or_warning_percentage"], 50.0)

    def test_stability_metrics(self):
        """Verify stability metrics are computed correctly based on distinct findings_hash per envelope."""
        self.client.force_authenticate(user=self.manager_user)
        now = timezone.now()

        # Envelope 1: Unstable (2 different findings_hash values)
        self._create_snapshot(self.envelope_1, findings_hash="hashA", template_hash="thash", created_at=now - datetime.timedelta(days=1))
        self._create_snapshot(self.envelope_1, findings_hash="hashB", template_hash="thash", created_at=now - datetime.timedelta(days=2))

        # Envelope 2: Stable (1 findings_hash value across multiple snapshots due to template change)
        self._create_snapshot(self.envelope_2, findings_hash="hashC", template_hash="thash1", created_at=now - datetime.timedelta(days=3))
        self._create_snapshot(self.envelope_2, findings_hash="hashC", template_hash="thash2", created_at=now - datetime.timedelta(days=4))


        response = self.client.get(self.metrics_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        stability = response.data["stability_metrics"]
        self.assertEqual(stability["total_envelopes"], 2)
        self.assertEqual(stability["stable_envelopes_count"], 1)
        self.assertEqual(stability["unstable_envelopes_count"], 1)
