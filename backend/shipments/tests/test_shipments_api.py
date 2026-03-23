from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from core.models import City, Country, Location
from parties.models import Address, Company, Contact, Organization


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
        self.customer = Company.objects.create(name="Brisbane Imports", is_customer=True, company_type="CUSTOMER")
        Address.objects.create(
            company=self.customer,
            address_line_1="1 Eagle Street",
            address_line_2="Level 2",
            city=self.city_bne,
            country=self.country_au,
            postal_code="4000",
            is_primary=True,
        )
        self.contact = Contact.objects.create(
            company=self.customer,
            first_name="Cargo",
            last_name="Desk",
            email="desk@example.com",
            phone="+617123456",
            is_primary=True,
            is_active=True,
        )
        self.other_customer = Company.objects.create(name="Sydney Freight", is_customer=True, company_type="CUSTOMER")
        self.other_contact = Contact.objects.create(
            company=self.other_customer,
            first_name="Other",
            last_name="Contact",
            email="other@example.com",
            phone="+612999999",
            is_primary=True,
            is_active=True,
        )

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

    def test_address_book_list_route_is_not_shadowed_by_shipment_detail(self):
        response = self.client.get("/api/v3/shipments/address-book/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    def test_settings_route_is_not_shadowed_by_shipment_detail(self):
        response = self.client.get("/api/v3/shipments/settings/")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["connote_station_code"], "POM")
        self.assertEqual(body["connote_mode_code"], "AF")

    def test_address_book_entry_can_link_company_and_contact_and_store_snapshot(self):
        response = self.client.post(
            "/api/v3/shipments/address-book/",
            data={
                "label": "Brisbane consignee",
                "party_role": "CONSIGNEE",
                "company_id": str(self.customer.id),
                "contact_id": str(self.contact.id),
                "company_name": "Temporary Company",
                "contact_name": "Wrong Name",
                "email": "wrong@example.com",
                "phone": "000",
                "address_line_1": "Temporary Address",
                "address_line_2": "",
                "city": "Temporary City",
                "state": "",
                "postal_code": "0000",
                "country_code": "PG",
                "notes": "",
                "is_active": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["company_id"], str(self.customer.id))
        self.assertEqual(body["contact_id"], str(self.contact.id))
        self.assertEqual(body["company_name"], "Brisbane Imports")
        self.assertEqual(body["contact_name"], "Cargo Desk")
        self.assertEqual(body["email"], "desk@example.com")
        self.assertEqual(body["phone"], "+617123456")
        self.assertEqual(body["address_line_1"], "1 Eagle Street")
        self.assertEqual(body["address_line_2"], "Level 2")
        self.assertEqual(body["city"], "Brisbane")
        self.assertEqual(body["postal_code"], "4000")
        self.assertEqual(body["country_code"], "AU")

    def test_address_book_entry_rejects_contact_from_different_company(self):
        response = self.client.post(
            "/api/v3/shipments/address-book/",
            data={
                "label": "Invalid link",
                "party_role": "CONSIGNEE",
                "company_id": str(self.customer.id),
                "contact_id": str(self.other_contact.id),
                "company_name": "Brisbane Imports",
                "contact_name": "Other Contact",
                "email": "other@example.com",
                "phone": "+612999999",
                "address_line_1": "1 Eagle Street",
                "address_line_2": "",
                "city": "Brisbane",
                "state": "",
                "postal_code": "4000",
                "country_code": "AU",
                "notes": "",
                "is_active": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("contact_id", response.json())
