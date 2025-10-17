# backend/quotes/tests/test_pdf_generation.py

import pytest
from decimal import Decimal
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework import status

from core.models import Policy, FxSnapshot, Country, City, Currency, LocalTariff
from parties.models import Company
from quotes.models import Quote

@pytest.mark.django_db
class TestQuotePDFGeneration:
    def setup_method(self):
        """Set up the database state for the PDF test."""
        self.client = APIClient()

        # --- Create a complete, valid quote object in the database ---
        country_pg = Country.objects.create(code='PG', name='Papua New Guinea')
        city_pom = City.objects.create(country=country_pg, name='Port Moresby')
        pgk_currency = Currency.objects.create(code='PGK')

        bill_to = Company.objects.create(name='PDF Test Importer')
        shipper = Company.objects.create(name='PDF Test Exporter')

        policy = Policy.objects.create(
            name="PDF Test Policy",
            caf_import_pct=Decimal("0.05"),
            margin_pct=Decimal("0.15"),
            effective_from=timezone.now()
        )
        fx_snapshot = FxSnapshot.objects.create(
            as_of_timestamp=timezone.now(),
            source="TestBSP",
            rates={"AUD": {"tt_buy": "2.50"}}
        )
        LocalTariff.objects.create(
            country=country_pg,
            charge_code='CARTAGE',
            description='PNG Destination Cartage',
            basis=LocalTariff.Basis.FORMULA,
            currency=pgk_currency,
            gst_rate=Decimal("0.10")
        )

        # Use our service to create a valid quote
        from pricing_v2.pricing_service_v2 import PricingServiceV2
        service = PricingServiceV2()
        
        request_data = {
            "scenario": Quote.Scenario.IMP_D2D_COLLECT,
            "chargeable_kg": "120.00",
            "bill_to_id": str(bill_to.id),
            "shipper_id": str(shipper.id),
            "consignee_id": str(bill_to.id),
            "buy_lines": [{"currency": "AUD", "amount": "1000.00", "description": "Freight"}],
            "origin_code": "BNE",
            "destination_code": "POM"
        }
        self.test_quote = service.create_quote(request_data)


    def test_generate_pdf_for_quote(self):
        """
        Tests that the PDF generation endpoint returns a valid PDF file.
        """
        # --- Construct the URL for our specific quote ---
        url = f"/api/v2/quotes/{self.test_quote.id}/pdf/"

        # --- Make the GET request ---
        response = self.client.get(url)

        # --- Assert the response headers and content ---
        assert response.status_code == status.HTTP_200_OK
        
        # Check that the browser will treat it as a file download
        assert response.has_header('Content-Disposition')
        assert 'attachment' in response['Content-Disposition']
        assert f'filename="Quote-{self.test_quote.quote_number}.pdf"' in response['Content-Disposition']
        
        # Check the file type
        assert response['Content-Type'] == 'application/pdf'

        # Check that the content is a valid PDF file (by checking the "magic number")
        assert response.content.startswith(b'%PDF-')
