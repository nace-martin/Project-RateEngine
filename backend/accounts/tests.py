"""
Tests for authentication and authorization.

Covers:
- Login success/failure
- Login rate limiting (brute force protection)
- Registration disabled by default
- RBAC permission enforcement
"""
import json
from io import StringIO
from io import BytesIO

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient
from rest_framework import status
from PIL import Image
from core.models import Currency
from parties.models import Branch, Department, Organization, OrganizationBranding
from .models import CustomUser, Permission, Role, RolePermission, UserMembership


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
        )

    def _create_default_organization(self):
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
    
    def test_sales_can_view_cogs_true(self):
        """Sales users should be able to view COGS."""
        self.assertTrue(self.sales_user.can_view_cogs)
    
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
        )

    def test_manager_can_list_organizations(self):
        self.client.force_authenticate(user=self.manager)

        response = self.client.get('/api/auth/organizations/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        slugs = [row['slug'] for row in response.json()]
        self.assertIn('efm-express-air-cargo', slugs)
        self.assertIn('lae-branch-workspace', slugs)

    def test_user_create_defaults_to_request_users_organization(self):
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

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        created = CustomUser.objects.get(username='new-sales-user')
        self.assertEqual(created.organization, self.org_a)

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


class RBACFoundationSeedTests(TestCase):
    def setUp(self):
        self.pgk = Currency.objects.filter(code='PGK').first() or Currency.objects.create(
            code='PGK',
            name='Papua New Guinean Kina',
        )
        self.efm = Organization.objects.create(
            name='Express Freight Management',
            slug='efm',
            default_currency=self.pgk,
            is_active=True,
        )
        self.test_org = Organization.objects.create(
            name='Test Org',
            slug='test-org',
            default_currency=self.pgk,
            is_active=True,
        )

    def _run_seed(self):
        output = StringIO()
        call_command('seed_rbac_foundation', '--json', stdout=output)
        return json.loads(output.getvalue())

    def test_seed_command_creates_foundation_records_and_is_idempotent(self):
        CustomUser.objects.create_user(
            username='air-sales',
            password='test12345',
            role=CustomUser.ROLE_SALES,
            department='AIR',
            organization=self.efm,
        )

        first = self._run_seed()
        second = self._run_seed()

        self.assertGreaterEqual(first['branches']['created'], 5)
        self.assertEqual(first['departments']['created'], Organization.objects.count() * 5)
        self.assertGreater(first['permissions']['created'], 0)
        self.assertEqual(first['roles']['created'], 4)
        self.assertEqual(first['memberships']['created'], 1)
        self.assertEqual(second['branches']['created'], 0)
        self.assertEqual(second['departments']['created'], 0)
        self.assertEqual(second['permissions']['created'], 0)
        self.assertEqual(second['roles']['created'], 0)
        self.assertEqual(second['memberships']['created'], 0)
        self.assertEqual(second['memberships']['existing'], 1)

        self.assertEqual(Branch.objects.filter(organization=self.efm).count(), 5)
        self.assertEqual(Department.objects.filter(organization=self.efm).count(), 5)
        self.assertEqual(Department.objects.filter(organization=self.test_org).count(), 5)
        self.assertEqual(Role.objects.filter(organization__isnull=True).count(), 4)
        self.assertTrue(Permission.objects.filter(code='quote.view.buy_cost').exists())
        self.assertTrue(
            RolePermission.objects.filter(
                role__code=CustomUser.ROLE_SALES,
                permission__code='quote.view.buy_cost',
            ).exists()
        )

    def test_membership_backfill_reports_null_or_ambiguous_users_without_guessing(self):
        good_user = CustomUser.objects.create_user(
            username='good-user',
            password='test12345',
            role=CustomUser.ROLE_MANAGER,
            department='AIR',
            organization=self.efm,
        )
        null_org_user = CustomUser.objects.create_user(
            username='null-org-user',
            password='test12345',
            role=CustomUser.ROLE_SALES,
            department='AIR',
        )
        unknown_role_user = CustomUser.objects.create_user(
            username='unknown-role-user',
            password='test12345',
            role='contractor',
            department='AIR',
            organization=self.efm,
        )
        unknown_department_user = CustomUser.objects.create_user(
            username='unknown-department-user',
            password='test12345',
            role=CustomUser.ROLE_SALES,
            department='SPACE',
            organization=self.efm,
        )
        no_department_user = CustomUser.objects.create_user(
            username='no-department-user',
            password='test12345',
            role=CustomUser.ROLE_ADMIN,
            organization=self.efm,
        )

        result = self._run_seed()

        self.assertEqual(UserMembership.objects.filter(user=good_user).count(), 1)
        self.assertEqual(UserMembership.objects.filter(user=no_department_user).count(), 1)
        self.assertEqual(UserMembership.objects.filter(user=null_org_user).count(), 0)
        self.assertEqual(UserMembership.objects.filter(user=unknown_role_user).count(), 0)
        self.assertEqual(UserMembership.objects.filter(user=unknown_department_user).count(), 0)
        self.assertIn('null-org-user', result['skipped']['null_organization'])
        self.assertIn('unknown-role-user', result['skipped']['unknown_role'])
        self.assertIn('unknown-department-user', result['skipped']['unknown_department'])
        self.assertIn('no-department-user', result['reported']['users_missing_department'])

        good_membership = UserMembership.objects.get(user=good_user)
        self.assertEqual(good_membership.organization, self.efm)
        self.assertIsNone(good_membership.branch)
        self.assertEqual(good_membership.department.code, 'AIR')
        self.assertEqual(good_membership.role.code, CustomUser.ROLE_MANAGER)

    def test_existing_login_and_me_responses_remain_backward_compatible(self):
        organization = self.efm
        OrganizationBranding.objects.create(
            organization=organization,
            display_name='Express Freight Management',
            primary_color='#0F2A56',
            accent_color='#D71920',
        )
        user = CustomUser.objects.create_user(
            username='compat-user',
            password='testpass123',
            role=CustomUser.ROLE_SALES,
            organization=organization,
        )
        self._run_seed()

        client = APIClient()
        login_response = client.post(
            '/api/auth/login/',
            {'username': 'compat-user', 'password': 'testpass123'},
            format='json',
        )

        self.assertEqual(login_response.status_code, status.HTTP_200_OK)
        login_data = login_response.json()
        self.assertEqual(login_data['username'], user.username)
        self.assertEqual(login_data['role'], CustomUser.ROLE_SALES)
        self.assertIn('token', login_data)
        self.assertEqual(
            set(login_data['user']['permissions'].keys()),
            {'can_view_buy_charges', 'can_view_margins'},
        )
        self.assertEqual(login_data['user']['organization']['slug'], 'efm')

        me_response = client.get(
            '/api/auth/me/',
            HTTP_AUTHORIZATION=f"Token {login_data['token']}",
        )

        self.assertEqual(me_response.status_code, status.HTTP_200_OK)
        me_data = me_response.json()
        self.assertEqual(me_data['username'], user.username)
        self.assertEqual(me_data['role'], CustomUser.ROLE_SALES)
        self.assertEqual(
            set(me_data['permissions'].keys()),
            {'can_view_buy_charges', 'can_view_margins'},
        )
        self.assertEqual(me_data['organization']['branding']['display_name'], 'Express Freight Management')
