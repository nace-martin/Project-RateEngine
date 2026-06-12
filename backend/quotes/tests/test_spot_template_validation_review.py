from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
from rest_framework import status
from rest_framework.test import APITestCase

from pricing_v4.models import CanonicalChargeType
from quotes.spot_models import (
    SpotPricingEnvelopeDB,
    ExpectedChargeTemplate,
    ExpectedTemplateLine,
    SpotTemplateValidationReview
)
from quotes.services.spot_template_validation import validate_envelope_charges


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
class SpotTemplateValidationReviewAPITest(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="spotflow",
            password="pass123",
            email="spotflow@example.com",
            role="sales"  # sales role is default for standard view
        )
        self.client.force_authenticate(user=self.user)

        self.other_user = User.objects.create_user(
            username="otheruser",
            password="pass123",
            email="other@example.com",
            role="sales"
        )

        # Create standard PNG shipment context
        self.shipment_context = {
            "origin_country": "SG",
            "destination_country": "PG",
            "transport_mode": "AIR",
            "service_scope": "A2D",
            "origin_code": "SIN",
            "destination_code": "POM"
        }

        # Create envelope created by self.user
        self.envelope = SpotPricingEnvelopeDB.objects.create(
            status="draft",
            shipment_context_json=self.shipment_context,
            expires_at=timezone.now() + timedelta(days=2),
            spot_trigger_reason_code="MANUAL",
            spot_trigger_reason_text="Manual trigger",
            created_by=self.user
        )

        # Retrieve or create canonical charge type
        self.cct, _ = CanonicalChargeType.objects.get_or_create(
            code="AWB_DOCUMENTATION",
            defaults={"name": "AWB Documentation", "category": "DOCS"}
        )

        # Create ExpectedChargeTemplate
        self.template = ExpectedChargeTemplate.objects.create(
            name="SG-PG Air Import Template",
            mode="IMPORT",
            transport_mode="AIR",
            service_scope="A2D",
            origin_country="SG",
            destination_country="PG",
            is_active=True
        )

        # Create ExpectedTemplateLine
        self.template_line = ExpectedTemplateLine.objects.create(
            template=self.template,
            canonical_charge_type=self.cct,
            requirement_level=ExpectedTemplateLine.RequirementLevel.REQUIRED,
            expected_basis="any"
        )

        self.review_url = reverse(
            "quotes:spot-envelope-finding-reviewed",
            kwargs={"envelope_id": self.envelope.id}
        )

    def test_create_validation_review_successfully(self):
        """Verify the endpoint successfully registers a reviewed finding."""
        payload = {
            "finding_code": "expected_charge_missing",
            "canonical_type": "AWB_DOCUMENTATION",
            "template_line_id": self.template_line.id,
            "charge_line_id": None,
            "comment": "Reviewed with rate owner"
        }

        response = self.client.post(self.review_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("id", response.data)
        self.assertEqual(response.data["finding_code"], "expected_charge_missing")
        self.assertEqual(response.data["canonical_type"], "AWB_DOCUMENTATION")
        self.assertEqual(response.data["template_line_id"], self.template_line.id)
        self.assertEqual(response.data["comment"], "Reviewed with rate owner")
        self.assertEqual(response.data["reviewed_by"], self.user.id)

        # Check DB
        reviews = SpotTemplateValidationReview.objects.filter(envelope=self.envelope)
        self.assertEqual(reviews.count(), 1)
        review = reviews.first()
        self.assertEqual(review.finding_code, "expected_charge_missing")
        self.assertEqual(review.comment, "Reviewed with rate owner")
        self.assertEqual(review.reviewed_by, self.user)

    def test_duplicate_post_is_idempotent_or_safely_updates_comment(self):
        """Verify submitting a duplicate review updates the comment and doesn't duplicate."""
        payload = {
            "finding_code": "expected_charge_missing",
            "canonical_type": "AWB_DOCUMENTATION",
            "template_line_id": self.template_line.id,
            "charge_line_id": None,
            "comment": "Initial comment"
        }

        response = self.client.post(self.review_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Send duplicate POST with updated comment
        payload["comment"] = "Updated comment"
        response2 = self.client.post(self.review_url, payload, format="json")
        self.assertEqual(response2.status_code, status.HTTP_201_CREATED)

        # Check DB count remains 1
        reviews = SpotTemplateValidationReview.objects.filter(envelope=self.envelope)
        self.assertEqual(reviews.count(), 1)
        review = reviews.first()
        self.assertEqual(review.comment, "Updated comment")
        self.assertEqual(review.reviewed_by, self.user)

    def test_unauthorized_out_of_scope_envelope_is_rejected(self):
        """Verify users without access to the envelope are rejected with 404."""
        self.client.force_authenticate(user=self.other_user)
        payload = {
            "finding_code": "expected_charge_missing",
            "canonical_type": "AWB_DOCUMENTATION",
            "template_line_id": self.template_line.id,
            "charge_line_id": None,
            "comment": "Hacker attempt"
        }

        response = self.client.post(self.review_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_validate_envelope_charges_annotates_matching_findings_and_status_immutable(self):
        """Verify matching findings are annotated and envelope status remains unchanged."""
        # 1. Run validation before review
        res1 = validate_envelope_charges(self.envelope)
        self.assertEqual(res1["status"], "warnings")  # expected_charge_missing is severity warning
        finding = res1["findings"][0]
        self.assertEqual(finding["is_reviewed"], False)
        self.assertIsNone(finding["review"])

        # 2. Add a review record
        payload = {
            "finding_code": "expected_charge_missing",
            "canonical_type": "AWB_DOCUMENTATION",
            "template_line_id": self.template_line.id,
            "charge_line_id": None,
            "comment": "Reviewed and approved"
        }
        response = self.client.post(self.review_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # 3. Run validation again after review
        res2 = validate_envelope_charges(self.envelope)
        # Validation status MUST NOT change (remains warnings)
        self.assertEqual(res2["status"], "warnings")
        finding_after = res2["findings"][0]
        self.assertEqual(finding_after["is_reviewed"], True)
        self.assertIsNotNone(finding_after["review"])
        self.assertEqual(finding_after["review"]["comment"], "Reviewed and approved")
        self.assertEqual(finding_after["review"]["reviewed_by"], self.user.username)

    def test_invalid_finding_code_rejected(self):
        """Verify that validation review endpoint rejects invalid/unknown finding codes."""
        payload = {
            "finding_code": "invalid_finding_code_foo",
            "canonical_type": "AWB_DOCUMENTATION",
            "template_line_id": self.template_line.id,
            "charge_line_id": None,
            "comment": "Nice try"
        }
        response = self.client.post(self.review_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("finding_code", response.data)

    def test_long_comment_rejected(self):
        """Verify that validation review endpoint rejects comments over 2000 characters."""
        payload = {
            "finding_code": "expected_charge_missing",
            "canonical_type": "AWB_DOCUMENTATION",
            "template_line_id": self.template_line.id,
            "charge_line_id": None,
            "comment": "x" * 2001
        }
        response = self.client.post(self.review_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("comment", response.data)

    def test_whitespace_comment_stripped(self):
        """Verify that validation review endpoint strips leading/trailing comment whitespace."""
        payload = {
            "finding_code": "expected_charge_missing",
            "canonical_type": "AWB_DOCUMENTATION",
            "template_line_id": self.template_line.id,
            "charge_line_id": None,
            "comment": "   Hello world!  \n "
        }
        response = self.client.post(self.review_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["comment"], "Hello world!")

        review = SpotTemplateValidationReview.objects.get(id=response.data["id"])
        self.assertEqual(review.comment, "Hello world!")

    def test_fingerprint_remains_stable(self):
        """Verify compute_finding_fingerprint output format remains stable."""
        from quotes.services.spot_template_validation import compute_finding_fingerprint
        fp = compute_finding_fingerprint("expected_charge_missing", "AWB_DOCUMENTATION", 123, "ba259968-f2c4-4725-b264-3da6d5a166ca")
        self.assertEqual(fp, "expected_charge_missing:AWB_DOCUMENTATION:123:ba259968-f2c4-4725-b264-3da6d5a166ca")

