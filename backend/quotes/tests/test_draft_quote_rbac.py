"""
Test RBAC enforcement for draft quote endpoints.
"""
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status
from uuid import uuid4

from quotes.spot_models import SpotPricingEnvelopeDB
from accounts.models import Role
from parties.models import Organization, Branch, Department
from accounts.models import UserMembership


class DraftQuoteEndpointIntegrationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        
        # Create users with different roles
        self.admin_user = get_user_model().objects.create_user(
            username="admin_test",
            password="testpass123",
            role=get_user_model().ROLE_ADMIN,
        )
        
        self.manager_user = get_user_model().objects.create_user(
            username="manager_test",
            password="testpass123",
            role=get_user_model().ROLE_MANAGER,
        )
        
        self.sales_user = get_user_model().objects.create_user(
            username="sales_test",
            password="testpass123",
            role=get_user_model().ROLE_SALES,
        )
        
        self.finance_user = get_user_model().objects.create_user(
            username="finance_test",
            password="testpass123",
            role=get_user_model().ROLE_FINANCE,
        )
        
        # Create a test SPE (with minimal required fields)
        org = Organization.objects.create(name="Test Org", slug="test-org")
        branch = Branch.objects.create(organization=org, code="TEST", name="Test Branch")
        dept = Department.objects.create(organization=org, code="AIR", name="Air Freight")
        
        self.spe = SpotPricingEnvelopeDB.objects.create(
            shipment_context_json={
                "origin_country": "PG",
                "destination_country": "PG", 
                "origin_code": "POM",
                "destination_code": "LAE",
                "commodity": "GCR",
                "total_weight_kg": 100,
                "pieces": 1,
                "service_scope": "D2D",
            },
            conditions_json={},
            organization=org,
            branch=branch,
            department=dept,
            owner=self.sales_user,
            created_by=self.sales_user,
            spot_trigger_reason_code="MISSING_SCOPE_RATES",
            spot_trigger_reason_text="Missing scope rates",
            expires_at="2026-12-31T23:59:59Z",
        )

    def test_draft_quote_read_endpoint_permissions(self):
        """Test that only authorized users can access draft quote read endpoint."""
        url = f"/api/v3/spot/envelopes/{self.spe.id}/draft-quote/"
        
        # Unauthenticated request should fail
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        
        # Login as finance user (should be denied)
        self.client.force_authenticate(user=self.finance_user)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        
        # Login as sales user (should be allowed)
        self.client.force_authenticate(user=self.sales_user)
        response = self.client.get(url)
        # This might return 404 or 200 depending on whether draft quote data exists,
        # but it should not be a 403 Forbidden
        self.assertNotEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        
        # Login as manager user (should be allowed)
        self.client.force_authenticate(user=self.manager_user)
        response = self.client.get(url)
        self.assertNotEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        
        # Login as admin user (should be allowed)
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(url)
        self.assertNotEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_draft_quote_resolve_endpoint_permissions(self):
        """Test that only authorized users can access draft quote resolve endpoint."""
        url = f"/api/v3/spot/envelopes/{self.spe.id}/draft-quote/resolve/"
        
        # Unauthenticated request should fail
        response = self.client.post(url, {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        
        # Login as finance user (should be denied)
        self.client.force_authenticate(user=self.finance_user)
        response = self.client.post(url, {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        
        # Login as sales user (should be allowed)
        self.client.force_authenticate(user=self.sales_user)
        response = self.client.post(url, {}, format='json')
        # This will likely return 400 due to missing required fields, but not 403
        self.assertNotEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        
        # Login as manager user (should be allowed)
        self.client.force_authenticate(user=self.manager_user)
        response = self.client.post(url, {}, format='json')
        self.assertNotEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        
        # Login as admin user (should be allowed)
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.post(url, {}, format='json')
        self.assertNotEqual(response.status_code, status.HTTP_403_FORBIDDEN)