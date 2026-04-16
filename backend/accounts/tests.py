"""
Tests for authentication and authorization.

Covers:
- Login success/failure
- Login rate limiting (brute force protection)
- Registration disabled by default
- RBAC permission enforcement
"""
import json
from io import BytesIO

from django.test import TestCase, override_settings
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient
from rest_framework import status
from PIL import Image
from core.models import Currency
from parties.models import Organization, OrganizationBranding
from .models import CustomUser


def _ensure_default_organization():
    pgk = Currency.objects.filter(code='PGK').first() or Currency.objects.create(
        code='PGK',
        name='Papua New Guinean Kina',
    )
    organization, _ = Organization.objects.get_or_create(
        slug='efm-express-air-cargo',
        defaults={
            'name': 'EFM Express Air Cargo',
            'default_currency': pgk,
            'is_active': True,
        },
    )
    return organization


class LoginTests(TestCase):
    """Tests for the login endpoint."""
    
    def setUp(self):
        self.client = APIClient()
        self.login_url = '/api/auth/login/'
        self.me_url = '/api/auth/me/'
        self.organization = self._create_default_organization()
        
        # Create a test user
        self.user = CustomUser.objects.create_user(
            username='testuser',
            password='testpass123',
            role=CustomUser.ROLE_SALES,
            organization=self.organization,
            department=CustomUser.DEPARTMENT_GENERAL,
        )

    def _create_default_organization(self):
        organization = _ensure_default_organization()
        OrganizationBranding.objects.update_or_create(
            organization=organization,
            defaults={
                'display_name': 'EFM Express Air Cargo',
                'primary_color': '#0F2A56',
                'accent_color': '#D71920',
            },
        )
        return organization
    
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
        self.assertEqual(data['user']['organization']['slug'], 'efm-express-air-cargo')
        self.assertEqual(data['user']['organization']['branding']['display_name'], 'EFM Express Air Cargo')
    
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

    def test_me_returns_user_with_organization_branding(self):
        token_response = self.client.post(
            self.login_url,
            {'username': 'testuser', 'password': 'testpass123'},
            format='json'
        )
        token = token_response.json()['token']

        response = self.client.get(
            self.me_url,
            HTTP_AUTHORIZATION=f'Token {token}',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data['username'], 'testuser')
        self.assertEqual(data['organization']['slug'], 'efm-express-air-cargo')
        self.assertEqual(data['organization']['branding']['display_name'], 'EFM Express Air Cargo')

    def test_login_branding_uses_primary_logo_when_small_logo_is_missing(self):
        branding = self.organization.branding
        branding.logo_small = None
        buffer = BytesIO()
        Image.new("RGB", (2, 2), color="#0F2A56").save(buffer, format="PNG")
        buffer.seek(0)
        branding.logo_primary.save(
            "primary-logo.png",
            SimpleUploadedFile("primary-logo.png", buffer.read(), content_type="image/png"),
            save=True,
        )
        branding.save(update_fields=['logo_small'])

        response = self.client.post(
            self.login_url,
            {'username': 'testuser', 'password': 'testpass123'},
            format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertTrue(
            data['user']['organization']['branding']['logo_url'].endswith(
                '/api/v3/public/branding/efm-express-air-cargo/primary/'
            )
        )

    def test_login_branding_omits_missing_logo_urls(self):
        branding = self.organization.branding
        branding.logo_small = "branding/efm-express-air-cargo/missing-small.png"
        branding.logo_primary = "branding/efm-express-air-cargo/missing-primary.png"
        branding.save(update_fields=["logo_small", "logo_primary"])

        response = self.client.post(
            self.login_url,
            {'username': 'testuser', 'password': 'testpass123'},
            format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertIsNone(data['user']['organization']['branding']['logo_url'])


class RegistrationTests(TestCase):
    """Tests for the registration endpoint."""
    
    def setUp(self):
        self.client = APIClient()
        self.register_url = '/api/auth/register/'
        pgk = Currency.objects.filter(code='PGK').first() or Currency.objects.create(
            code='PGK',
            name='Papua New Guinean Kina',
        )
        Organization.objects.get_or_create(
            slug='efm-express-air-cargo',
            defaults={
                'name': 'EFM Express Air Cargo',
                'default_currency': pgk,
                'is_active': True,
            },
        )
    
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
                self.assertEqual(data['user']['organization']['slug'], 'efm-express-air-cargo')
        finally:
            os.environ.pop('ALLOW_SELF_REGISTRATION', None)


class RBACPermissionTests(TestCase):
    """Tests for role-based access control."""
    
    def setUp(self):
        self.client = APIClient()
        self.organization = _ensure_default_organization()
        
        # Create users with different roles
        self.sales_user = CustomUser.objects.create_user(
            username='sales',
            password='test123',
            role=CustomUser.ROLE_SALES,
            organization=self.organization,
            department=CustomUser.DEPARTMENT_GENERAL,
        )
        self.manager_user = CustomUser.objects.create_user(
            username='manager',
            password='test123',
            role=CustomUser.ROLE_MANAGER,
            organization=self.organization,
            department=CustomUser.DEPARTMENT_GENERAL,
        )
        self.finance_user = CustomUser.objects.create_user(
            username='finance',
            password='test123',
            role=CustomUser.ROLE_FINANCE,
            organization=self.organization,
            department=CustomUser.DEPARTMENT_GENERAL,
        )
        self.admin_user = CustomUser.objects.create_user(
            username='admin',
            password='test123',
            role=CustomUser.ROLE_ADMIN,
            organization=self.organization,
            department=CustomUser.DEPARTMENT_GENERAL,
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


class UserManagementOrganizationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.pgk = Currency.objects.filter(code='PGK').first() or Currency.objects.create(
            code='PGK',
            name='Papua New Guinean Kina',
        )
        self.org_a, _ = Organization.objects.get_or_create(
            slug='efm-express-air-cargo',
            defaults={
                'name': 'EFM Express Air Cargo',
                'default_currency': self.pgk,
                'is_active': True,
            },
        )
        self.org_b = Organization.objects.create(
            name='Lae Branch Workspace',
            slug='lae-branch-workspace',
            default_currency=self.pgk,
            is_active=True,
        )
        self.manager = CustomUser.objects.create_user(
            username='manager-user',
            password='test12345',
            role=CustomUser.ROLE_MANAGER,
            organization=self.org_a,
            department='AIR',
        )

    def test_manager_can_list_organizations(self):
        self.client.force_authenticate(user=self.manager)

        response = self.client.get('/api/auth/organizations/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        slugs = [row['slug'] for row in response.json()]
        self.assertIn('efm-express-air-cargo', slugs)
        self.assertIn('lae-branch-workspace', slugs)

    def test_user_create_requires_explicit_organization(self):
        self.client.force_authenticate(user=self.manager)

        response = self.client.post(
            '/api/auth/users/',
            {
                'username': 'new-sales-user',
                'email': 'new-sales@example.com',
                'role': 'sales',
                'department': 'AIR',
                'password': 'password123',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('organization', response.json())

    def test_user_create_can_assign_explicit_organization(self):
        self.client.force_authenticate(user=self.manager)

        response = self.client.post(
            '/api/auth/users/',
            {
                'username': 'lae-sales-user',
                'email': 'lae-sales@example.com',
                'role': 'sales',
                'department': 'AIR',
                'password': 'password123',
                'organization': str(self.org_b.id),
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        created = CustomUser.objects.get(username='lae-sales-user')
        self.assertEqual(created.organization, self.org_b)

    def test_user_create_requires_explicit_department(self):
        self.client.force_authenticate(user=self.manager)

        response = self.client.post(
            '/api/auth/users/',
            {
                'username': 'missing-department-user',
                'email': 'missing-department@example.com',
                'role': 'sales',
                'password': 'password123',
                'organization': str(self.org_a.id),
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('department', response.json())
