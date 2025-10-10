from django.test import TestCase
from django.urls import reverse, NoReverseMatch
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status
import datetime

from quotes.models import Quotation
from customers.models import Customer
from core.models import Station

User = get_user_model()

class ComputeV2APITest(TestCase):
    def setUp(self):
        # Adjust these kwargs if your CustomUser uses different field names
        self.sales_user = User.objects.create_user(username='sales', password='password', role='sales')
        self.manager_user = User.objects.create_user(username='manager', password='password', role='manager')

        self.sales_client = APIClient()
        self.manager_client = APIClient()
        self.sales_client.force_authenticate(self.sales_user)
        self.manager_client.force_authenticate(self.manager_user)

        # Create a customer
        self.customer = Customer.objects.create(company_name='Test Customer')

        # Create stations
        self.origin = Station.objects.create(iata_code='LAE', city='Lae', country_code='PG')
        self.destination = Station.objects.create(iata_code='POM', city='Port Moresby', country_code='PG')

        # Create a quotation
        self.quotation = Quotation.objects.create(
            reference='TEST-001',
            customer=self.customer,
            date=datetime.date.today(),
            service_type='EXPORT',
            terms='FOB',
            scope='A2A',
            payment_term='PREPAID'
        )
        self.quote_id = self.quotation.pk

        # Resolve URL once and fail loudly if route is missing
        try:
            self.url = reverse('quote-version-create', kwargs={'id': self.quote_id})
        except NoReverseMatch as e:
            self.fail(f"URL name 'quote-version-create' not found: {e}")

    def test_sales_cannot_create_version(self):
        data = {
            "origin": self.origin.pk,
            "destination": self.destination.pk,
            "volumetric_weight_kg": 10.0,
            "chargeable_weight_kg": 10.0,
            "sell_currency": "PGK",
            "valid_from": datetime.date.today().isoformat(),
            "valid_to": (datetime.date.today() + datetime.timedelta(days=30)).isoformat(),
            "pieces": []
        }
        res = self.sales_client.post(self.url, data, format='json')
        # Expect 403 if RBAC blocks sales; change to 200/201 if your policy differs
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN, res.content)

    def test_manager_can_create_version(self):
        data = {
            "origin": self.origin.pk,
            "destination": self.destination.pk,
            "volumetric_weight_kg": 10.0,
            "chargeable_weight_kg": 10.0,
            "sell_currency": "PGK",
            "valid_from": datetime.date.today().isoformat(),
            "valid_to": (datetime.date.today() + datetime.timedelta(days=30)).isoformat(),
            "pieces": []
        }
        res = self.manager_client.post(self.url, data, format='json')
        self.assertIn(res.status_code, {status.HTTP_200_OK, status.HTTP_201_CREATED}, res.content)
