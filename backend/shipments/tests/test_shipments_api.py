from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from core.models import City, Country, Location
from parties.models import Address, Company, Contact, Organization
from shipments.models import Shipment, ShipmentCharge, ShipmentEvent
from shipments.services import recalculate_shipment_totals


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
        self.manager_user = user_model.objects.create_user(
            username="shipment-manager",
            password="pass123",
            role="manager",
            organization=self.organization,
        )
        self.sales_user = user_model.objects.create_user(
            username="shipment-sales",
            password="pass123",
            role="sales",
            organization=self.organization,
        )
        self.other_organization = Organization.objects.create(name="Other Org", slug="other-org")
        self.other_org_user = user_model.objects.create_user(
            username="other-org-user",
            password="pass123",
            role="admin",
            organization=self.other_organization,
        )
        self.client.force_authenticate(user=self.user)

        self.country_pg = Country.objects.create(code="PG", name="Papua New Guinea")
        self.country_au = Country.objects.create(code="AU", name="Australia")
        self.city_pom = City.objects.create(name="Port Moresby", country=self.country_pg)
        self.city_bne = City.objects.create(name="Brisbane", country=self.country_au)
        self.city_lae = City.objects.create(name="Lae", country=self.country_pg)
        self.origin_pom = Location.objects.create(code="POM", name="Port Moresby", city=self.city_pom, country=self.country_pg)
        self.destination_bne = Location.objects.create(code="BNE", name="Brisbane", city=self.city_bne, country=self.country_au)
        self.destination_lae = Location.objects.create(code="LAE", name="Lae", city=self.city_lae, country=self.country_pg)
        self.origin_bne = Location.objects.create(code="BNE2", name="Brisbane Export", city=self.city_bne, country=self.country_au)
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

        self.base_payload = {
            "shipment_type": "EXPORT",
            "branch": "POM",
            "shipment_date": "2026-03-22",
            "reference_number": "EFM-OPS-1",
            "booking_reference": "BK-1001",
            "flight_reference": "PX001",
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
            "origin_location_id": str(self.origin_pom.id),
            "destination_location_id": str(self.destination_bne.id),
            "cargo_type": "GENERAL_CARGO",
            "service_product": "EXPRESS",
            "service_scope": "A2A",
            "payment_term": "PREPAID",
            "export_reference": "EXP-77",
            "invoice_reference": "INV-22",
            "permit_reference": "PRM-9",
            "cargo_description": "General cargo documents",
            "dangerous_goods_details": "",
            "perishable_details": "",
            "handling_notes": "Keep dry.",
            "declaration_notes": "No batteries.",
            "customs_notes": "Handle export clearance at origin.",
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
                    "description": "Legacy freight",
                    "amount": "1250.00",
                    "currency": "PGK",
                    "payment_by": "SHIPPER",
                    "notes": "",
                }
            ],
        }

    def test_create_export_shipment_ignores_charge_lines(self):
        response = self.client.post("/api/v3/shipments/", data=self.base_payload, format="json")

        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["status"], "DRAFT")
        self.assertEqual(body["shipment_type"], "EXPORT")
        self.assertEqual(body["branch"], "POM")
        self.assertEqual(body["total_pieces"], 2)
        self.assertEqual(body["total_gross_weight_kg"], "24.00")
        self.assertEqual(body["total_charges_amount"], "0.00")
        self.assertEqual(body["charges"], [])

    def test_create_domestic_shipment(self):
        payload = dict(self.base_payload)
        payload["shipment_type"] = "DOMESTIC"
        payload["destination_location_id"] = str(self.destination_lae.id)
        payload["consignee_city"] = "Lae"
        payload["consignee_country_code"] = "PG"
        payload["flight_reference"] = ""
        payload["export_reference"] = ""
        payload["invoice_reference"] = ""
        payload["permit_reference"] = ""
        payload["customs_notes"] = ""

        response = self.client.post("/api/v3/shipments/", data=payload, format="json")

        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["shipment_type"], "DOMESTIC")
        self.assertEqual(body["origin_code"], "POM")
        self.assertEqual(body["destination_code"], "LAE")

    def test_finalize_generates_connote_number_and_pdf(self):
        create_response = self.client.post("/api/v3/shipments/", data=self.base_payload, format="json")
        shipment_id = create_response.json()["id"]

        finalize_response = self.client.post(f"/api/v3/shipments/{shipment_id}/finalize/", data={}, format="json")
        pdf_response = self.client.get(f"/api/v3/shipments/{shipment_id}/pdf/")

        self.assertEqual(finalize_response.status_code, 200)
        finalize_body = finalize_response.json()
        self.assertEqual(finalize_body["status"], "FINALIZED")
        self.assertTrue(finalize_body["connote_number"].startswith("POM-AF-20260322-"))
        self.assertEqual(pdf_response.status_code, 200)
        self.assertEqual(pdf_response["Content-Type"], "application/pdf")
        self.assertTrue(pdf_response.content.startswith(b"%PDF"))

    def test_finalize_is_idempotent_for_finalized_shipments(self):
        create_response = self.client.post("/api/v3/shipments/", data=self.base_payload, format="json")
        shipment_id = create_response.json()["id"]

        self.client.post(f"/api/v3/shipments/{shipment_id}/finalize/", data={}, format="json")
        second_finalize = self.client.post(
            f"/api/v3/shipments/{shipment_id}/finalize/",
            data={"branch": "LAE", "shipper_company_name": "Tampered"},
            format="json",
        )

        self.assertEqual(second_finalize.status_code, 200)
        shipment = Shipment.objects.get(pk=shipment_id)
        self.assertEqual(shipment.branch, "POM")
        self.assertEqual(shipment.shipper_company_name, "EFM Express")

    def test_second_pdf_request_is_logged_as_reprint(self):
        create_response = self.client.post("/api/v3/shipments/", data=self.base_payload, format="json")
        shipment_id = create_response.json()["id"]

        self.client.post(f"/api/v3/shipments/{shipment_id}/finalize/", data={}, format="json")
        self.client.get(f"/api/v3/shipments/{shipment_id}/pdf/")
        self.client.get(f"/api/v3/shipments/{shipment_id}/pdf/")

        shipment = Shipment.objects.get(pk=shipment_id)
        self.assertEqual(shipment.documents.count(), 2)
        self.assertTrue(shipment.events.filter(event_type=ShipmentEvent.EventType.PDF_GENERATED).exists())
        self.assertTrue(shipment.events.filter(event_type=ShipmentEvent.EventType.REPRINTED).exists())

    def test_shipment_document_download_url_uses_authenticated_endpoint(self):
        create_response = self.client.post("/api/v3/shipments/", data=self.base_payload, format="json")
        shipment_id = create_response.json()["id"]

        self.client.post(f"/api/v3/shipments/{shipment_id}/finalize/", data={}, format="json")
        self.client.get(f"/api/v3/shipments/{shipment_id}/pdf/")
        detail_response = self.client.get(f"/api/v3/shipments/{shipment_id}/")

        self.assertEqual(detail_response.status_code, 200)
        document = detail_response.json()["documents"][0]
        self.assertIn(f"/api/v3/shipments/{shipment_id}/documents/", document["download_url"])
        self.assertTrue(document["download_url"].endswith("/download/"))

    def test_shipment_document_download_rejects_cross_organization_access(self):
        create_response = self.client.post("/api/v3/shipments/", data=self.base_payload, format="json")
        shipment_id = create_response.json()["id"]

        self.client.post(f"/api/v3/shipments/{shipment_id}/finalize/", data={}, format="json")
        self.client.get(f"/api/v3/shipments/{shipment_id}/pdf/")
        shipment = Shipment.objects.get(pk=shipment_id)
        document = shipment.documents.first()

        self.client.force_authenticate(user=self.other_org_user)
        response = self.client.get(f"/api/v3/shipments/{shipment_id}/documents/{document.id}/download/")

        self.assertEqual(response.status_code, 404)

    def test_finalized_shipments_are_locked(self):
        create_response = self.client.post("/api/v3/shipments/", data=self.base_payload, format="json")
        shipment_id = create_response.json()["id"]
        self.client.post(f"/api/v3/shipments/{shipment_id}/finalize/", data={}, format="json")

        update_response = self.client.patch(
            f"/api/v3/shipments/{shipment_id}/",
            data={"branch": "LAE"},
            format="json",
        )

        self.assertEqual(update_response.status_code, 400)
        self.assertIn("locked", str(update_response.json()).lower())

    def test_export_validation_rejects_domestic_route(self):
        payload = dict(self.base_payload)
        payload["shipment_type"] = "EXPORT"
        payload["destination_location_id"] = str(self.destination_lae.id)
        payload["consignee_city"] = "Lae"
        payload["consignee_country_code"] = "PG"

        response = self.client.post("/api/v3/shipments/", data=payload, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertIn("shipment_type", response.json())

    def test_patch_preserves_legacy_import_shipment_type(self):
        create_response = self.client.post("/api/v3/shipments/", data=self.base_payload, format="json")
        shipment = Shipment.objects.get(pk=create_response.json()["id"])
        shipment.shipment_type = Shipment.ShipmentType.IMPORT
        shipment.origin_location = self.origin_bne
        shipment.destination_location = self.origin_pom
        shipment.save(update_fields=["shipment_type", "origin_location", "destination_location", "updated_at"])

        response = self.client.patch(
            f"/api/v3/shipments/{shipment.id}/",
            data={"branch": "BNE"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        shipment.refresh_from_db()
        self.assertEqual(shipment.shipment_type, Shipment.ShipmentType.IMPORT)
        self.assertEqual(response.json()["shipment_type"], Shipment.ShipmentType.IMPORT)

    def test_patch_preserves_legacy_third_party_payment_term(self):
        create_response = self.client.post("/api/v3/shipments/", data=self.base_payload, format="json")
        shipment = Shipment.objects.get(pk=create_response.json()["id"])
        shipment.payment_term = Shipment.PaymentTerm.THIRD_PARTY
        shipment.save(update_fields=["payment_term", "updated_at"])

        response = self.client.patch(
            f"/api/v3/shipments/{shipment.id}/",
            data={"branch": "BNE"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        shipment.refresh_from_db()
        self.assertEqual(shipment.payment_term, Shipment.PaymentTerm.THIRD_PARTY)
        self.assertEqual(response.json()["payment_term"], Shipment.PaymentTerm.THIRD_PARTY)

    def test_finalize_requires_branch_and_piece_completion(self):
        payload = dict(self.base_payload)
        payload["branch"] = ""
        payload["pieces"] = []

        create_response = self.client.post("/api/v3/shipments/", data=payload, format="json")
        self.assertEqual(create_response.status_code, 201)
        shipment_id = create_response.json()["id"]

        finalize_response = self.client.post(f"/api/v3/shipments/{shipment_id}/finalize/", data={}, format="json")

        self.assertEqual(finalize_response.status_code, 400)

    def test_pdf_rejects_incomplete_draft_finalize(self):
        payload = dict(self.base_payload)
        payload["branch"] = ""
        payload["pieces"] = []

        create_response = self.client.post("/api/v3/shipments/", data=payload, format="json")
        shipment_id = create_response.json()["id"]

        pdf_response = self.client.get(f"/api/v3/shipments/{shipment_id}/pdf/")

        self.assertEqual(pdf_response.status_code, 400)
        shipment = Shipment.objects.get(pk=shipment_id)
        self.assertEqual(shipment.status, Shipment.Status.DRAFT)
        self.assertFalse(shipment.connote_number)

    def test_duplicate_creates_new_draft_without_charges(self):
        create_response = self.client.post("/api/v3/shipments/", data=self.base_payload, format="json")
        shipment_id = create_response.json()["id"]

        response = self.client.post(f"/api/v3/shipments/{shipment_id}/duplicate/", data={}, format="json")

        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["status"], "DRAFT")
        self.assertNotEqual(body["id"], shipment_id)
        self.assertEqual(body["source_shipment_id"], shipment_id)
        self.assertEqual(body["charges"], [])

    def test_duplicate_rejects_finalized_shipments(self):
        create_response = self.client.post("/api/v3/shipments/", data=self.base_payload, format="json")
        shipment_id = create_response.json()["id"]
        self.client.post(f"/api/v3/shipments/{shipment_id}/finalize/", data={}, format="json")

        response = self.client.post(f"/api/v3/shipments/{shipment_id}/duplicate/", data={}, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertIn("reissue", str(response.json()).lower())

    def test_draft_update_preserves_existing_legacy_charges(self):
        create_response = self.client.post("/api/v3/shipments/", data=self.base_payload, format="json")
        shipment_id = create_response.json()["id"]
        shipment = Shipment.objects.get(pk=shipment_id)
        ShipmentCharge.objects.create(
            shipment=shipment,
            line_number=1,
            charge_type=ShipmentCharge.ChargeType.FREIGHT,
            description="Legacy freight",
            amount="1250.00",
            currency="PGK",
            payment_by=ShipmentCharge.PaymentBy.SHIPPER,
        )
        recalculate_shipment_totals(shipment)

        response = self.client.patch(
            f"/api/v3/shipments/{shipment_id}/",
            data={"branch": "LAE"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        shipment.refresh_from_db()
        self.assertEqual(shipment.charges.count(), 1)
        self.assertEqual(str(shipment.total_charges_amount), "1250.00")
        self.assertEqual(response.json()["charges"][0]["description"], "Legacy freight")

    def test_sales_user_cannot_cancel_or_reissue_finalized_shipment(self):
        create_response = self.client.post("/api/v3/shipments/", data=self.base_payload, format="json")
        shipment_id = create_response.json()["id"]
        self.client.post(f"/api/v3/shipments/{shipment_id}/finalize/", data={}, format="json")

        self.client.force_authenticate(user=self.sales_user)
        cancel_response = self.client.post(
            f"/api/v3/shipments/{shipment_id}/cancel/",
            data={"reason": "Attempted override"},
            format="json",
        )
        reissue_response = self.client.post(f"/api/v3/shipments/{shipment_id}/reissue/", data={}, format="json")

        self.assertEqual(cancel_response.status_code, 403)
        self.assertEqual(reissue_response.status_code, 403)

    def test_manager_can_reissue_finalized_shipment_and_original_is_marked_reissued(self):
        create_response = self.client.post("/api/v3/shipments/", data=self.base_payload, format="json")
        shipment_id = create_response.json()["id"]
        self.client.post(f"/api/v3/shipments/{shipment_id}/finalize/", data={}, format="json")

        self.client.force_authenticate(user=self.manager_user)
        response = self.client.post(f"/api/v3/shipments/{shipment_id}/reissue/", data={}, format="json")

        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["status"], "DRAFT")
        self.assertEqual(body["reissued_from_id"], shipment_id)
        original = Shipment.objects.get(pk=shipment_id)
        self.assertEqual(original.status, Shipment.Status.REISSUED)

    def test_manager_cancel_requires_reason_for_finalized_shipment(self):
        create_response = self.client.post("/api/v3/shipments/", data=self.base_payload, format="json")
        shipment_id = create_response.json()["id"]
        self.client.post(f"/api/v3/shipments/{shipment_id}/finalize/", data={}, format="json")

        self.client.force_authenticate(user=self.manager_user)
        response = self.client.post(f"/api/v3/shipments/{shipment_id}/cancel/", data={"reason": ""}, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertIn("reason", str(response.json()).lower())

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
