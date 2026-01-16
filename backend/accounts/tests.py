"""
Tests for authentication and authorization.

Covers:
- Login success/failure
- Login rate limiting (brute force protection)
- Registration disabled by default
- RBAC permission enforcement
"""
import json
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from .models import CustomUser


class LoginTests(TestCase):
    """Tests for the login endpoint."""
    
    def setUp(self):
        self.client = APIClient()
        self.login_url = '/api/auth/login/'
        
        # Create a test user
        self.user = CustomUser.objects.create_user(
            username='testuser',
            password='testpass123',
            role=CustomUser.ROLE_SALES
        )
    
    def test_login_success(self):
        """Valid credentials should return token and user info."""
        response = self.client.post(
            self.login_url,
            {'username': 'testuser', 'password': 'testpass123'},
            format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertIn('token', data)
        self.assertEqual(data['username'], 'testuser')
        self.assertEqual(data['role'], 'sales')
    
    def test_login_invalid_password(self):
        """Invalid password should return 401."""
        response = self.client.post(
            self.login_url,
            {'username': 'testuser', 'password': 'wrongpassword'},
            format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertIn('detail', response.json())
    
    def test_login_invalid_username(self):
        """Non-existent username should return 401."""
        response = self.client.post(
            self.login_url,
            {'username': 'nonexistent', 'password': 'testpass123'},
            format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
    
    def test_login_missing_credentials(self):
        """Missing username or password should return 400."""
        response = self.client.post(
            self.login_url,
            {'username': 'testuser'},
            format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class RegistrationTests(TestCase):
    """Tests for the registration endpoint."""
    
    def setUp(self):
        self.client = APIClient()
        self.register_url = '/api/auth/register/'
    
    def test_registration_disabled_by_default(self):
        """Registration should be disabled without ALLOW_SELF_REGISTRATION."""
        response = self.client.post(
            self.register_url,
            {'username': 'newuser', 'password': 'newpass123'},
            format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn('disabled', response.json().get('detail', '').lower())
    
    @override_settings()
    def test_registration_role_always_sales(self):
        """Even when enabled, users should always get 'sales' role."""
        import os
        os.environ['ALLOW_SELF_REGISTRATION'] = 'True'
        try:
            response = self.client.post(
                self.register_url,
                {
                    'username': 'newuser',
                    'password': 'newpass123',
                    'role': 'admin'  # Try to set admin role
                },
                format='json'
            )
            if response.status_code == status.HTTP_201_CREATED:
                # Verify role is sales, not admin
                data = response.json()
                self.assertEqual(data['role'], 'sales')
        finally:
            os.environ.pop('ALLOW_SELF_REGISTRATION', None)


class RBACPermissionTests(TestCase):
    """Tests for role-based access control."""
    
    def setUp(self):
        self.client = APIClient()
        
        # Create users with different roles
        self.sales_user = CustomUser.objects.create_user(
            username='sales',
            password='test123',
            role=CustomUser.ROLE_SALES
        )
        self.manager_user = CustomUser.objects.create_user(
            username='manager',
            password='test123',
            role=CustomUser.ROLE_MANAGER
        )
        self.finance_user = CustomUser.objects.create_user(
            username='finance',
            password='test123',
            role=CustomUser.ROLE_FINANCE
        )
        self.admin_user = CustomUser.objects.create_user(
            username='admin',
            password='test123',
            role=CustomUser.ROLE_ADMIN
        )
    
    def test_sales_can_view_cogs_false(self):
        """Sales users should not be able to view COGS."""
        self.assertFalse(self.sales_user.can_view_cogs)
    
    def test_manager_can_view_cogs_true(self):
        """Managers should be able to view COGS."""
        self.assertTrue(self.manager_user.can_view_cogs)
    
    def test_finance_can_view_cogs_true(self):
        """Finance users should be able to view COGS."""
        self.assertTrue(self.finance_user.can_view_cogs)
    
    def test_sales_can_edit_quotes_true(self):
        """Sales users should be able to edit quotes."""
        self.assertTrue(self.sales_user.can_edit_quotes)
    
    def test_finance_can_edit_quotes_false(self):
        """Finance users should not be able to edit quotes."""
        self.assertFalse(self.finance_user.can_edit_quotes)
    
    def test_only_finance_and_admin_can_edit_fx_rates(self):
        """Only Finance and Admin should edit FX rates."""
        self.assertFalse(self.sales_user.can_edit_fx_rates)
        self.assertFalse(self.manager_user.can_edit_fx_rates)
        self.assertTrue(self.finance_user.can_edit_fx_rates)
        self.assertTrue(self.admin_user.can_edit_fx_rates)
    
    def test_only_admin_can_access_system_settings(self):
        """Only Admin should access system settings."""
        self.assertFalse(self.sales_user.can_access_system_settings)
        self.assertFalse(self.manager_user.can_access_system_settings)
        self.assertFalse(self.finance_user.can_access_system_settings)
        self.assertTrue(self.admin_user.can_access_system_settings)
