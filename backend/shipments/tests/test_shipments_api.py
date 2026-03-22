from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from core.models import City, Country, Location
from parties.models import Organization


class ShipmentAPITests(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.organization = Organization.objects.create(name="EFM", slug="efm")
        self.user = user_model.objects.create_user(
            username="shipment-user",
            password="pass123",
            role="admin",
            organization=self.organization,
        )
        self.client.force_authenticate(user=self.user)

        self.country_pg = Country.objects.create(code="PG", name="Papua New Guinea")
        self.country_au = Country.objects.create(code="AU", name="Australia")
        self.city_pom = City.objects.create(name="Port Moresby", country=self.country_pg)
        self.city_bne = City.objects.create(name="Brisbane", country=self.country_au)
        self.origin = Location.objects.create(code="POM", name="Port Moresby", city=self.city_pom, country=self.country_pg)
        self.destination = Location.objects.create(code="BNE", name="Brisbane", city=self.city_bne, country=self.country_au)

        self.payload = {
            "shipment_date": "2026-03-22",
            "reference_number": "EFM-OPS-1",
            "shipper_company_name": "EFM Express",
            "shipper_contact_name": "Ops Team",
            "shipper_email": "ops@efm.example",
            "shipper_phone": "+675123456",
            "shipper_address_line_1": "Jacksons Parade",
            "shipper_address_line_2": "",
            "shipper_city": "Port Moresby",
            "shipper_state": "NCD",
            "shipper_postal_code": "121",
            "shipper_country_code": "PG",
            "consignee_company_name": "Brisbane Imports",
            "consignee_contact_name": "Cargo Desk",
            "consignee_email": "desk@example.com",
            "consignee_phone": "+617123456",
            "consignee_address_line_1": "1 Eagle Street",
            "consignee_address_line_2": "",
            "consignee_city": "Brisbane",
            "consignee_state": "QLD",
            "consignee_postal_code": "4000",
            "consignee_country_code": "AU",
            "origin_location_id": str(self.origin.id),
            "destination_location_id": str(self.destination.id),
            "service_level": "EXPRESS",
            "payment_term": "PREPAID",
            "commodity_description": "General Cargo",
            "goods_description": "Documents",
            "is_dangerous_goods": False,
            "dangerous_goods_details": "",
            "is_perishable": False,
            "perishable_details": "",
            "handling_notes": "Keep dry.",
            "declaration_notes": "No batteries.",
            "declared_value": "500.00",
            "currency": "PGK",
            "pieces": [
                {
                    "piece_count": 2,
                    "package_type": "CTN",
                    "description": "Cartons",
                    "length_cm": "50",
                    "width_cm": "40",
                    "height_cm": "30",
                    "gross_weight_kg": "12",
                }
            ],
            "charges": [
                {
                    "charge_type": "FREIGHT",
                    "description": "Air freight",
                    "amount": "1250.00",
                    "currency": "PGK",
                    "payment_by": "SHIPPER",
                    "notes": "",
                }
            ],
        }

    def test_create_shipment_calculates_totals(self):
        response = self.client.post("/api/v3/shipments/", data=self.payload, format="json")

        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["status"], "DRAFT")
        self.assertEqual(body["total_pieces"], 2)
        self.assertEqual(body["total_gross_weight_kg"], "24.00")
        self.assertEqual(body["total_charges_amount"], "1250.00")

    def test_finalize_generates_connote_number(self):
        create_response = self.client.post("/api/v3/shipments/", data=self.payload, format="json")
        shipment_id = create_response.json()["id"]

        response = self.client.post(f"/api/v3/shipments/{shipment_id}/finalize/", data={}, format="json")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "FINALIZED")
        self.assertTrue(body["connote_number"].startswith("POM-AF-20260322-"))

    def test_dangerous_goods_requires_details(self):
        payload = dict(self.payload)
        payload["is_dangerous_goods"] = True
        payload["dangerous_goods_details"] = ""

        response = self.client.post("/api/v3/shipments/", data=payload, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertIn("dangerous_goods_details", response.json())

    def test_duplicate_creates_new_draft(self):
        create_response = self.client.post("/api/v3/shipments/", data=self.payload, format="json")
        shipment_id = create_response.json()["id"]

        response = self.client.post(f"/api/v3/shipments/{shipment_id}/duplicate/", data={}, format="json")

        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["status"], "DRAFT")
        self.assertNotEqual(body["id"], shipment_id)
        self.assertEqual(body["source_shipment_id"], shipment_id)

    def test_pdf_endpoint_returns_pdf_for_finalized_shipment(self):
        create_response = self.client.post("/api/v3/shipments/", data=self.payload, format="json")
        shipment_id = create_response.json()["id"]
        self.client.post(f"/api/v3/shipments/{shipment_id}/finalize/", data={}, format="json")

        response = self.client.get(f"/api/v3/shipments/{shipment_id}/pdf/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(response.content.startswith(b"%PDF"))
