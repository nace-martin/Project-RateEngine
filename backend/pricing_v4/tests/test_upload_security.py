from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APITestCase

from parties.models import Organization


class V4RateUploadSecurityTests(APITestCase):
    def setUp(self):
        organization = Organization.objects.create(name="EFM", slug="efm-pricing")
        self.user = get_user_model().objects.create_user(
            username="pricing-manager",
            password="pass123",
            role="manager",
            organization=organization,
        )
        self.client.force_authenticate(user=self.user)

    def test_rate_upload_rejects_non_csv_file(self):
        upload = SimpleUploadedFile("rates.pdf", b"%PDF-not-a-csv", content_type="application/pdf")

        response = self.client.post("/api/v4/rates/upload/", {"file": upload}, format="multipart")

        self.assertEqual(response.status_code, 400)
        self.assertIn("CSV", response.data["message"])
