from django.urls import reverse
from rest_framework.test import APITestCase
from django.contrib.auth.models import User, Group

class ComputeV2APITest(APITestCase):
    def setUp(self):
        self.sales_user = User.objects.create_user(username='sales', password='password')
        self.manager_user = User.objects.create_user(username='manager', password='password')

        sales_group = Group.objects.create(name='Sales')
        self.sales_user.groups.add(sales_group)

    def test_rbac_sales_user(self):
        """Verify that a sales user does not see BUY-side data."""
        self.client.login(username='sales', password='password')
        url = reverse('quote-compute-v2')
        data = {
            "shipment_pieces": [],
            "audience": "",
            "payment_term": "PREPAID",
            "origin": "",
            "destination": "",
            "spot_offers": []
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('best_buy_offer', response.data)
        self.assertNotIn('snapshot', response.data)

    def test_rbac_manager_user(self):
        """Verify that a manager user sees BUY-side data."""
        self.client.login(username='manager', password='password')
        url = reverse('quote-compute-v2')
        data = {
            "shipment_pieces": [],
            "audience": "",
            "payment_term": "PREPAID",
            "origin": "",
            "destination": "",
            "spot_offers": []
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertIn('best_buy_offer', response.data)
        self.assertIn('snapshot', response.data)
