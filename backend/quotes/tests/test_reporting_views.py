
import pytest
from rest_framework import status
from rest_framework.test import APIClient
from quotes.models import Quote, QuoteVersion, QuoteTotal
from django.contrib.auth import get_user_model
from decimal import Decimal
from itertools import count

@pytest.fixture
def api_client():
    return APIClient()

@pytest.fixture
def manager_user(db):
    user = get_user_model().objects.create_user(
        username='manager',
        password='password',
        role='manager'
    )
    return user

@pytest.fixture
def sales_user(db):
    user = get_user_model().objects.create_user(
        username='sales',
        password='password',
        role='sales'
    )
    return user

@pytest.fixture
def quote_factory(db):
    from parties.models import Company
    from core.models import Location

    company = Company.objects.create(name="Test Co", company_type="CUSTOMER")
    location = Location.objects.create(code="POM", name="Port Moresby")
    quote_numbers = count(1)

    def create_quote(user, status, total_pgk):
        quote = Quote.objects.create(
            quote_number=f"QT-{next(quote_numbers)}",
            created_by=user,
            status=status,
            customer=company,
            origin_location=location,
            destination_location=location,
            mode='AIR',
            shipment_type='IMPORT'
        )
        version = QuoteVersion.objects.create(quote=quote, version_number=1, status=status)
        QuoteTotal.objects.create(
            quote_version=version,
            total_sell_pgk=Decimal(total_pgk),
            total_sell_pgk_incl_gst=Decimal(total_pgk) * Decimal('1.1')
        )
        return quote
    return create_quote

@pytest.mark.django_db
class TestReportsViewSet:
    
    def test_dashboard_access_denied_for_sales(self, api_client, sales_user):
        api_client.force_authenticate(user=sales_user)
        url = '/api/v3/reports/dashboard/'
        response = api_client.get(url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_dashboard_metrics(self, api_client, manager_user, quote_factory):
        api_client.force_authenticate(user=manager_user)

        # Create some data
        quote_factory(manager_user, Quote.Status.FINALIZED, 1000)
        quote_factory(manager_user, Quote.Status.DRAFT, 500)
        quote_factory(manager_user, Quote.Status.LOST, 200)
        
        url = '/api/v3/reports/dashboard/'
        response = api_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        assert data['total_revenue'] == 1000.0  # Only Finalized count
        assert data['conversion']['total'] == 3
        assert data['conversion']['drafts'] == 1
        assert data['conversion']['finalized'] == 1
        assert data['conversion']['lost'] == 1

    def test_dashboard_uses_latest_version_total(self, api_client, manager_user, quote_factory):
        api_client.force_authenticate(user=manager_user)

        quote = quote_factory(manager_user, Quote.Status.FINALIZED, 1000)
        version = QuoteVersion.objects.create(
            quote=quote,
            version_number=2,
            status=Quote.Status.FINALIZED
        )
        QuoteTotal.objects.create(
            quote_version=version,
            total_sell_pgk=Decimal('1500'),
            total_sell_pgk_incl_gst=Decimal('1650')
        )

        url = '/api/v3/reports/dashboard/'
        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert data['total_revenue'] == 1500.0
        mode_entry = next((item for item in data['volume_by_mode'] if item['mode'] == 'AIR'), None)
        assert mode_entry is not None
        assert mode_entry['revenue'] == 1500.0

    def test_sales_performance(self, api_client, manager_user, sales_user, quote_factory):
        api_client.force_authenticate(user=manager_user)
        
        quote_factory(sales_user, Quote.Status.FINALIZED, 2000)
        quote_factory(sales_user, Quote.Status.DRAFT, 1000)
        
        url = '/api/v3/reports/sales_performance/'
        response = api_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        # Find the sales user entry
        sales_entry = next((item for item in data if item['created_by__username'] == 'sales'), None)
        assert sales_entry is not None
        assert sales_entry['total_quotes'] == 2
        assert sales_entry['total_revenue'] == 2000.0
        assert sales_entry['converted_quotes'] == 1
