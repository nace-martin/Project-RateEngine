from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from rest_framework import status
from rest_framework.test import APITestCase

from core.tests.helpers import create_location, indexed_iata_code
from parties.models import Company, Contact, Organization, OrganizationBranding
from quotes.models import Quote, QuoteVersion, QuoteLine, QuoteTotal
from quotes.spot_models import SpotPricingEnvelopeDB
from core.models import Location


class QuoteRetrieveV3APITest(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="v3tester",
            password="pass123",
            email="v3tester@example.com",
        )
        self.client.force_authenticate(user=self.user)

        self.quote = self._create_quote_with_versions()
        self.url = reverse("quotes:quote-v3-detail", kwargs={"pk": self.quote.id})

    def _create_quote_with_versions(self):
        customer = Company.objects.create(name="Test Customer Co.")
        organization, _ = Organization.objects.get_or_create(
            slug="efm-express-air-cargo",
            defaults={"name": "EFM Express Air Cargo"},
        )
        OrganizationBranding.objects.update_or_create(
            organization=organization,
            defaults={
                "display_name": "EFM Express Air Cargo",
                "support_email": "quotes@efmexpress.com",
                "support_phone": "+675 325 8500",
                "primary_color": "#0F2A56",
                "accent_color": "#D71920",
            },
        )
        contact = Contact.objects.create(
            company=customer,
            first_name="Jane",
            last_name="Doe",
            email=f"jane{uuid4().hex[:6]}@example.com",
        )

        origin_location = create_location(
            name="Los Angeles",
            code="LAX",
        )
        destination_location = create_location(
            name="Port Moresby",
            code="POM",
        )

        quote = Quote.objects.create(
            customer=customer,
            organization=organization,
            contact=contact,
            mode="AIR",
            shipment_type=Quote.ShipmentType.IMPORT,
            incoterm="DAP",
            payment_term=Quote.PaymentTerm.PREPAID,
            output_currency="USD",
            origin_location=origin_location,
            destination_location=destination_location,
            status=Quote.Status.FINALIZED,
            created_by=self.user,
        )

        QuoteVersion.objects.create(
            quote=quote,
            version_number=1,
            status=Quote.Status.DRAFT,
            created_by=self.user,
        )

        latest_version = QuoteVersion.objects.create(
            quote=quote,
            version_number=2,
            status=Quote.Status.FINALIZED,
            created_by=self.user,
        )

        QuoteLine.objects.create(
            quote_version=latest_version,
            service_component=None,
            cost_pgk=Decimal("120.00"),
            cost_fcy=Decimal("35.00"),
            cost_fcy_currency="USD",
            sell_pgk=Decimal("180.00"),
            sell_pgk_incl_gst=Decimal("198.00"),
            sell_fcy=Decimal("55.00"),
            sell_fcy_incl_gst=Decimal("60.50"),
            sell_fcy_currency="USD",
            exchange_rate=Decimal("0.52"),
            cost_source="BASE_COST",
            cost_source_description="Base PGK cost",
            is_rate_missing=False,
        )

        QuoteTotal.objects.create(
            quote_version=latest_version,
            total_cost_pgk=Decimal("120.00"),
            total_sell_pgk=Decimal("180.00"),
            total_sell_pgk_incl_gst=Decimal("198.00"),
            total_sell_fcy=Decimal("55.00"),
            total_sell_fcy_incl_gst=Decimal("60.50"),
            total_sell_fcy_currency="USD",
            has_missing_rates=False,
            notes="Complete totals",
        )

        return quote

    def test_retrieve_returns_latest_version(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.json()
        self.assertEqual(data["id"], str(self.quote.id))
        self.assertEqual(data["latest_version"]["version_number"], 2)
        self.assertEqual(len(data["latest_version"]["lines"]), 1)
        self.assertEqual(data["branding"]["display_name"], "EFM Express Air Cargo")
        self.assertEqual(data["branding"]["support_email"], "quotes@efmexpress.com")

        totals = data["latest_version"]["totals"]
        self.assertEqual(totals["total_sell_fcy"], "55.00")
        self.assertEqual(totals["total_sell_fcy_currency"], "USD")

    def test_retrieve_requires_authentication(self):
        self.client.force_authenticate(user=None)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_spot_negotiation_serializes_latest_envelope(self):
        SpotPricingEnvelopeDB.objects.create(
            quote=self.quote,
            shipment_context_json={
                "origin_country": "PG",
                "destination_country": "AU",
                "origin_code": "POM",
                "destination_code": "SYD",
                "commodity": "GCR",
                "total_weight_kg": 100,
                "pieces": 2,
            },
            spot_trigger_reason_code="MISSING_SCOPE_RATES",
            spot_trigger_reason_text="Missing required rate components",
            expires_at=timezone.now() + timedelta(hours=72),
        )

        second_envelope = SpotPricingEnvelopeDB.objects.create(
            quote=self.quote,
            shipment_context_json={
                "origin_country": "PG",
                "destination_country": "AU",
                "origin_code": "POM",
                "destination_code": "SYD",
                "commodity": "GCR",
                "total_weight_kg": 110,
                "pieces": 3,
            },
            spot_trigger_reason_code="MISSING_SCOPE_RATES",
            spot_trigger_reason_text="Missing required rate components",
            expires_at=timezone.now() + timedelta(hours=72),
        )
        SpotPricingEnvelopeDB.objects.filter(id=second_envelope.id).update(
            created_at=timezone.now() + timedelta(seconds=1)
        )

        detail_response = self.client.get(self.url)
        self.assertEqual(detail_response.status_code, status.HTTP_200_OK)
        detail_data = detail_response.json()
        self.assertEqual(
            detail_data["spot_negotiation"]["id"],
            str(second_envelope.id),
        )

        list_url = reverse("quotes:quote-v3-list")
        list_response = self.client.get(list_url)
        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        list_data = list_response.json()["results"][0]
        self.assertEqual(
            list_data["spot_negotiation"]["id"],
            str(second_envelope.id),
        )

    def test_rate_provider_ignores_internal_source_labels(self):
        latest_version = self.quote.versions.order_by('-version_number').first()
        QuoteLine.objects.create(
            quote_version=latest_version,
            service_component=None,
            sell_pgk=Decimal("10.00"),
            sell_pgk_incl_gst=Decimal("10.00"),
            sell_fcy=Decimal("3.00"),
            sell_fcy_incl_gst=Decimal("3.00"),
            sell_fcy_currency="USD",
            cost_source="10.0000% of COGS",
            is_rate_missing=False,
        )
        QuoteLine.objects.create(
            quote_version=latest_version,
            service_component=None,
            sell_pgk=Decimal("10.00"),
            sell_pgk_incl_gst=Decimal("10.00"),
            sell_fcy=Decimal("3.00"),
            sell_fcy_incl_gst=Decimal("3.00"),
            sell_fcy_currency="USD",
            cost_source="Default",
            is_rate_missing=False,
        )

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["rate_provider"], "Internal")

    def test_rate_provider_returns_real_provider_name(self):
        latest_version = self.quote.versions.order_by('-version_number').first()
        QuoteLine.objects.create(
            quote_version=latest_version,
            service_component=None,
            sell_pgk=Decimal("10.00"),
            sell_pgk_incl_gst=Decimal("10.00"),
            sell_fcy=Decimal("3.00"),
            sell_fcy_incl_gst=Decimal("3.00"),
            sell_fcy_currency="USD",
            cost_source="SPOT-MATRIX-AGENT",
            is_rate_missing=False,
        )

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["rate_provider"], "SPOT-MATRIX-AGENT")


