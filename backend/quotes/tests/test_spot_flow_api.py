from django.contrib.auth import get_user_model
from django.urls import reverse

from rest_framework import status
from rest_framework.test import APITestCase

from core.models import Location
from services.models import ServiceComponent


class SpotEnvelopeFlowAPITest(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="spotflow",
            password="pass123",
            email="spotflow@example.com",
        )
        self.client.force_authenticate(user=self.user)

        self.origin = Location.objects.create(name="Port Moresby", code="POM")
        self.destination = Location.objects.create(name="Sydney", code="SYD")

        self.service_component = ServiceComponent.objects.create(
            code="FRT_SPOT",
            description="Spot Airfreight",
            mode="AIR",
            leg="MAIN",
            category="TRANSPORT",
        )

        self.create_url = reverse("quotes:spot-envelope-list-create")

    def test_spot_envelope_flow_acknowledge_compute(self):
        create_payload = {
            "shipment_context": {
                "origin_country": "PG",
                "destination_country": "AU",
                "origin_code": self.origin.code,
                "destination_code": self.destination.code,
                "commodity": "GCR",
                "total_weight_kg": 100,
                "pieces": 2,
            },
            "charges": [
                {
                    "code": "FRT_SPOT",
                    "description": "Airfreight",
                    "amount": 5,
                    "currency": "USD",
                    "unit": "per_kg",
                    "bucket": "airfreight",
                    "is_primary_cost": True,
                    "conditional": False,
                    "source_reference": "Agent email",
                }
            ],
            "trigger_code": "MISSING_SCOPE_RATES",
            "trigger_text": "Missing required rate components",
            "conditions": {
                "rate_validity_hours": 72,
            },
        }

        create_response = self.client.post(self.create_url, create_payload, format="json")
        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)

        spe_id = create_response.json()["id"]

        acknowledge_url = reverse(
            "quotes:spot-envelope-acknowledge", kwargs={"envelope_id": spe_id}
        )
        acknowledge_response = self.client.post(acknowledge_url, format="json")
        self.assertEqual(acknowledge_response.status_code, status.HTTP_200_OK)
        self.assertEqual(acknowledge_response.json()["status"], "ready")

        compute_url = reverse(
            "quotes:spot-envelope-compute", kwargs={"envelope_id": spe_id}
        )
        compute_response = self.client.post(
            compute_url,
            {
                "quote_request": {
                    "payment_term": "PREPAID",
                    "service_scope": "D2D",
                    "output_currency": "PGK",
                }
            },
            format="json",
        )
        self.assertEqual(compute_response.status_code, status.HTTP_200_OK)

        payload = compute_response.json()
        self.assertFalse(payload["is_complete"])
        self.assertIn("ORIGIN_LOCAL", payload["missing_components"])
        self.assertIn("DESTINATION_LOCAL", payload["missing_components"])
        self.assertEqual(payload["pricing_mode"], "SPOT")
        self.assertEqual(len(payload["lines"]), 1)
        self.assertNotEqual(payload["totals"]["total_sell_pgk"], "0")
