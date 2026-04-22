from django.contrib.auth import get_user_model
from django.urls import reverse
from unittest.mock import patch
from django.utils import timezone
from datetime import date, timedelta

from rest_framework import status
from rest_framework.test import APITestCase

from core.models import Location
from core.tests.helpers import create_location
from pricing_v4.models import ChargeAlias, CommodityChargeRule, ProductCode
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

        self.origin = create_location(name="Port Moresby", code="POM")
        self.destination = create_location(name="Sydney", code="SYD")

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

    def _component_outcomes(self, freight: bool, origin: bool, destination: bool):
        def outcome(component: str, covered: bool):
            return {
                "component": component,
                "status": "covered_exact" if covered else "missing_rate",
                "detail": "",
                "match_type": "exact" if covered else None,
                "selector_model": None,
                "selector_context": {},
                "missing_dimensions": [],
                "conflicting_rows": [],
                "fallback_applied": False,
            }

        return {
            COMPONENT_FREIGHT: outcome(COMPONENT_FREIGHT, freight),
            COMPONENT_ORIGIN_LOCAL: outcome(COMPONENT_ORIGIN_LOCAL, origin),
            COMPONENT_DESTINATION_LOCAL: outcome(COMPONENT_DESTINATION_LOCAL, destination),
        }

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

    def test_create_spe_persists_normalization_metadata_without_breaking_manual_write_path(self):
        product_code = ProductCode.objects.create(
            id=1095,
            code="EXP-FREIGHT-SPOT",
            description="Export Freight Spot",
            domain=ProductCode.DOMAIN_EXPORT,
            category=ProductCode.CATEGORY_FREIGHT,
            is_gst_applicable=False,
            gst_rate="0.00",
            gst_treatment=ProductCode.GST_TREATMENT_ZERO_RATED,
            gl_revenue_code="4100",
            gl_cost_code="5100",
            default_unit=ProductCode.UNIT_KG,
        )
        alias = ChargeAlias.objects.create(
            alias_text="Airfreight",
            match_type=ChargeAlias.MatchType.EXACT,
            mode_scope=ChargeAlias.ModeScope.EXPORT,
            direction_scope=ChargeAlias.DirectionScope.MAIN,
            product_code=product_code,
            priority=10,
        )

        create_payload = {
            "shipment_context": {
                "origin_country": "PG",
                "destination_country": "AU",
                "origin_code": self.origin.code,
                "destination_code": self.destination.code,
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
            "conditions": {
                "rate_validity_hours": 72,
            },
        }

        create_response = self.client.post(self.create_url, create_payload, format="json")
        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        payload_line = create_response.json()["charges"][0]
        self.assertEqual(payload_line["description"], "Airfreight")
        self.assertEqual(payload_line["source_reference"], "Agent email")
        self.assertEqual(payload_line["source_label"], "Airfreight")
        self.assertEqual(payload_line["normalized_label"], "airfreight")
        self.assertEqual(payload_line["normalization_status"], "MATCHED")
        self.assertEqual(payload_line["normalization_method"], "EXACT_ALIAS")
        self.assertEqual(payload_line["matched_alias_id"], alias.id)
        self.assertEqual(
            payload_line["resolved_product_code"],
            {
                "id": product_code.id,
                "code": product_code.code,
                "description": product_code.description,
            },
        )
        self.assertEqual(
            payload_line["effective_resolved_product_code"],
            {
                "id": product_code.id,
                "code": product_code.code,
                "description": product_code.description,
            },
        )

        spe = SpotPricingEnvelopeDB.objects.get(id=create_response.json()["id"])
        line = spe.charge_lines.get()
        self.assertEqual(line.source_label, "Airfreight")
        self.assertEqual(line.normalized_label, "airfreight")
        self.assertEqual(line.normalization_status, SPEChargeLineDB.NormalizationStatus.MATCHED)
        self.assertEqual(line.normalization_method, SPEChargeLineDB.NormalizationMethod.EXACT_ALIAS)
        self.assertEqual(line.matched_alias_id, alias.id)
        self.assertEqual(line.resolved_product_code_id, product_code.id)

    def test_manual_resolution_endpoint_persists_review_metadata_and_returns_updated_charge_line(self):
        manual_product_code = ProductCode.objects.create(
            id=2095,
            code="EXP-MANUAL-TERM",
            description="Export Manual Terminal",
            domain=ProductCode.DOMAIN_EXPORT,
            category=ProductCode.CATEGORY_HANDLING,
            is_gst_applicable=False,
            gst_rate="0.00",
            gst_treatment=ProductCode.GST_TREATMENT_ZERO_RATED,
            gl_revenue_code="4100",
            gl_cost_code="5100",
            default_unit=ProductCode.UNIT_SHIPMENT,
        )

        create_payload = {
            "shipment_context": {
                "origin_country": "PG",
                "destination_country": "AU",
                "origin_code": self.origin.code,
                "destination_code": self.destination.code,
                "commodity": "GCR",
                "total_weight_kg": 100,
                "pieces": 1,
            },
            "charges": [
                {
                    "code": "FRT_SPOT",
                    "description": "Unknown freight fee",
                    "amount": 25,
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
        spe_id = create_response.json()["id"]
        charge_line_id = create_response.json()["charges"][0]["id"]

        manual_review_url = reverse(
            "quotes:spot-charge-line-manual-resolution",
            kwargs={"envelope_id": spe_id, "charge_line_id": charge_line_id},
        )
        review_response = self.client.patch(
            manual_review_url,
            {"product_code_id": manual_product_code.id},
            format="json",
        )
        self.assertEqual(review_response.status_code, status.HTTP_200_OK)
        payload = review_response.json()
        self.assertEqual(payload["normalization_status"], "UNMAPPED")
        self.assertEqual(payload["manual_resolution_status"], "RESOLVED")
        self.assertEqual(
            payload["manual_resolved_product_code"],
            {
                "id": manual_product_code.id,
                "code": manual_product_code.code,
                "description": manual_product_code.description,
            },
        )
        self.assertEqual(
            payload["effective_resolved_product_code"],
            {
                "id": manual_product_code.id,
                "code": manual_product_code.code,
                "description": manual_product_code.description,
            },
        )
        self.assertEqual(payload["effective_resolution_status"], "RESOLVED")
        self.assertFalse(payload["requires_review"])
        self.assertEqual(payload["manual_resolution_by_user_id"], str(self.user.id))
        self.assertEqual(payload["manual_resolution_by_username"], self.user.username)
        self.assertIsNotNone(payload["manual_resolution_at"])

        line = SPEChargeLineDB.objects.get(id=charge_line_id)
        self.assertEqual(line.manual_resolution_status, SPEChargeLineDB.ManualResolutionStatus.RESOLVED)
        self.assertEqual(line.manual_resolved_product_code_id, manual_product_code.id)
        self.assertEqual(line.manual_resolution_by_id, self.user.id)
        self.assertIsNotNone(line.manual_resolution_at)

        detail_url = reverse("quotes:spot-envelope-detail", kwargs={"envelope_id": spe_id})
        detail_response = self.client.get(detail_url, format="json")
        self.assertEqual(detail_response.status_code, status.HTTP_200_OK)
        detail_line = detail_response.json()["charges"][0]
        self.assertEqual(detail_line["effective_resolution_status"], "RESOLVED")
        self.assertFalse(detail_line["requires_review"])
        self.assertEqual(detail_line["manual_resolution_status"], "RESOLVED")
        self.assertEqual(detail_line["manual_resolved_product_code"]["code"], manual_product_code.code)
        self.assertEqual(detail_line["effective_resolved_product_code"]["code"], manual_product_code.code)

    def test_manual_resolution_endpoint_rejects_matched_lines(self):
        product_code = ProductCode.objects.create(
            id=3095,
            code="EXP-FREIGHT-MATCHED",
            description="Export Freight Matched",
            domain=ProductCode.DOMAIN_EXPORT,
            category=ProductCode.CATEGORY_FREIGHT,
            is_gst_applicable=False,
            gst_rate="0.00",
            gst_treatment=ProductCode.GST_TREATMENT_ZERO_RATED,
            gl_revenue_code="4100",
            gl_cost_code="5100",
            default_unit=ProductCode.UNIT_KG,
        )
        ChargeAlias.objects.create(
            alias_text="Airfreight",
            match_type=ChargeAlias.MatchType.EXACT,
            mode_scope=ChargeAlias.ModeScope.EXPORT,
            direction_scope=ChargeAlias.DirectionScope.MAIN,
            product_code=product_code,
            priority=10,
        )

        create_payload = {
            "shipment_context": {
                "origin_country": "PG",
                "destination_country": "AU",
                "origin_code": self.origin.code,
                "destination_code": self.destination.code,
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
        spe_id = create_response.json()["id"]
        charge_line_id = create_response.json()["charges"][0]["id"]

        manual_review_url = reverse(
            "quotes:spot-charge-line-manual-resolution",
            kwargs={"envelope_id": spe_id, "charge_line_id": charge_line_id},
        )
        review_response = self.client.patch(
            manual_review_url,
            {"product_code_id": product_code.id},
            format="json",
        )
        self.assertEqual(review_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("UNMAPPED or AMBIGUOUS", review_response.json()["error"])

    def test_patch_preserves_manual_resolution_metadata_for_existing_charge_lines(self):
        manual_product_code = ProductCode.objects.create(
            id=4095,
            code="EXP-MANUAL-PATCH",
            description="Export Manual Patch Preserve",
            domain=ProductCode.DOMAIN_EXPORT,
            category=ProductCode.CATEGORY_HANDLING,
            is_gst_applicable=False,
            gst_rate="0.00",
            gst_treatment=ProductCode.GST_TREATMENT_ZERO_RATED,
            gl_revenue_code="4100",
            gl_cost_code="5100",
            default_unit=ProductCode.UNIT_SHIPMENT,
        )

        create_payload = {
            "shipment_context": {
                "origin_country": "PG",
                "destination_country": "AU",
                "origin_code": self.origin.code,
                "destination_code": self.destination.code,
                "commodity": "GCR",
                "total_weight_kg": 100,
                "pieces": 1,
            },
            "charges": [
                {
                    "code": "FRT_SPOT",
                    "description": "Unknown patch freight",
                    "amount": 25,
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
        spe_id = create_response.json()["id"]
        initial_line = create_response.json()["charges"][0]

        manual_review_url = reverse(
            "quotes:spot-charge-line-manual-resolution",
            kwargs={"envelope_id": spe_id, "charge_line_id": initial_line["id"]},
        )
        review_response = self.client.patch(
            manual_review_url,
            {"product_code_id": manual_product_code.id},
            format="json",
        )
        self.assertEqual(review_response.status_code, status.HTTP_200_OK)

        patch_url = reverse("quotes:spot-envelope-detail", kwargs={"envelope_id": spe_id})
        patch_response = self.client.patch(
            patch_url,
            {
                "charges": [
                    {
                        "charge_line_id": initial_line["id"],
                        "code": initial_line["code"],
                        "description": initial_line["description"],
                        "amount": 30,
                        "currency": initial_line["currency"],
                        "unit": initial_line["unit"],
                        "bucket": initial_line["bucket"],
                        "is_primary_cost": initial_line["is_primary_cost"],
                        "conditional": initial_line["conditional"],
                        "source_reference": initial_line["source_reference"],
                    }
                ]
            },
            format="json",
        )
        self.assertEqual(patch_response.status_code, status.HTTP_200_OK)
        payload_line = patch_response.json()["charges"][0]
        self.assertEqual(payload_line["id"], initial_line["id"])
        self.assertEqual(payload_line["amount"], "30.00")
        self.assertEqual(payload_line["normalization_status"], "UNMAPPED")
        self.assertEqual(payload_line["manual_resolution_status"], "RESOLVED")
        self.assertEqual(payload_line["manual_resolved_product_code"]["id"], manual_product_code.id)
        self.assertEqual(payload_line["effective_resolved_product_code"]["id"], manual_product_code.id)

        line = SpotPricingEnvelopeDB.objects.get(id=spe_id).charge_lines.get()
        self.assertEqual(line.amount, 30)
        self.assertEqual(str(line.id), initial_line["id"])
        self.assertEqual(line.manual_resolution_status, SPEChargeLineDB.ManualResolutionStatus.RESOLVED)
        self.assertEqual(line.manual_resolved_product_code_id, manual_product_code.id)

    def test_patch_matches_existing_charge_line_by_signature_when_charge_line_id_missing(self):
        create_payload = {
            "shipment_context": {
                "origin_country": "PG",
                "destination_country": "AU",
                "origin_code": self.origin.code,
                "destination_code": self.destination.code,
                "commodity": "GCR",
                "total_weight_kg": 100,
                "pieces": 1,
            },
            "charges": [
                {
                    "code": "FRT_SPOT",
                    "description": "Fallback Signature Freight",
                    "amount": 25,
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
        spe_id = create_response.json()["id"]
        initial_line = create_response.json()["charges"][0]

        patch_url = reverse("quotes:spot-envelope-detail", kwargs={"envelope_id": spe_id})
        patch_response = self.client.patch(
            patch_url,
            {
                "charges": [
                    {
                        "code": initial_line["code"],
                        "description": initial_line["description"],
                        "amount": 40,
                        "currency": initial_line["currency"],
                        "unit": initial_line["unit"],
                        "bucket": initial_line["bucket"],
                        "is_primary_cost": initial_line["is_primary_cost"],
                        "conditional": initial_line["conditional"],
                        "source_reference": initial_line["source_reference"],
                    }
                ]
            },
            format="json",
        )
        self.assertEqual(patch_response.status_code, status.HTTP_200_OK)
        payload_line = patch_response.json()["charges"][0]
        self.assertEqual(payload_line["id"], initial_line["id"])
        self.assertEqual(payload_line["amount"], "40.00")

        line = SpotPricingEnvelopeDB.objects.get(id=spe_id).charge_lines.get()
        self.assertEqual(str(line.id), initial_line["id"])
        self.assertEqual(line.amount, 40)

    @patch("quotes.spot_services.RateAvailabilityService.get_component_outcomes")
    def test_evaluate_trigger_requires_payment_term(self, mock_outcomes):
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
        mock_outcomes.assert_not_called()

    @patch("quotes.spot_services.RateAvailabilityService.get_component_outcomes")
    def test_evaluate_trigger_passes_payment_term_to_availability(self, mock_outcomes):
        mock_outcomes.return_value = self._component_outcomes(
            freight=False,
            origin=False,
            destination=True,
        )
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
        kwargs = mock_outcomes.call_args.kwargs
        self.assertEqual(kwargs["payment_term"], "COLLECT")

    @patch("quotes.spot_services.RateAvailabilityService.get_component_outcomes")
    def test_evaluate_trigger_returns_missing_commodity_rates(self, mock_outcomes):
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

        mock_outcomes.return_value = self._component_outcomes(
            freight=True,
            origin=True,
            destination=False,
        )
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

    @patch("quotes.spot_services.RateAvailabilityService.get_component_outcomes")
    def test_evaluate_trigger_returns_manual_commodity_requirement(self, mock_outcomes):
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

        mock_outcomes.return_value = self._component_outcomes(
            freight=True,
            origin=True,
            destination=False,
        )
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

    @patch("quotes.spot_services.RateAvailabilityService.get_component_outcomes")
    def test_acknowledge_allows_d2d_without_context_missing_components_when_freight_available(self, mock_outcomes):
        mock_outcomes.return_value = self._component_outcomes(
            freight=True,
            origin=False,
            destination=False,
        )

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
