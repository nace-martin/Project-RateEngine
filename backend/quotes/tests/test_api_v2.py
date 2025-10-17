# backend/quotes/tests/test_api_v2.py

import pytest
from decimal import Decimal
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework import status

from core.models import Policy, FxSnapshot, Country, City, LocalTariff, Currency
from parties.models import Company
from quotes.models import Quote

@pytest.mark.django_db
class TestCreateQuoteAPI:
    def setup_method(self):
        """Set up the database state for all tests in this class."""
        self.client = APIClient()
        self.url = "/api/v2/quotes/compute/"

        # --- Create necessary objects for a valid request ---
        self.pg_currency = Currency.objects.create(code='PGK')
        country_pg = Country.objects.create(code='PG', name='Papua New Guinea')
        city_pom = City.objects.create(country=country_pg, name='Port Moresby')

        self.bill_to_company = Company.objects.create(name='Test Importer Inc.')
        self.shipper_company = Company.objects.create(name='Test Exporter Co.')

        print(f"Bill To ID: {self.bill_to_company.id}")
        print(f"Shipper ID: {self.shipper_company.id}")

        Policy.objects.create(
            name="Test API Policy",
            caf_import_pct=Decimal("0.05"),
            margin_pct=Decimal("0.15"),
            effective_from=timezone.now()
        )

        FxSnapshot.objects.create(
            as_of_timestamp=timezone.now(),
            source="TestBSP",
            rates={"AUD": {"tt_buy": "2.50", "tt_sell": "2.60"}}
        )

        LocalTariff.objects.create(
            country=country_pg,
            charge_code='CARTAGE',
            description='PNG Destination Cartage',
            basis=LocalTariff.Basis.FORMULA,
            currency=self.pg_currency,
            gst_rate=Decimal("0.10")
        )

    def test_create_quote_api_success(self):
        """
        Tests a successful quote creation through the API endpoint.
        """
        # --- Define the API request payload ---
        payload = {
            "scenario": Quote.Scenario.IMP_D2D_COLLECT,
            "chargeable_kg": "120.00",
            "bill_to_id": str(self.bill_to_company.id),
            "shipper_id": str(self.shipper_company.id),
            "consignee_id": str(self.bill_to_company.id),
            "buy_lines": [
                {"currency": "AUD", "amount": "1000.00", "description": "Freight"}
            ]
        }

        # --- Make the POST request to our endpoint ---
        response = self.client.post(self.url, payload, format='json')
        print(response.json())

        # --- Assert the response ---
        assert response.status_code == status.HTTP_201_CREATED
        
        response_data = response.json()
        assert 'id' in response_data
        assert response_data['scenario'] == Quote.Scenario.IMP_D2D_COLLECT
        
        # --- Verify key calculation in the response ---
        # Expected calculation:
        # Buy: 1000 AUD * (2.50 * 1.05 CAF) = 2625.00 PGK
        # Sell: 2625.00 * 1.15 Margin = 3018.75 PGK
        # Cartage: 1.50 * 120 = 180.00 PGK
        # Cartage GST: 180.00 * 0.10 = 18.00 PGK
        # Grand Total: 3018.75 + 180.00 + 18.00 = 3216.75 PGK
        
        totals = response_data['totals']
        assert Decimal(totals['grand_total_pgk']) == Decimal("3216.75")
        assert Decimal(totals['gst_total_pgk']) == Decimal("18.00")
        assert len(response_data['lines']) == 2 # 1 origin line, 1 destination line

    def test_create_quote_api_bad_request(self):
        """
        Tests that the API returns a 400 Bad Request for invalid data.
        """
        # --- Define an invalid payload (missing chargeable_kg) ---
        payload = {
            "scenario": Quote.Scenario.IMP_D2D_COLLECT,
            # "chargeable_kg": "120.00", # Missing
            "bill_to_id": str(self.bill_to_company.id),
            "shipper_id": str(self.shipper_company.id),
            "consignee_id": str(self.bill_to_company.id)
        }

        response = self.client.post(self.url, payload, format='json')

        # --- Assert the response ---
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'chargeable_kg' in response.json() # Check for the specific error