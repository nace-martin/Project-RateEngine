# backend/quotes/tests/test_departmental_access.py
"""
Departmental Visibility Tests

Tests the RBAC departmental visibility rules:
1. Admin/Finance see all quotes
2. Manager sees only quotes from their department
3. Sales sees only their own quotes
"""
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status as http_status

from accounts.models import CustomUser
from quotes.models import Quote
from parties.models import Company


class DepartmentalVisibilityTestCase(TestCase):
    """Tests for departmental visibility filtering on quote list."""
    
    @classmethod
    def setUpTestData(cls):
        """Create test users and quotes."""
        # Create customer company
        cls.customer = Company.objects.create(
            name='Test Customer',
            is_customer=True
        )
        
        # Create users with different roles and departments
        cls.admin_user = CustomUser.objects.create_user(
            username='admin_user',
            password='testpass123',
            role=CustomUser.ROLE_ADMIN,
            department=None  # Admin has no department, sees all
        )
        cls.finance_user = CustomUser.objects.create_user(
            username='finance_user',
            password='testpass123',
            role=CustomUser.ROLE_FINANCE,
            department=None  # Finance sees all
        )
        cls.air_manager = CustomUser.objects.create_user(
            username='air_manager',
            password='testpass123',
            role=CustomUser.ROLE_MANAGER,
            department='AIR'
        )
        cls.sea_manager = CustomUser.objects.create_user(
            username='sea_manager',
            password='testpass123',
            role=CustomUser.ROLE_MANAGER,
            department='SEA'
        )
        cls.air_sales = CustomUser.objects.create_user(
            username='air_sales',
            password='testpass123',
            role=CustomUser.ROLE_SALES,
            department='AIR'
        )
        cls.sea_sales = CustomUser.objects.create_user(
            username='sea_sales',
            password='testpass123',
            role=CustomUser.ROLE_SALES,
            department='SEA'
        )
        
        # Create quotes by different users
        cls.quote_by_air_sales = Quote.objects.create(
            customer=cls.customer,
            mode='AIR',
            status=Quote.Status.DRAFT,
            created_by=cls.air_sales
        )
        cls.quote_by_sea_sales = Quote.objects.create(
            customer=cls.customer,
            mode='AIR',  # Mode is different from department!
            status=Quote.Status.DRAFT,
            created_by=cls.sea_sales
        )
        cls.quote_by_air_manager = Quote.objects.create(
            customer=cls.customer,
            mode='AIR',
            status=Quote.Status.DRAFT,
            created_by=cls.air_manager
        )


class AdminVisibilityTest(DepartmentalVisibilityTestCase):
    """Test Admin can see all quotes."""
    
    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin_user)
    
    def test_admin_sees_all_quotes(self):
        """Admin should see all quotes regardless of department."""
        response = self.client.get('/api/v3/quotes/')
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        
        data = response.json()
        quote_ids = [q['id'] for q in data['results']]
        
        # Should see all 3 quotes
        self.assertEqual(len(quote_ids), 3)
        self.assertIn(str(self.quote_by_air_sales.id), quote_ids)
        self.assertIn(str(self.quote_by_sea_sales.id), quote_ids)
        self.assertIn(str(self.quote_by_air_manager.id), quote_ids)


class FinanceVisibilityTest(DepartmentalVisibilityTestCase):
    """Test Finance can see all quotes."""
    
    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.finance_user)
    
    def test_finance_sees_all_quotes(self):
        """Finance should see all quotes regardless of department."""
        response = self.client.get('/api/v3/quotes/')
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        
        data = response.json()
        # Should see all 3 quotes
        self.assertEqual(len(data['results']), 3)


class ManagerVisibilityTest(DepartmentalVisibilityTestCase):
    """Test Manager sees only quotes from their department."""
    
    def test_air_manager_sees_air_department_quotes(self):
        """Air Manager should see quotes created by Air department users."""
        client = APIClient()
        client.force_authenticate(user=self.air_manager)
        
        response = client.get('/api/v3/quotes/')
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        
        data = response.json()
        quote_ids = [q['id'] for q in data['results']]
        
        # Air Manager sees: quotes by air_sales + own quotes
        self.assertIn(str(self.quote_by_air_sales.id), quote_ids)
        self.assertIn(str(self.quote_by_air_manager.id), quote_ids)
        # Air Manager should NOT see SEA department quotes
        self.assertNotIn(str(self.quote_by_sea_sales.id), quote_ids)
    
    def test_sea_manager_sees_sea_department_quotes(self):
        """Sea Manager should see quotes created by Sea department users."""
        client = APIClient()
        client.force_authenticate(user=self.sea_manager)
        
        response = client.get('/api/v3/quotes/')
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        
        data = response.json()
        quote_ids = [q['id'] for q in data['results']]
        
        # Sea Manager sees: quotes by sea_sales + own quotes
        self.assertIn(str(self.quote_by_sea_sales.id), quote_ids)
        # Sea Manager should NOT see AIR department quotes
        self.assertNotIn(str(self.quote_by_air_sales.id), quote_ids)


class SalesVisibilityTest(DepartmentalVisibilityTestCase):
    """Test Sales sees only their own quotes."""
    
    def test_air_sales_sees_only_own_quotes(self):
        """Air Sales should see only their own quotes."""
        client = APIClient()
        client.force_authenticate(user=self.air_sales)
        
        response = client.get('/api/v3/quotes/')
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        
        data = response.json()
        quote_ids = [q['id'] for q in data['results']]
        
        # Air Sales sees only own quote
        self.assertEqual(len(quote_ids), 1)
        self.assertIn(str(self.quote_by_air_sales.id), quote_ids)
        # Should NOT see other quotes
        self.assertNotIn(str(self.quote_by_sea_sales.id), quote_ids)
        self.assertNotIn(str(self.quote_by_air_manager.id), quote_ids)
    
    def test_sea_sales_sees_only_own_quotes(self):
        """Sea Sales should see only their own quotes."""
        client = APIClient()
        client.force_authenticate(user=self.sea_sales)
        
        response = client.get('/api/v3/quotes/')
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        
        data = response.json()
        quote_ids = [q['id'] for q in data['results']]
        
        # Sea Sales sees only own quote
        self.assertEqual(len(quote_ids), 1)
        self.assertIn(str(self.quote_by_sea_sales.id), quote_ids)


class ManagerWithNoDepartmentTest(DepartmentalVisibilityTestCase):
    """Test Manager with no department assigned."""
    
    def test_manager_no_dept_sees_only_own_quotes(self):
        """Manager without department should see only own quotes (fallback)."""
        no_dept_manager = CustomUser.objects.create_user(
            username='no_dept_manager',
            password='testpass123',
            role=CustomUser.ROLE_MANAGER,
            department=None
        )
        own_quote = Quote.objects.create(
            customer=self.customer,
            mode='AIR',
            status=Quote.Status.DRAFT,
            created_by=no_dept_manager
        )
        
        client = APIClient()
        client.force_authenticate(user=no_dept_manager)
        
        response = client.get('/api/v3/quotes/')
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        
        data = response.json()
        quote_ids = [q['id'] for q in data['results']]
        
        # Should only see own quote
        self.assertEqual(len(quote_ids), 1)
        self.assertIn(str(own_quote.id), quote_ids)
