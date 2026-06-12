import json
import hashlib
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from pricing_v4.models import CanonicalChargeType, ProductCode, ChargeAlias
from quotes.spot_models import (
    SpotPricingEnvelopeDB,
    ExpectedChargeTemplate,
    ExpectedTemplateLine,
    SpotTemplateValidationSnapshot,
    TRIGGER_ENVELOPE_CREATED,
    TRIGGER_ENVELOPE_UPDATED,
    TRIGGER_SALES_ACKNOWLEDGED,
)


@override_settings(
    REST_FRAMEWORK={
        "DEFAULT_PERMISSION_CLASSES": [
            "rest_framework.permissions.IsAuthenticated",
        ],
        "DEFAULT_AUTHENTICATION_CLASSES": [
            "rest_framework.authentication.TokenAuthentication",
        ],
        "DEFAULT_THROTTLE_CLASSES": [],
    }
)
class SpotTemplateValidationSnapshotTest(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="snapuser",
            password="pass123",
            email="snapuser@example.com",
            role="sales"
        )
        self.client.force_authenticate(user=self.user)

        self.cct, _ = CanonicalChargeType.objects.get_or_create(
            code="AWB_DOCUMENTATION",
            defaults={"name": "AWB Documentation", "category": "DOCS"}
        )

        product = ProductCode.objects.create(
            id=10101,
            code="AWB_DOCUMENTATION",
            description="AWB Doc Fee",
            domain="AIR",
            category="HANDLING",
            default_unit="SHIPMENT",
            is_gst_applicable=False,
        )
        ChargeAlias.objects.create(
            alias_text="AWB Doc Fee",
            normalized_alias_text=ChargeAlias.normalize_alias_text_value("AWB Doc Fee"),
            match_type=ChargeAlias.MatchType.EXACT,
            mode_scope=ChargeAlias.ModeScope.IMPORT,
            direction_scope=ChargeAlias.DirectionScope.ANY,
            product_code=product,
            canonical_charge_type=self.cct,
            priority=10,
            alias_source=ChargeAlias.AliasSource.ADMIN,
            review_status=ChargeAlias.ReviewStatus.APPROVED,
        )

        self.template = ExpectedChargeTemplate.objects.create(
            name="SG-PG Air Import Template",
            mode="IMPORT",
            transport_mode="AIR",
            service_scope="A2D",
            origin_country="SG",
            destination_country="PG",
            is_active=True
        )

        self.template_line = ExpectedTemplateLine.objects.create(
            template=self.template,
            canonical_charge_type=self.cct,
            requirement_level=ExpectedTemplateLine.RequirementLevel.REQUIRED,
            expected_basis="any"
        )

        self.shipment_context = {
            "origin_country": "SG",
            "destination_country": "PG",
            "transport_mode": "AIR",
            "service_scope": "A2D",
            "origin_code": "SIN",
            "destination_code": "POM",
            "commodity": "GCR",
            "total_weight_kg": 100,
            "pieces": 2,
        }

    def test_snapshot_lifecycle(self):
        # 1. Snapshot created on envelope creation
        create_url = reverse("quotes:spot-envelope-list-create")
        create_payload = {
            "shipment_context": self.shipment_context,
            "charges": [
                {
                    "code": "AWB_DOCUMENTATION",
                    "description": "AWB Doc Fee",
                    "amount": 50,
                    "currency": "USD",
                    "unit": "flat",
                    "bucket": "origin_charges",
                    "is_primary_cost": True,
                    "conditional": False,
                    "source_reference": "Email Quote",
                }
            ],
            "trigger_code": "MISSING_SCOPE_RATES",
            "trigger_text": "Need spot approval for rates",
        }

        # Before POST, verify no snapshots exist
        self.assertEqual(SpotTemplateValidationSnapshot.objects.count(), 0)

        response = self.client.post(create_url, create_payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        spe_id = response.json()["id"]

        # Verify a snapshot was created with TRIGGER_ENVELOPE_CREATED
        self.assertEqual(SpotTemplateValidationSnapshot.objects.count(), 1)
        snap1 = SpotTemplateValidationSnapshot.objects.get()
        self.assertEqual(snap1.trigger, TRIGGER_ENVELOPE_CREATED)
        self.assertEqual(snap1.template_id, self.template.id)
        self.assertTrue(len(snap1.template_hash) > 0)
        self.assertTrue(len(snap1.findings_hash) > 0)
        self.assertEqual(snap1.finding_count, 0)  # We satisfied the required AWB_DOCUMENTATION

        # Save hashes to verify deduplication
        first_template_hash = snap1.template_hash
        first_findings_hash = snap1.findings_hash

        # 2. GET/detail does not trigger validation snapshot writes
        detail_url = reverse("quotes:spot-envelope-detail", kwargs={"envelope_id": spe_id})
        detail_resp = self.client.get(detail_url)
        self.assertEqual(detail_resp.status_code, status.HTTP_200_OK)
        # Snapshots count should remain 1
        self.assertEqual(SpotTemplateValidationSnapshot.objects.count(), 1)

        # 3. Duplicate snapshot not created for identical validation state during update
        patch_payload = {
            "charges": [
                {
                    "code": "AWB_DOCUMENTATION",
                    "description": "AWB Doc Fee",
                    "amount": 50,
                    "currency": "USD",
                    "unit": "flat",
                    "bucket": "origin_charges",
                    "is_primary_cost": True,
                    "conditional": False,
                    "source_reference": "Email Quote",
                }
            ]
        }
        patch_resp = self.client.patch(detail_url, patch_payload, format="json")
        self.assertEqual(patch_resp.status_code, status.HTTP_200_OK)
        # Still 1 snapshot (deduplicated!)
        self.assertEqual(SpotTemplateValidationSnapshot.objects.count(), 1)

        # 4. Changed charges create new snapshot
        # Remove AWB_DOCUMENTATION, which should trigger a validation warning/missing charge finding
        patch_payload_empty = {
            "charges": []
        }
        patch_resp_empty = self.client.patch(detail_url, patch_payload_empty, format="json")
        self.assertEqual(patch_resp_empty.status_code, status.HTTP_200_OK)
        # A new snapshot should be generated with different findings_hash and TRIGGER_ENVELOPE_UPDATED
        self.assertEqual(SpotTemplateValidationSnapshot.objects.count(), 2)
        snap2 = SpotTemplateValidationSnapshot.objects.order_by("-created_at").first()
        self.assertEqual(snap2.trigger, TRIGGER_ENVELOPE_UPDATED)
        self.assertEqual(snap2.template_id, self.template.id)
        self.assertEqual(snap2.template_hash, first_template_hash) # Template hasn't changed
        self.assertNotEqual(snap2.findings_hash, first_findings_hash) # Findings changed (AWB_DOCUMENTATION missing now)
        self.assertEqual(snap2.finding_count, 1)
        self.assertIn("expected_charge_missing", snap2.finding_codes)

        # 5. Acknowledgment captures/dedupes correctly
        # Re-adding charges to make it identical to first validation state, then acknowledge
        patch_resp_restore = self.client.patch(detail_url, patch_payload, format="json")
        self.assertEqual(patch_resp_restore.status_code, status.HTTP_200_OK)
        # Should NOT write a new snapshot on PATCH since we restored same state as snap1
        self.assertEqual(SpotTemplateValidationSnapshot.objects.count(), 2)

        # Now call acknowledge
        ack_url = reverse("quotes:spot-envelope-acknowledge", kwargs={"envelope_id": spe_id})
        ack_resp = self.client.post(ack_url, format="json")
        self.assertEqual(ack_resp.status_code, status.HTTP_200_OK)
        
        # Acknowledging should write a new snapshot because the trigger is TRIGGER_SALES_ACKNOWLEDGED,
        # and trigger is NOT in the uniqueness constraint fields!
        # Uniqueness is on (envelope, status, template_hash, findings_hash).
        # Since this is a new validation state combination? Wait!
        # If the validation_status, template_hash, findings_hash are identical to snap1,
        # the UniqueConstraint (envelope, validation_status, template_hash, findings_hash) WILL trigger.
        # So it should be DEDUPLICATED and NOT insert a new snapshot row to avoid spam.
        # Let's verify that the row was deduplicated correctly!
        self.assertEqual(SpotTemplateValidationSnapshot.objects.count(), 2)

        # Let's verify if we change validation state again, then acknowledge:
        # 1. Update to empty charges (generates warning snapshot)
        self.client.patch(detail_url, patch_payload_empty, format="json")
        self.assertEqual(SpotTemplateValidationSnapshot.objects.count(), 2) # already exists for status/hashes
        
        # 6. Snapshot survives later template changes because findings_json/template_hash preserve historical state
        # Let's read snap2 findings_json
        saved_findings = snap2.findings_json
        saved_template_hash = snap2.template_hash

        # Delete template lines or modify template
        self.template_line.delete()
        self.template.is_active = False
        self.template.save()

        # Refresh snap2 from DB and ensure it is untouched
        snap2.refresh_from_db()
        self.assertEqual(snap2.template_hash, saved_template_hash)
        self.assertEqual(snap2.findings_json, saved_findings)