class QuoteListV3APITest(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="v3listtester",
            password="pass123",
            email="v3listtester@example.com",
        )
        self.client.force_authenticate(user=self.user)

        # Create multiple quotes to test pagination
        self.quotes = []
        for i in range(5):
            self.quotes.append(self._create_simple_quote(i))
        
        self.url = reverse("quotes:quote-v3-list")

    def _create_simple_quote(self, index):
        customer = Company.objects.create(name=f"Customer {index}")
        origin = create_location(name=f"Origin {index}", code=indexed_iata_code(index, prefix="O"))
        dest = create_location(name=f"Dest {index}", code=indexed_iata_code(index, prefix="D"))
        
        quote = Quote.objects.create(
            customer=customer,
            mode="AIR",
            origin_location=origin,
            destination_location=dest,
            created_by=self.user,
        )
        
        version = QuoteVersion.objects.create(
            quote=quote,
            version_number=1,
            created_by=self.user,
        )
        
        QuoteTotal.objects.create(
            quote_version=version,
            total_sell_fcy=Decimal("100.00"),
            total_sell_fcy_currency="PGK",
        )
        
        # Add a line item to check if it's EXCLUDED in list view
        QuoteLine.objects.create(
            quote_version=version,
            cost_pgk=Decimal("50.00"),
        )
        
        return quote

    def test_list_is_paginated(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        data = response.json()
        self.assertIn("results", data)
        self.assertIn("count", data)
        self.assertEqual(data["count"], 5)
        self.assertEqual(len(data["results"]), 5)

    def test_list_uses_summary_serializer(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        data = response.json()
        first_quote = data["results"][0]
        
        # Check that latest_version is present but lines/payload_json are NOT
        self.assertIn("latest_version", first_quote)
        self.assertNotIn("lines", first_quote["latest_version"])
        self.assertNotIn("payload_json", first_quote["latest_version"])
        
        # Totals should still be there
        self.assertIn("totals", first_quote["latest_version"])
        self.assertEqual(first_quote["latest_version"]["totals"]["total_sell_fcy"], "100.00")
