from django.contrib.auth import get_user_model
from django.urls import reverse
from unittest.mock import patch
from django.utils import timezone
from datetime import date, timedelta

from rest_framework import status
from rest_framework.test import APITestCase

from core.models import Location
from pricing_v4.models import CommodityChargeRule, ProductCode
from services.models import ServiceComponent
from quotes.completeness import (
    COMPONENT_FREIGHT,
    COMPONENT_ORIGIN_LOCAL,
    COMPONENT_DESTINATION_LOCAL,
)
from quotes.spot_models import SpotPricingEnvelopeDB, SPEChargeLineDB


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
        self.scope_url = reverse("quotes:spot-validate-scope")
        self.evaluate_url = reverse("quotes:spot-evaluate-trigger")

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

    def test_scope_validation_resolves_country_from_airport_codes(self):
        response = self.client.post(
            self.scope_url,
            {
                "origin_country": "OTHER",
                "destination_country": "OTHER",
                "origin_code": "POM",
                "destination_code": "SIN",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.json()
        self.assertTrue(payload["is_valid"])
        self.assertIsNone(payload["error"])

    @patch("quotes.spot_services.RateAvailabilityService.get_availability")
    def test_evaluate_trigger_requires_payment_term(self, mock_availability):
        response = self.client.post(
            self.evaluate_url,
            {
                "origin_country": "AU",
                "destination_country": "PG",
                "origin_airport": "BNE",
                "destination_airport": "POM",
                "service_scope": "A2D",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("payment_term", response.json().get("error", ""))
        mock_availability.assert_not_called()

    @patch("quotes.spot_services.RateAvailabilityService.get_availability")
    def test_evaluate_trigger_passes_payment_term_to_availability(self, mock_availability):
        mock_availability.return_value = {
            COMPONENT_FREIGHT: False,
            COMPONENT_ORIGIN_LOCAL: False,
            COMPONENT_DESTINATION_LOCAL: True,
        }
        response = self.client.post(
            self.evaluate_url,
            {
                "origin_country": "AU",
                "destination_country": "PG",
                "origin_airport": "SIN",
                "destination_airport": "POM",
                "service_scope": "A2D",
                "payment_term": "COLLECT",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.json()["is_spot_required"])
        kwargs = mock_availability.call_args.kwargs
        self.assertEqual(kwargs["payment_term"], "COLLECT")

    @patch("quotes.spot_services.RateAvailabilityService.get_availability")
    def test_evaluate_trigger_returns_missing_commodity_rates(self, mock_availability):
        valid_from = date.today() - timedelta(days=1)
        valid_until = date.today() + timedelta(days=30)
        product_code = ProductCode.objects.create(
            id=1979,
            code="EXP-DG-API",
            description="Export DG API Test",
            domain="EXPORT",
            category="HANDLING",
            is_gst_applicable=True,
            gl_revenue_code="4100",
            gl_cost_code="5100",
            default_unit="SHIPMENT",
        )
        CommodityChargeRule.objects.create(
            shipment_type="EXPORT",
            service_scope="D2A",
            commodity_code="DG",
            product_code=product_code,
            leg="ORIGIN",
            trigger_mode="AUTO",
            effective_from=valid_from,
            effective_to=valid_until,
        )

        mock_availability.return_value = {
            COMPONENT_FREIGHT: True,
            COMPONENT_ORIGIN_LOCAL: True,
            COMPONENT_DESTINATION_LOCAL: False,
        }
        response = self.client.post(
            self.evaluate_url,
            {
                "origin_country": "PG",
                "destination_country": "AU",
                "origin_airport": "POM",
                "destination_airport": "SYD",
                "service_scope": "D2A",
                "payment_term": "PREPAID",
                "commodity": "DG",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.json()
        self.assertTrue(payload["is_spot_required"])
        self.assertEqual(payload["trigger"]["code"], "MISSING_COMMODITY_RATES")
        self.assertEqual(payload["trigger"]["missing_product_codes"], ["EXP-DG-API"])
        self.assertIn("Export DG API Test (EXP-DG-API)", payload["trigger"]["text"])

    @patch("quotes.spot_services.RateAvailabilityService.get_availability")
    def test_evaluate_trigger_returns_manual_commodity_requirement(self, mock_availability):
        valid_from = date.today() - timedelta(days=1)
        valid_until = date.today() + timedelta(days=30)
        product_code = ProductCode.objects.create(
            id=1978,
            code="EXP-AVI-MANUAL-API",
            description="Export AVI Manual API Test",
            domain="EXPORT",
            category="HANDLING",
            is_gst_applicable=True,
            gl_revenue_code="4100",
            gl_cost_code="5100",
            default_unit="SHIPMENT",
        )
        CommodityChargeRule.objects.create(
            shipment_type="EXPORT",
            service_scope="D2A",
            commodity_code="AVI",
            product_code=product_code,
            leg="ORIGIN",
            trigger_mode="REQUIRES_MANUAL",
            effective_from=valid_from,
            effective_to=valid_until,
        )

        mock_availability.return_value = {
            COMPONENT_FREIGHT: True,
            COMPONENT_ORIGIN_LOCAL: True,
            COMPONENT_DESTINATION_LOCAL: False,
        }
        response = self.client.post(
            self.evaluate_url,
            {
                "origin_country": "PG",
                "destination_country": "AU",
                "origin_airport": "POM",
                "destination_airport": "SYD",
                "service_scope": "D2A",
                "payment_term": "PREPAID",
                "commodity": "AVI",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.json()
        self.assertTrue(payload["is_spot_required"])
        self.assertEqual(payload["trigger"]["code"], "COMMODITY_REQUIRES_MANUAL")
        self.assertEqual(payload["trigger"]["manual_required_product_codes"], ["EXP-AVI-MANUAL-API"])
        self.assertIn(
            "Export AVI Manual API Test (EXP-AVI-MANUAL-API)",
            payload["trigger"]["text"],
        )

    def test_acknowledge_allows_a2d_destination_only_charge_without_airfreight(self):
        create_payload = {
            "shipment_context": {
                "origin_country": "AU",
                "destination_country": "PG",
                "origin_code": self.destination.code,
                "destination_code": self.origin.code,
                "commodity": "GCR",
                "total_weight_kg": 100,
                "pieces": 1,
                "service_scope": "a2d",
            },
            "charges": [
                {
                    "code": "DESTINATION_LOCAL",
                    "description": "Destination handling",
                    "amount": 75,
                    "currency": "USD",
                    "unit": "flat",
                    "bucket": "destination_charges",
                    "is_primary_cost": False,
                    "conditional": False,
                    "source_reference": "Agent email",
                }
            ],
            "trigger_code": "MISSING_SCOPE_RATES",
            "trigger_text": "Missing required rate components",
            "conditions": {"rate_validity_hours": 72},
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

    @patch("quotes.spot_services.RateAvailabilityService.get_availability")
    def test_acknowledge_allows_d2d_without_context_missing_components_when_freight_available(self, mock_availability):
        mock_availability.return_value = {
            COMPONENT_FREIGHT: True,
            COMPONENT_ORIGIN_LOCAL: False,
            COMPONENT_DESTINATION_LOCAL: False,
        }

        create_payload = {
            "shipment_context": {
                "origin_country": "PG",
                "destination_country": "HK",
                "origin_code": self.origin.code,
                "destination_code": "HKG",
                "commodity": "GCR",
                "total_weight_kg": 100,
                "pieces": 1,
                "service_scope": "d2d",
            },
            "charges": [
                {
                    "code": "DESTINATION_LOCAL",
                    "description": "Destination handling",
                    "amount": 75,
                    "currency": "USD",
                    "unit": "flat",
                    "bucket": "destination_charges",
                    "is_primary_cost": False,
                    "conditional": False,
                    "source_reference": "Agent email",
                }
            ],
            "trigger_code": "MISSING_SCOPE_RATES",
            "trigger_text": "Missing required rate components",
            "conditions": {"rate_validity_hours": 72},
        }

        create_response = self.client.post(self.create_url, create_payload, format="json")
        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)

        shipment = create_response.json()["shipment"]
        self.assertNotIn(COMPONENT_FREIGHT, shipment.get("missing_components") or [])

        spe_id = create_response.json()["id"]
        acknowledge_url = reverse(
            "quotes:spot-envelope-acknowledge", kwargs={"envelope_id": spe_id}
        )
        acknowledge_response = self.client.post(acknowledge_url, format="json")
        self.assertEqual(acknowledge_response.status_code, status.HTTP_200_OK)
        self.assertEqual(acknowledge_response.json()["status"], "ready")

    def test_create_spe_normalizes_country_codes_from_route(self):
        create_payload = {
            "shipment_context": {
                "origin_country": "OTHER",
                "destination_country": "OTHER",
                "origin_code": "POM",
                "destination_code": "SIN",
                "commodity": "GCR",
                "total_weight_kg": 100,
                "pieces": 1,
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
            "conditions": {"rate_validity_hours": 72},
        }

        create_response = self.client.post(self.create_url, create_payload, format="json")
        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        shipment = create_response.json()["shipment"]
        self.assertEqual(shipment["origin_country"], "PG")
        self.assertEqual(shipment["destination_country"], "SG")

    def test_create_spe_accepts_non_whitelisted_iso_country_codes(self):
        create_payload = {
            "shipment_context": {
                "origin_country": "MY",
                "destination_country": "PG",
                "origin_code": "KUL",
                "destination_code": self.origin.code,
                "commodity": "GCR",
                "total_weight_kg": 100,
                "pieces": 1,
                "service_scope": "a2d",
            },
            "charges": [
                {
                    "code": "DESTINATION_LOCAL",
                    "description": "Destination handling",
                    "amount": 75,
                    "currency": "USD",
                    "unit": "flat",
                    "bucket": "destination_charges",
                    "is_primary_cost": False,
                    "conditional": False,
                    "source_reference": "Agent email",
                }
            ],
            "trigger_code": "MISSING_SCOPE_RATES",
            "trigger_text": "Missing required rate components",
            "conditions": {"rate_validity_hours": 72},
        }

        create_response = self.client.post(self.create_url, create_payload, format="json")
        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        shipment = create_response.json()["shipment"]
        self.assertEqual(shipment["origin_country"], "MY")
        self.assertEqual(shipment["destination_country"], "PG")

    def test_acknowledge_ignores_legacy_zero_amount_charge_lines(self):
        create_payload = {
            "shipment_context": {
                "origin_country": "AU",
                "destination_country": "PG",
                "origin_code": self.destination.code,
                "destination_code": self.origin.code,
                "commodity": "GCR",
                "total_weight_kg": 100,
                "pieces": 1,
                "service_scope": "a2d",
                "missing_components": ["DESTINATION_LOCAL"],
            },
            "charges": [
                {
                    "code": "DESTINATION_LOCAL",
                    "description": "Destination handling",
                    "amount": 75,
                    "currency": "USD",
                    "unit": "flat",
                    "bucket": "destination_charges",
                    "is_primary_cost": False,
                    "conditional": False,
                    "source_reference": "Agent email",
                }
            ],
            "trigger_code": "MISSING_SCOPE_RATES",
            "trigger_text": "Missing required rate components",
            "conditions": {"rate_validity_hours": 72},
        }

        create_response = self.client.post(self.create_url, create_payload, format="json")
        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        spe_id = create_response.json()["id"]

        spe = SpotPricingEnvelopeDB.objects.get(id=spe_id)
        SPEChargeLineDB.objects.create(
            envelope=spe,
            code="LEGACY_ZERO",
            description="Legacy zero line",
            amount=0,
            currency="USD",
            unit="flat",
            bucket="destination_charges",
            is_primary_cost=False,
            conditional=False,
            source_reference="legacy",
            entered_at=timezone.now(),
        )

        acknowledge_url = reverse(
            "quotes:spot-envelope-acknowledge", kwargs={"envelope_id": spe_id}
        )
        acknowledge_response = self.client.post(acknowledge_url, format="json")
        self.assertEqual(acknowledge_response.status_code, status.HTTP_200_OK)
        self.assertEqual(acknowledge_response.json()["status"], "ready")
