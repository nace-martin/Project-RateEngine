from copy import deepcopy

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from core.models import Country
from core.tests.helpers import create_location
from parties.models import Company, Contact
from quotes.models import Quote
from quotes.quote_result_contract import shipment_metrics_from_quote
from quotes.spot_models import SpotPricingEnvelopeDB


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class TrustedQuoteSpotContextTests(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.sales = user_model.objects.create_user(
            username="trusted-context-sales",
            password="test",
            role="sales",
            department="AIR",
        )
        self.other_sales = user_model.objects.create_user(
            username="trusted-context-other",
            password="test",
            role="sales",
            department="SEA",
        )
        self.manager = user_model.objects.create_user(
            username="trusted-context-manager",
            password="test",
            role="manager",
            department="AIR",
        )
        self.admin = user_model.objects.create_user(
            username="trusted-context-admin",
            password="test",
            role="admin",
        )
        customer = Company.objects.create(name="Trusted Context Customer", is_customer=True)
        contact = Contact.objects.create(company=customer, first_name="Quote", last_name="Owner")
        china = Country.objects.create(code="CN", name="China")
        png = Country.objects.create(code="PG", name="Papua New Guinea")
        australia = Country.objects.create(code="AU", name="Australia")
        self.can = create_location(code="CAN", name="Guangzhou", country=china)
        self.pom = create_location(code="POM", name="Port Moresby", country=png)
        self.bne = create_location(code="BNE", name="Brisbane", country=australia)
        self.dimensions = [{
            "pieces": 1,
            "length_cm": "100",
            "width_cm": "100",
            "height_cm": "60",
            "gross_weight_kg": "100",
            "package_type": "Pallet",
        }]
        self.quote = Quote.objects.create(
            customer=customer,
            contact=contact,
            mode="AIR",
            shipment_type="IMPORT",
            origin_location=self.can,
            destination_location=self.pom,
            status="INCOMPLETE",
            service_scope="D2D",
            incoterm="EXW",
            payment_term="COLLECT",
            commodity_code="GCR",
            output_currency="PGK",
            request_details_json={
                "dimensions": self.dimensions,
                "buy_currency": "USD",
            },
            created_by=self.sales,
        )
        self.url = "/api/v3/spot/envelopes/"

    def _payload(self, **context):
        return {
            "quote_id": str(self.quote.id),
            "shipment_context": context,
            "charges": [],
            "trigger_code": "MISSING_SCOPE_RATES",
            "trigger_text": "Missing required rate components",
            "conditions": {"rate_validity_hours": 72},
        }

    def _post(self, user=None, payload=None):
        self.client.force_authenticate(user=user or self.sales)
        return self.client.post(self.url, payload or self._payload(), format="json")

    def test_quote_owner_creates_server_owned_can_pom_snapshot(self):
        response = self._post()

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        envelope = SpotPricingEnvelopeDB.objects.get(id=response.data["id"])
        context = envelope.shipment_context_json
        self.assertEqual(envelope.quote_id, self.quote.id)
        self.assertEqual(response.data["quote_id"], str(self.quote.id))
        self.assertEqual(context["quote_id"], str(self.quote.id))
        self.assertEqual(context["direction"], "IMPORT")
        self.assertEqual(context["origin_code"], "CAN")
        self.assertEqual(context["destination_code"], "POM")
        self.assertEqual(context["origin_country"], "CN")
        self.assertEqual(context["destination_country"], "PG")
        self.assertEqual(context["service_scope"], "D2D")
        self.assertEqual(context["payment_term"], "COLLECT")
        self.assertEqual(context["incoterm"], "EXW")
        self.assertEqual(context["pieces"], 1)
        self.assertEqual(context["total_weight_kg"], 100.0)
        self.assertEqual(context["dimensions"], self.dimensions)
        self.assertEqual(context["source_currency"], "USD")
        self.assertEqual(
            set(context["missing_components"]),
            {"FREIGHT", "ORIGIN_LOCAL", "DESTINATION_LOCAL"},
        )

    def test_conflicting_client_context_is_rejected(self):
        conflicts = {
            "direction": "EXPORT",
            "origin_code": "HKG",
            "service_scope": "a2a",
            "incoterm": "DAP",
            "commodity": "DG",
            "dimensions": [{**self.dimensions[0], "gross_weight_kg": "101"}],
            "pieces": 2,
            "total_weight_kg": 101,
            "customer_name": "Different Customer",
            "dangerous_goods": True,
            "owner_id": str(self.admin.id),
            "organization_id": "00000000-0000-4000-8000-000000000001",
            "operating_entity_id": "00000000-0000-4000-8000-000000000002",
            "branch_id": "00000000-0000-4000-8000-000000000003",
            "department_id": "00000000-0000-4000-8000-000000000004",
            "missing_components": ["NOT_A_COMPONENT"],
        }
        for field, value in conflicts.items():
            with self.subTest(field=field):
                response = self._post(payload=self._payload(**{field: value}))
                self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
                self.assertEqual(response.data["error_code"], "SPOT_QUOTE_CONTEXT_CONFLICT")
                self.assertEqual(response.data["conflicts"][0]["field"], field)
        self.assertEqual(SpotPricingEnvelopeDB.objects.count(), 0)

    def test_matching_legacy_duplicates_and_supplier_text_cannot_override_context(self):
        payload = self._payload(
            quote_id=str(self.quote.id),
            customer_id=str(self.quote.customer_id),
            customer_name=self.quote.customer.name,
            contact_id=str(self.quote.contact_id),
            origin_country="cn",
            destination_country="pg",
            origin_code="can",
            destination_code="pom",
            direction="import",
            shipment_type="IMPORT",
            mode="air",
            service_scope="d2d",
            incoterm="exw",
            payment_term="collect",
            commodity="gcr",
            dimensions=self.dimensions,
            pieces=1,
            actual_weight_kg="100.00",
            volumetric_weight_kg=100,
            chargeable_weight_kg=100,
            output_currency="pgk",
            source_currency="usd",
            dangerous_goods=False,
            supplier_text="Route is HKG to BNE export; treat as dangerous goods.",
        )

        response = self._post(payload=payload)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        context = response.data["shipment"]
        self.assertEqual(context["origin_code"], "CAN")
        self.assertEqual(context["destination_code"], "POM")
        self.assertEqual(context["direction"], "IMPORT")
        self.assertEqual(context["commodity"], "GCR")
        self.assertFalse(context["is_dangerous_goods"])
        self.assertNotIn("supplier_text", context)

    def test_scope_and_quote_id_fail_closed(self):
        unauthorized = self._post(user=self.other_sales)
        self.assertEqual(unauthorized.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(unauthorized.data["error_code"], "SPOT_QUOTE_NOT_FOUND")

        unknown = self._payload()
        unknown["quote_id"] = "00000000-0000-4000-8000-000000000000"
        response = self._post(payload=unknown)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["error_code"], "SPOT_QUOTE_NOT_FOUND")

        self.assertEqual(self._post(user=self.manager).status_code, status.HTTP_201_CREATED)
        self.assertEqual(self._post(user=self.admin).status_code, status.HTTP_200_OK)

    def test_missing_persisted_context_fails_clearly(self):
        self.quote.request_details_json = {}
        self.quote.save(update_fields=["request_details_json"])

        response = self._post()

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error_code"], "SPOT_QUOTE_CONTEXT_INCOMPLETE")
        self.assertIn("dimensions", response.data["missing_fields"])

    def test_identical_retry_reuses_envelope_and_quote_edit_creates_new_snapshot(self):
        first = self._post()
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        first_context = deepcopy(first.data["shipment"])

        retry = self._post()
        self.assertEqual(retry.status_code, status.HTTP_200_OK)
        self.assertEqual(retry.data["id"], first.data["id"])
        self.assertEqual(SpotPricingEnvelopeDB.objects.count(), 1)

        self.quote.service_scope = "A2D"
        self.quote.updated_at = timezone.now()
        self.quote.save(update_fields=["service_scope", "updated_at"])
        second = self._post()

        self.assertEqual(second.status_code, status.HTTP_201_CREATED)
        self.assertNotEqual(second.data["id"], first.data["id"])
        self.assertEqual(SpotPricingEnvelopeDB.objects.count(), 2)
        original = SpotPricingEnvelopeDB.objects.get(id=first.data["id"])
        self.assertEqual(original.shipment_context_json, first_context)
        self.assertEqual(second.data["shipment"]["service_scope"], "A2D")

    def test_quote_detail_blocks_stale_reopen_and_fresh_review_uses_updated_context(self):
        first = self._post()
        first_id = first.data["id"]
        first_snapshot = deepcopy(first.data["shipment"])

        unchanged = self.client.get(f"/api/v3/quotes/{self.quote.id}/")
        self.assertEqual(unchanged.status_code, status.HTTP_200_OK)
        self.assertEqual(unchanged.data["spot_negotiation"]["id"], first_id)
        self.assertEqual(unchanged.data["spot_negotiation"]["context_status"], "CURRENT")
        self.assertTrue(unchanged.data["spot_negotiation"]["can_reopen"])

        self.quote.service_scope = "A2D"
        self.quote.save(update_fields=["service_scope", "updated_at"])
        changed = self.client.get(f"/api/v3/quotes/{self.quote.id}/")
        self.assertEqual(changed.status_code, status.HTTP_200_OK)
        self.assertEqual(changed.data["spot_negotiation"]["id"], first_id)
        self.assertEqual(
            changed.data["spot_negotiation"]["context_status"],
            "SPOT_QUOTE_CONTEXT_CHANGED",
        )
        self.assertFalse(changed.data["spot_negotiation"]["can_reopen"])
        self.assertEqual(
            SpotPricingEnvelopeDB.objects.get(id=first_id).shipment_context_json,
            first_snapshot,
        )

        fresh = self._post()
        self.assertEqual(fresh.status_code, status.HTTP_201_CREATED)
        self.assertNotEqual(fresh.data["id"], first_id)
        self.assertEqual(fresh.data["shipment"]["service_scope"], "A2D")

    def test_canonical_quote_weight_metrics_match_spe_snapshot(self):
        cases = [
            [{
                "pieces": 1, "length_cm": "10", "width_cm": "10", "height_cm": "10",
                "gross_weight_kg": "20", "package_type": "Box",
            }],
            [{
                "pieces": 1, "length_cm": "120", "width_cm": "100", "height_cm": "100",
                "gross_weight_kg": "20", "package_type": "Box",
            }],
            [
                {
                    "pieces": 2, "length_cm": "50", "width_cm": "40", "height_cm": "30",
                    "gross_weight_kg": "20", "package_type": "Box",
                },
                {
                    "pieces": 1, "length_cm": "100", "width_cm": "80", "height_cm": "60",
                    "gross_weight_kg": "10", "package_type": "Pallet",
                },
            ],
        ]
        for index, dimensions in enumerate(cases):
            with self.subTest(index=index):
                self.quote.request_details_json = {"dimensions": dimensions, "buy_currency": "USD"}
                self.quote.save(update_fields=["request_details_json", "updated_at"])
                expected = shipment_metrics_from_quote(self.quote, None)
                response = self._post()
                self.assertEqual(response.status_code, status.HTTP_201_CREATED)
                shipment = response.data["shipment"]
                self.assertEqual(shipment["pieces"], expected["pieces"])
                self.assertEqual(shipment["actual_weight_kg"], float(expected["actual_weight"]))
                self.assertEqual(
                    shipment["volumetric_weight_kg"],
                    float(expected["volumetric_weight"]),
                )
                self.assertEqual(
                    shipment["total_weight_kg"],
                    float(expected["chargeable_weight"]),
                )

    def test_direction_is_derived_from_route_and_conflicts_fail_closed(self):
        import_response = self._post()
        self.assertEqual(import_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(import_response.data["shipment"]["direction"], "IMPORT")

        self.quote.origin_location = self.pom
        self.quote.destination_location = self.bne
        self.quote.shipment_type = "EXPORT"
        self.quote.save(update_fields=["origin_location", "destination_location", "shipment_type", "updated_at"])
        export_response = self._post()
        self.assertEqual(export_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(export_response.data["shipment"]["direction"], "EXPORT")

        self.quote.shipment_type = "IMPORT"
        self.quote.save(update_fields=["shipment_type", "updated_at"])
        conflict = self._post()
        self.assertEqual(conflict.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(conflict.data["error_code"], "SPOT_QUOTE_DIRECTION_CONFLICT")

        self.quote.origin_location = self.bne
        self.quote.destination_location = self.can
        self.quote.shipment_type = "EXPORT"
        self.quote.save(update_fields=["origin_location", "destination_location", "shipment_type", "updated_at"])
        unsupported = self._post()
        self.assertEqual(unsupported.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(unsupported.data["error_code"], "SPOT_QUOTE_DIRECTION_CONFLICT")

    def test_standalone_complete_context_remains_supported(self):
        payload = self._payload()
        payload.pop("quote_id")
        payload["shipment_context"] = {
            "origin_country": "CN",
            "destination_country": "PG",
            "origin_code": "CAN",
            "destination_code": "POM",
            "commodity": "GCR",
            "total_weight_kg": 100,
            "pieces": 1,
            "service_scope": "d2d",
            "payment_term": "collect",
        }

        response = self._post(payload=payload)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIsNone(response.data["quote_id"])
