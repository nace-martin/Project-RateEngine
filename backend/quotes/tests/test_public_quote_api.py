from decimal import Decimal

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from core.models import Location
from core.tests.helpers import create_location
from parties.models import Company, Contact, Organization, OrganizationBranding
from quotes.models import Quote, QuoteLine, QuoteTotal, QuoteVersion
from quotes.public_links import build_public_quote_token
from services.models import ServiceComponent


class QuotePublicDetailAPITest(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="public_quote_tester",
            password="pass123",
            email="public_quote_tester@example.com",
        )
        self.customer = Company.objects.create(name="Seed Customer")
        self.organization, _ = Organization.objects.get_or_create(
            slug="efm-express-air-cargo",
            defaults={"name": "EFM Express Air Cargo"},
        )
        self.branding, _ = OrganizationBranding.objects.update_or_create(
            organization=self.organization,
            defaults={
                "display_name": "EFM Express Air Cargo",
                "support_email": "quotes@efmexpress.com",
                "support_phone": "+675 325 8500",
                "public_quote_tagline": "Air cargo quotations from EFM Express Air Cargo",
                "primary_color": "#0F2A56",
                "accent_color": "#D71920",
            },
        )
        self.origin = create_location(code="POM", name="Port Moresby Jacksons Intl")
        self.destination = create_location(code="HKG", name="Hong Kong Intl")
        self.url = reverse("quotes:quote-public-detail")

    def _create_quote(
        self,
        *,
        service_scope=None,
        contact=None,
        incoterm="DAP",
        payment_term=Quote.PaymentTerm.PREPAID,
        shipment_type=Quote.ShipmentType.EXPORT,
        payload_json=None,
        request_details_json=None,
    ) -> Quote:
        quote = Quote.objects.create(
            customer=self.customer,
            contact=contact,
            organization=self.organization,
            mode="AIR",
            shipment_type=shipment_type,
            payment_term=payment_term,
            service_scope=service_scope,
            incoterm=incoterm,
            output_currency="USD",
            origin_location=self.origin,
            destination_location=self.destination,
            status=Quote.Status.FINALIZED,
            created_by=self.user,
            request_details_json=request_details_json,
        )

        version = QuoteVersion.objects.create(
            quote=quote,
            version_number=1,
            status=Quote.Status.FINALIZED,
            payload_json=payload_json,
            created_by=self.user,
        )
        QuoteTotal.objects.create(
            quote_version=version,
            total_cost_pgk=Decimal("100.00"),
            total_sell_pgk=Decimal("150.00"),
            total_sell_pgk_incl_gst=Decimal("165.00"),
            total_sell_fcy=Decimal("50.00"),
            total_sell_fcy_incl_gst=Decimal("55.00"),
            total_sell_fcy_currency="USD",
        )
        return quote

    def test_public_quote_returns_persisted_customer_and_shipment_details(self):
        contact = Contact.objects.create(
            company=self.customer,
            first_name="Chris",
            last_name="Im",
            email="chris@example.com",
        )
        quote = self._create_quote(
            service_scope="D2D",
            contact=contact,
            incoterm="EXW",
            payment_term=Quote.PaymentTerm.COLLECT,
            shipment_type=Quote.ShipmentType.IMPORT,
            payload_json={
                "shipment": {
                    "pieces": [
                        {
                            "pieces": 1,
                            "length_cm": 0,
                            "width_cm": 0,
                            "height_cm": 0,
                            "gross_weight_kg": 100,
                        }
                    ]
                }
            },
        )
        token = build_public_quote_token(str(quote.id))

        response = self.client.get(self.url, {"token": token})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.json()
        self.assertEqual(payload["customer"]["name"], "Seed Customer")
        self.assertEqual(payload["customer"]["contact"], "Chris Im")
        self.assertEqual(payload["customer"]["contact_id"], str(contact.id))
        self.assertEqual(payload["shipment"]["incoterm"], "EXW")
        self.assertEqual(payload["shipment"]["payment_term"], "COLLECT")
        self.assertEqual(payload["shipment"]["service_scope"], "D2D")
        self.assertEqual(payload["shipment"]["direction"], "IMPORT")
        self.assertEqual(payload["shipment"]["chargeable_weight_kg"], "100.00")
        self.assertEqual(payload["route"]["origin_code"], "POM")
        self.assertEqual(payload["route"]["destination_code"], "HKG")
        self.assertEqual(payload["totals"]["sell_excl_gst"], "50.00")
        self.assertEqual(payload["totals"]["gst"], "5.00")

    def test_public_quote_does_not_treat_customer_id_as_missing_contact_fallback(self):
        quote = self._create_quote(
            service_scope="D2D",
            request_details_json={"contact_id": str(self.customer.id)},
        )
        token = build_public_quote_token(str(quote.id))

        response = self.client.get(self.url, {"token": token})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.json()
        self.assertIsNone(payload["customer"]["contact"])
        self.assertIsNone(payload["customer"]["contact_id"])

    def test_public_quote_returns_scope_from_quote_field(self):
        quote = self._create_quote(service_scope="A2D")
        token = build_public_quote_token(str(quote.id))

        response = self.client.get(self.url, {"token": token})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.json()
        self.assertEqual(payload["shipment"]["service_scope"], "A2D")
        self.assertEqual(payload["route"]["origin_name"], "Port Moresby Jacksons Intl")
        self.assertEqual(payload["branding"]["display_name"], "EFM Express Air Cargo")
        self.assertEqual(payload["branding"]["public_quote_tagline"], "Air cargo quotations from EFM Express Air Cargo")

    def test_public_quote_falls_back_to_version_payload_scope(self):
        quote = self._create_quote(service_scope=None, payload_json={"service_scope": "d2d"})
        token = build_public_quote_token(str(quote.id))

        response = self.client.get(self.url, {"token": token})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.json()
        self.assertEqual(payload["shipment"]["service_scope"], "D2D")

    def test_public_quote_falls_back_to_request_payload_scope(self):
        quote = self._create_quote(
            service_scope=None,
            payload_json={},
            request_details_json={"quote_request": {"service_scope": "d2a"}},
        )
        token = build_public_quote_token(str(quote.id))

        response = self.client.get(self.url, {"token": token})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.json()
        self.assertEqual(payload["shipment"]["service_scope"], "D2A")

    def test_public_quote_uses_quote_line_bucket_for_totals(self):
        quote = self._create_quote(service_scope="D2D")
        version = quote.versions.get(version_number=1)

        # Intentionally keep component leg as MAIN to prove line.bucket is authoritative.
        fsc_component = ServiceComponent.objects.create(
            code="EXP-FSC-AIR",
            description="Airline Export Fuel Surcharge",
            mode="AIR",
            leg="MAIN",
            category="FREIGHT",
        )
        freight_component = ServiceComponent.objects.create(
            code="EXP-FRT-AIR",
            description="Export Air Freight",
            mode="AIR",
            leg="MAIN",
            category="FREIGHT",
        )

        QuoteLine.objects.create(
            quote_version=version,
            service_component=fsc_component,
            sell_pgk=Decimal("30.00"),
            sell_fcy=Decimal("10.00"),
            sell_fcy_currency="USD",
            sell_fcy_incl_gst=Decimal("10.00"),
            cost_source_description="Airline Export Fuel Surcharge",
            leg="ORIGIN",
            bucket="origin_charges",
        )
        QuoteLine.objects.create(
            quote_version=version,
            service_component=freight_component,
            sell_pgk=Decimal("120.00"),
            sell_fcy=Decimal("40.00"),
            sell_fcy_currency="USD",
            sell_fcy_incl_gst=Decimal("40.00"),
            cost_source_description="Export Air Freight",
            leg="MAIN",
            bucket="airfreight",
        )

        token = build_public_quote_token(str(quote.id))
        response = self.client.get(self.url, {"token": token})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.json()
        buckets = {bucket["name"]: bucket for bucket in payload["charge_buckets"]}

        self.assertEqual(buckets["Origin Charges"]["subtotal"], "10.00")
        self.assertEqual(buckets["Freight"]["subtotal"], "40.00")
        self.assertIn(
            "Airline Export Fuel Surcharge",
            [line["description"] for line in buckets["Origin Charges"]["lines"]],
        )

    def test_public_quote_hides_cost_only_lines_from_charge_breakdown(self):
        quote = self._create_quote(service_scope="D2D")
        version = quote.versions.get(version_number=1)

        awb_component = ServiceComponent.objects.create(
            code="DOM-AWB",
            description="AWB Fee",
            mode="AIR",
            leg="ORIGIN",
            category="DOCUMENTATION",
        )
        doc_component = ServiceComponent.objects.create(
            code="DOM-DOC",
            description="Documentation Fee",
            mode="AIR",
            leg="ORIGIN",
            category="DOCUMENTATION",
        )
        terminal_component = ServiceComponent.objects.create(
            code="DOM-TERMINAL",
            description="Terminal Fee",
            mode="AIR",
            leg="ORIGIN",
            category="HANDLING",
        )

        QuoteLine.objects.create(
            quote_version=version,
            service_component=awb_component,
            sell_pgk=Decimal("70.00"),
            sell_fcy=Decimal("70.00"),
            sell_fcy_currency="PGK",
            sell_fcy_incl_gst=Decimal("77.00"),
            cost_source_description="AWB Fee",
            leg="ORIGIN",
            bucket="origin_charges",
        )
        QuoteLine.objects.create(
            quote_version=version,
            service_component=doc_component,
            sell_pgk=Decimal("0.00"),
            sell_fcy=Decimal("0.00"),
            sell_fcy_currency="PGK",
            sell_fcy_incl_gst=Decimal("0.00"),
            cost_pgk=Decimal("35.00"),
            cost_source_description="Documentation Fee",
            leg="ORIGIN",
            bucket="origin_charges",
        )
        QuoteLine.objects.create(
            quote_version=version,
            service_component=terminal_component,
            sell_pgk=Decimal("0.00"),
            sell_fcy=Decimal("0.00"),
            sell_fcy_currency="PGK",
            sell_fcy_incl_gst=Decimal("0.00"),
            cost_pgk=Decimal("35.00"),
            cost_source_description="Terminal Fee",
            leg="ORIGIN",
            bucket="origin_charges",
        )

        token = build_public_quote_token(str(quote.id))
        response = self.client.get(self.url, {"token": token})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.json()
        buckets = {bucket["name"]: bucket for bucket in payload["charge_buckets"]}
        origin_lines = buckets["Origin Charges"]["lines"]

        self.assertEqual(len(origin_lines), 1)
        self.assertEqual(origin_lines[0]["description"], "AWB Fee")

    def test_public_quote_hides_unapplied_conditional_lines_from_charge_breakdown(self):
        quote = self._create_quote(service_scope="D2D")
        quote.quote_number = "QT-2026-0001"
        quote.output_currency = "PGK"
        quote.save(update_fields=["quote_number", "output_currency"])
        version = quote.versions.get(version_number=1)

        QuoteLine.objects.create(
            quote_version=version,
            cost_source_description="Import Documentation Fee (Origin)",
            sell_pgk=Decimal("159.02"),
            leg="DESTINATION",
            bucket="origin_charges",
        )
        QuoteLine.objects.create(
            quote_version=version,
            cost_source_description="Import Origin Customs Clearance",
            sell_pgk=Decimal("159.02"),
            leg="ORIGIN",
            bucket="origin_charges",
        )
        QuoteLine.objects.create(
            quote_version=version,
            cost_source_description="Import Origin Permit / License",
            sell_pgk=Decimal("265.04"),
            leg="ORIGIN",
            bucket="origin_charges",
            conditional=True,
            is_informational=True,
        )
        QuoteLine.objects.create(
            quote_version=version,
            cost_source_description="Pick-Up Fee (Origin)",
            sell_pgk=Decimal("689.09"),
            leg="DESTINATION",
            bucket="origin_charges",
        )

        token = build_public_quote_token(str(quote.id))
        response = self.client.get(self.url, {"token": token})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.json()
        buckets = {bucket["name"]: bucket for bucket in payload["charge_buckets"]}
        origin_bucket = buckets["Origin Charges"]
        descriptions = [line["description"] for line in origin_bucket["lines"]]

        self.assertEqual(origin_bucket["subtotal"], "1007.13")
        self.assertNotIn("Import Origin Permit / License", descriptions)
        self.assertNotIn("265.04", [line["sell"] for line in origin_bucket["lines"]])

    def test_public_quote_groups_charge_lines_into_customer_facing_subcategories(self):
        quote = self._create_quote(service_scope="D2D")
        quote.output_currency = "PGK"
        quote.save(update_fields=["output_currency"])
        version = quote.versions.get(version_number=1)

        customs_component = ServiceComponent.objects.create(
            code="DST-CUST",
            description="Customs Clearance (Dest)",
            mode="AIR",
            leg="DESTINATION",
            category="CUSTOMS",
        )
        agency_component = ServiceComponent.objects.create(
            code="DST-AGENCY",
            description="Agency Fee (Dest)",
            mode="AIR",
            leg="DESTINATION",
            category="ACCESSORIAL",
        )
        cartage_component = ServiceComponent.objects.create(
            code="DST-CARTAGE",
            description="Cartage & Delivery (Dest)",
            mode="AIR",
            leg="DESTINATION",
            category="LOCAL",
        )
        cartage_fuel_component = ServiceComponent.objects.create(
            code="DST-CART-FUEL",
            description="Cartage Fuel Surcharge (V4)",
            mode="AIR",
            leg="DESTINATION",
            category="ACCESSORIAL",
        )
        handling_component = ServiceComponent.objects.create(
            code="DST-HANDLE",
            description="Loading Fee / Forklift (Dest)",
            mode="AIR",
            leg="DESTINATION",
            category="HANDLING",
        )
        doc_component = ServiceComponent.objects.create(
            code="DST-DOCS",
            description="Documentation Fee (Dest)",
            mode="AIR",
            leg="DESTINATION",
            category="DOCUMENTATION",
        )
        freight_component = ServiceComponent.objects.create(
            code="FRT-AIR",
            description="Import Air Freight",
            mode="AIR",
            leg="MAIN",
            category="TRANSPORT",
        )
        surcharge_component = ServiceComponent.objects.create(
            code="FRT-SEC",
            description="Security Surcharge",
            mode="AIR",
            leg="MAIN",
            category="ACCESSORIAL",
        )
        service_component = ServiceComponent.objects.create(
            code="DST-PROC",
            description="Processing Fee",
            mode="AIR",
            leg="DESTINATION",
            category="ACCESSORIAL",
        )
        other_component = ServiceComponent.objects.create(
            code="DST-MISC",
            description="Miscellaneous Charge",
            mode="AIR",
            leg="DESTINATION",
            category="ACCESSORIAL",
        )

        line_specs = [
            (customs_component, "Customs Clearance (Dest)", "300.00", "destination_charges"),
            (agency_component, "Agency Fee (Dest)", "250.00", "destination_charges"),
            (cartage_component, "Cartage & Delivery (Dest)", "150.00", "destination_charges"),
            (cartage_fuel_component, "Cartage Fuel Surcharge (V4)", "15.00", "destination_charges"),
            (handling_component, "Loading Fee / Forklift (Dest)", "150.00", "destination_charges"),
            (doc_component, "Documentation Fee (Dest)", "150.00", "destination_charges"),
            (service_component, "Processing Fee", "40.00", "destination_charges"),
            (other_component, "Miscellaneous Charge", "10.00", "destination_charges"),
            (freight_component, "Import Air Freight", "3975.53", "airfreight"),
            (surcharge_component, "Security Surcharge", "25.00", "airfreight"),
        ]
        for component, description, amount, bucket in line_specs:
            QuoteLine.objects.create(
                quote_version=version,
                service_component=component,
                cost_source_description=description,
                sell_pgk=Decimal(amount),
                leg=component.leg,
                bucket=bucket,
            )

        token = build_public_quote_token(str(quote.id))
        response = self.client.get(self.url, {"token": token})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.json()
        buckets = {bucket["name"]: bucket for bucket in payload["charge_buckets"]}
        destination_groups = {group["name"]: group for group in buckets["Destination Charges"]["groups"]}
        freight_groups = {group["name"]: group for group in buckets["Freight"]["groups"]}

        self.assertEqual(buckets["Destination Charges"]["subtotal"], "1065.00")
        self.assertEqual(destination_groups["Customs / Regulatory"]["subtotal"], "550.00")
        self.assertEqual(
            [line["description"] for line in destination_groups["Customs / Regulatory"]["lines"]],
            ["Customs Clearance (Dest)", "Agency Fee (Dest)"],
        )
        self.assertEqual(destination_groups["Local Transport / Cartage"]["subtotal"], "165.00")
        self.assertEqual(
            [line["description"] for line in destination_groups["Local Transport / Cartage"]["lines"]],
            ["Cartage & Delivery (Dest)", "Cartage Fuel Surcharge (V4)"],
        )
        self.assertEqual(destination_groups["Documentation"]["subtotal"], "150.00")
        self.assertEqual(destination_groups["Handling / Terminal"]["subtotal"], "150.00")
        self.assertEqual(destination_groups["Service / Agency Fees"]["subtotal"], "40.00")
        self.assertEqual(destination_groups["Other Charges"]["subtotal"], "10.00")

        self.assertEqual(buckets["Freight"]["subtotal"], "4000.53")
        self.assertEqual(freight_groups["Freight / Carrier"]["subtotal"], "3975.53")
        self.assertEqual(freight_groups["Carrier Surcharges"]["subtotal"], "25.00")

    def test_public_quote_includes_branding_payload(self):
        quote = self._create_quote(service_scope="D2D")
        token = build_public_quote_token(str(quote.id))

        response = self.client.get(self.url, {"token": token})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.json()
        self.assertEqual(payload["branding"]["display_name"], "EFM Express Air Cargo")
        self.assertEqual(payload["branding"]["support_email"], "quotes@efmexpress.com")
        self.assertEqual(payload["branding"]["support_phone"], "+675 325 8500")
        self.assertEqual(payload["branding"]["primary_color"], "#0F2A56")
        self.assertEqual(payload["branding"]["accent_color"], "#D71920")
        self.assertTrue(payload["branding"]["logo_url"])
        self.assertTrue(payload["branding"]["logo_url"].endswith("/static/images/efm_logo_cropped.png"))

    @override_settings(STATIC_URL="https://cdn.example.com/static/")
    def test_public_quote_branding_keeps_absolute_static_url(self):
        quote = self._create_quote(service_scope="D2D")
        token = build_public_quote_token(str(quote.id))

        response = self.client.get(self.url, {"token": token})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.json()
        self.assertEqual(
            payload["branding"]["logo_url"],
            "https://cdn.example.com/static/images/efm_logo_cropped.png",
        )

    def test_public_quote_branding_falls_back_to_static_logo_when_branding_is_inactive(self):
        self.branding.logo_primary = "branding/efm-express-air-cargo/primary-logo.png"
        self.branding.is_active = False
        self.branding.save(update_fields=["logo_primary", "is_active"])
        quote = self._create_quote(service_scope="D2D")
        token = build_public_quote_token(str(quote.id))

        response = self.client.get(self.url, {"token": token})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.json()
        self.assertTrue(payload["branding"]["logo_url"].endswith("/static/images/efm_logo_cropped.png"))
