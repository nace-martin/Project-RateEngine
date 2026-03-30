
import pytest
from datetime import timedelta
from rest_framework import status
from rest_framework.test import APIClient
from quotes.models import Quote, QuoteVersion, QuoteTotal
from django.contrib.auth import get_user_model
from django.utils import timezone
from decimal import Decimal
from itertools import count

from core.tests.helpers import create_location

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

    company = Company.objects.create(name="Test Co", company_type="CUSTOMER")
    location = create_location(code="POM", name="Port Moresby")
    quote_numbers = count(1)

    def create_quote(user, status, total_pgk, customer=None, created_at=None, updated_at=None, finalized_at=None):
        quote = Quote.objects.create(
            quote_number=f"QT-{next(quote_numbers)}",
            created_by=user,
            status=status,
            customer=customer or company,
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
        update_fields = {}
        if created_at is not None:
            update_fields['created_at'] = created_at
        if updated_at is not None:
            update_fields['updated_at'] = updated_at
        if finalized_at is not None:
            update_fields['finalized_at'] = finalized_at
        if update_fields:
            Quote.objects.filter(pk=quote.pk).update(**update_fields)
            quote.refresh_from_db()
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

    def test_dashboard_metrics_default_monthly(self, api_client, manager_user, quote_factory):
        """Test dashboard_metrics returns correct data for default monthly timeframe."""
        api_client.force_authenticate(user=manager_user)
        
        # Create test data
        quote_factory(manager_user, Quote.Status.DRAFT, 1000)
        quote_factory(manager_user, Quote.Status.FINALIZED, 2000)
        quote_factory(manager_user, Quote.Status.ACCEPTED, 3000)
        
        url = '/api/v3/reports/dashboard_metrics/'
        response = api_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        assert data['timeframe'] == 'monthly'
        assert 'pipeline_count' in data
        assert 'finalized_count' in data
        assert 'win_rate_percent' in data
        assert 'avg_quote_value' in data
        assert 'lost_opportunity_value' in data
        assert 'weekly_activity' in data
        assert data['activity_label'] == 'This month'
        assert 1 <= len(data['weekly_activity']) <= 6

    def test_dashboard_metrics_weekly_timeframe(self, api_client, manager_user, quote_factory):
        """Test dashboard_metrics with weekly timeframe filter."""
        api_client.force_authenticate(user=manager_user)
        
        quote_factory(manager_user, Quote.Status.FINALIZED, 1500)
        
        url = '/api/v3/reports/dashboard_metrics/?timeframe=weekly'
        response = api_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        assert data['timeframe'] == 'weekly'

    def test_dashboard_metrics_ytd_timeframe(self, api_client, manager_user, quote_factory):
        """Test dashboard_metrics with YTD timeframe filter."""
        api_client.force_authenticate(user=manager_user)
        
        quote_factory(manager_user, Quote.Status.ACCEPTED, 5000)
        
        url = '/api/v3/reports/dashboard_metrics/?timeframe=ytd'
        response = api_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        assert data['timeframe'] == 'ytd'
        assert data['quotes_accepted'] >= 1

    def test_dashboard_metrics_win_rate_calculation(self, api_client, manager_user, quote_factory):
        """Test win rate is calculated as ACCEPTED / (SENT + ACCEPTED + LOST) * 100."""
        api_client.force_authenticate(user=manager_user)
        
        # Create 2 ACCEPTED, 1 LOST = 2/3 = 66.7% win rate
        quote_factory(manager_user, Quote.Status.ACCEPTED, 1000)
        quote_factory(manager_user, Quote.Status.ACCEPTED, 2000)
        quote_factory(manager_user, Quote.Status.LOST, 500)
        
        url = '/api/v3/reports/dashboard_metrics/'
        response = api_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        assert data['total_quotes_sent'] == 3
        assert data['quotes_accepted'] == 2
        assert data['quotes_lost'] == 1
        # 2/3 * 100 = 66.67, rounded to 66.7
        assert data['win_rate_percent'] == 66.7

    def test_dashboard_metrics_lost_opportunity(self, api_client, manager_user, quote_factory):
        """Test lost opportunity sums LOST and EXPIRED quote values."""
        api_client.force_authenticate(user=manager_user)
        
        quote_factory(manager_user, Quote.Status.LOST, 1000)
        quote_factory(manager_user, Quote.Status.EXPIRED, 2000)
        quote_factory(manager_user, Quote.Status.FINALIZED, 5000)  # Should not be included
        
        url = '/api/v3/reports/dashboard_metrics/'
        response = api_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        # Lost (1000) + Expired (2000) = 3000 + GST
        assert data['lost_opportunity_value'] >= 3000.0

    def test_dashboard_metrics_counts_finalized_and_accepted_by_lifecycle_date(self, api_client, manager_user, quote_factory):
        api_client.force_authenticate(user=manager_user)

        now = timezone.now()
        old_created = now - timedelta(days=45)

        quote_factory(
            manager_user,
            Quote.Status.FINALIZED,
            1000,
            created_at=old_created,
            finalized_at=now,
            updated_at=now,
        )
        quote_factory(
            manager_user,
            Quote.Status.ACCEPTED,
            2000,
            created_at=old_created,
            updated_at=now,
        )

        response = api_client.get('/api/v3/reports/dashboard_metrics/')

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data['finalized_count'] == 2
        assert data['finalized_value'] == 3300.0

    def test_dashboard_metrics_monthly_activity_is_weekly_buckets(self, api_client, manager_user, quote_factory):
        api_client.force_authenticate(user=manager_user)

        today = timezone.now()
        for days_ago in [0, 2, 8, 10]:
            quote_factory(
                manager_user,
                Quote.Status.DRAFT,
                500,
                created_at=today - timedelta(days=days_ago),
                updated_at=today - timedelta(days=days_ago),
            )

        response = api_client.get('/api/v3/reports/dashboard_metrics/?timeframe=monthly')

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data['activity_label'] == 'This month'
        assert 1 <= len(data['weekly_activity']) <= 6
        assert all(entry['day'].startswith('W') for entry in data['weekly_activity'])

    def test_tier1_customer_stats_returns_top_customers_by_revenue(self, api_client, manager_user):
        api_client.force_authenticate(user=manager_user)

        from parties.models import Company

        location = create_location(code="LAE", name="Lae")
        customer_a = Company.objects.create(name="Customer A", company_type="CUSTOMER")
        customer_b = Company.objects.create(name="Customer B", company_type="CUSTOMER")

        def build_quote(customer, amount, status):
            quote = Quote.objects.create(
                quote_number=f"QT-CUST-{customer.name}-{amount}",
                created_by=manager_user,
                status=status,
                customer=customer,
                origin_location=location,
                destination_location=location,
                mode='AIR',
                shipment_type='EXPORT',
                finalized_at=timezone.now(),
            )
            version = QuoteVersion.objects.create(quote=quote, version_number=1, status=status)
            QuoteTotal.objects.create(
                quote_version=version,
                total_sell_pgk=Decimal(amount),
                total_sell_pgk_incl_gst=Decimal(amount) * Decimal('1.1')
            )
            return quote

        build_quote(customer_a, '5000', Quote.Status.FINALIZED)
        build_quote(customer_b, '2000', Quote.Status.ACCEPTED)

        response = api_client.get('/api/v3/reports/tier1_customer_stats/')

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert 'dormant_customers' not in data
        assert data['top_customers'][0]['name'] == 'Customer A'
        assert data['top_customers'][0]['value'] == 5500.0

    def test_dashboard_metrics_access_denied_for_sales(self, api_client, sales_user):
        """Test that sales users cannot access dashboard_metrics."""
        api_client.force_authenticate(user=sales_user)
        
        url = '/api/v3/reports/dashboard_metrics/'
        response = api_client.get(url)
        
        assert response.status_code == status.HTTP_403_FORBIDDEN
