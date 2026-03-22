from decimal import Decimal

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from core.models import Location
from parties.models import Company, Organization, OrganizationBranding
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
        self.origin = Location.objects.create(code="POM", name="Port Moresby Jacksons Intl")
        self.destination = Location.objects.create(code="HKG", name="Hong Kong Intl")
        self.url = reverse("quotes:quote-public-detail")

    def _create_quote(
        self,
        *,
        service_scope=None,
        payload_json=None,
        request_details_json=None,
    ) -> Quote:
        quote = Quote.objects.create(
            customer=self.customer,
            organization=self.organization,
            mode="AIR",
            shipment_type=Quote.ShipmentType.EXPORT,
            payment_term=Quote.PaymentTerm.PREPAID,
            service_scope=service_scope,
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

        token = build_public_quote_token(str(quote.id))
        response = self.client.get(self.url, {"token": token})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.json()
        buckets = {bucket["name"]: bucket for bucket in payload["charge_buckets"]}
        origin_lines = buckets["Origin Charges"]["lines"]

        self.assertEqual(len(origin_lines), 1)
        self.assertEqual(origin_lines[0]["description"], "AWB Fee")

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
