from django.urls import reverse
from rest_framework.test import APITestCase


class HealthCheckAPITests(APITestCase):
    def test_health_endpoint_is_public_and_reports_ok(self):
        response = self.client.get(reverse("core:health-check"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")
        self.assertEqual(response.json()["database"], "ok")
