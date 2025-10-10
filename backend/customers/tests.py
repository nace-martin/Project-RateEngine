from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase, APIClient

from customers.models import Customer, Address

User = get_user_model()

class CustomerAPITests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username='testuser', password='testpassword')
        self.client.force_authenticate(user=self.user)

        self.address1 = Address.objects.create(
            address_line_1='123 Main St', city='Anytown', state_province='AS',
            postcode='12345', country='USA'
        )
        self.customer1 = Customer.objects.create(
            company_name='Test Company 1',
            contact_person_name='John Doe',
            contact_person_email='john@example.com',
            audience_type='LOCAL_PNG_CUSTOMER',
            primary_address=self.address1
        )

        self.address2 = Address.objects.create(
            address_line_1='456 Oak Ave', city='Otherville', state_province='OS',
            postcode='67890', country='CAN'
        )
        self.customer2 = Customer.objects.create(
            company_name='Test Company 2',
            contact_person_name='Jane Smith',
            contact_person_email='jane@example.com',
            audience_type='OVERSEAS_PARTNER_AU',
            primary_address=self.address2
        )

        self.list_url = reverse('customer-list')
        self.detail_url = lambda pk: reverse('customer-detail', kwargs={'pk': pk})

    def test_list_customers(self):
        """
        Ensure we can list all customer objects.
        """
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)
        self.assertEqual(response.data[0]['company_name'], self.customer1.company_name)
        self.assertEqual(response.data[1]['company_name'], self.customer2.company_name)

    def test_create_customer(self):
        """
        Ensure we can create a new customer object without a nested address.
        """
        data = {
            'company_name': 'New Company',
            'contact_person_name': 'Alice Brown',
            'contact_person_email': 'alice@example.com',
            'audience_type': 'LOCAL_PNG_CUSTOMER',
        }
        response = self.client.post(self.list_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Customer.objects.count(), 3)
        self.assertEqual(response.data['company_name'], 'New Company')
        self.assertIsNone(response.data['primary_address']) # No address provided

    def test_retrieve_customer(self):
        """
        Ensure we can retrieve a single customer object.
        """
        response = self.client.get(self.detail_url(self.customer1.pk))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['company_name'], self.customer1.company_name)
        self.assertEqual(response.data['primary_address']['city'], self.address1.city)

    def test_update_customer(self):
        """
        Ensure we can update an existing customer object.
        """
        updated_data = {
            'company_name': 'Updated Company 1',
            'contact_person_email': 'john.doe@newemail.com',
        }
        response = self.client.patch(self.detail_url(self.customer1.pk), updated_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.customer1.refresh_from_db()
        self.assertEqual(self.customer1.company_name, 'Updated Company 1')
        self.assertEqual(self.customer1.contact_person_email, 'john.doe@newemail.com')
        self.assertEqual(response.data['company_name'], 'Updated Company 1')

    def test_delete_customer(self):
        """
        Ensure we can delete a customer object.
        """
        response = self.client.delete(self.detail_url(self.customer1.pk))
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(Customer.objects.count(), 1)
        self.assertFalse(Customer.objects.filter(pk=self.customer1.pk).exists())

    def test_create_customer_with_nested_address(self):
        """
        Ensure we can create a new customer with a nested primary_address.
        """
        data = {
            'company_name': 'Company with Address',
            'contact_person_name': 'Bob Builder',
            'contact_person_email': 'bob@example.com',
            'audience_type': 'OVERSEAS_PARTNER_NON_AU',
            'primary_address': {
                'address_line_1': '789 Pine St',
                'city': 'Villagetown',
                'state_province': 'VT',
                'postcode': '54321',
                'country': 'GBR'
            }
        }
        response = self.client.post(self.list_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Customer.objects.count(), 3)
        new_customer = Customer.objects.get(company_name='Company with Address')
        self.assertIsNotNone(new_customer.primary_address)
        self.assertEqual(new_customer.primary_address.city, 'Villagetown')
        self.assertEqual(response.data['primary_address']['country'], 'GBR')

    def test_update_customer_with_nested_address(self):
        """
        Ensure we can update a customer's primary_address using nested data.
        """
        updated_address_data = {
            'address_line_1': '321 New Road',
            'city': 'New City',
            'country': 'FRA'
        }
        data = {
            'company_name': 'Customer 1 New Name',
            'primary_address': updated_address_data
        }
        response = self.client.patch(self.detail_url(self.customer1.pk), data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.customer1.refresh_from_db()
        self.address1.refresh_from_db() # Refresh the address object as well

        self.assertEqual(self.customer1.company_name, 'Customer 1 New Name')
        self.assertEqual(self.customer1.primary_address.address_line_1, '321 New Road')
        self.assertEqual(self.customer1.primary_address.city, 'New City')
        self.assertEqual(self.customer1.primary_address.country, 'FRA')
        self.assertEqual(response.data['primary_address']['country'], 'FRA')

    def test_update_customer_with_null_address(self):
        """
        Ensure we can update a customer to have a null primary_address.
        """
        data = {
            'primary_address': None
        }
        response = self.client.patch(self.detail_url(self.customer1.pk), data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.customer1.refresh_from_db()
        self.assertIsNone(self.customer1.primary_address)
        self.assertIsNone(response.data['primary_address'])

    def test_unauthenticated_access(self):
        """
        Ensure unauthenticated requests are rejected.
        """
        self.client.logout() # Log out the authenticated user
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        response = self.client.post(self.list_url, {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)