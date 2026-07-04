# backend/quotes/tests/test_rbac_backend_enforcement.py
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status

from accounts.models import UserMembership, Role
from parties.models import Organization, Branch, Department
from quotes.models import Quote
from crm.models import Opportunity, Interaction, Task
from parties.models import Company, Contact


class RBACBackendEnforcementTestCase(TestCase):
    """
    Test cases for backend RBAC enforcement to prevent IDOR attacks
    and ensure proper cross-scope access restrictions.
    """

    def setUp(self):
        # Create organizations
        self.org1 = Organization.objects.create(name="EFM PNG", slug="efm-png")
        self.org2 = Organization.objects.create(name="EFM Australia", slug="efm-au")
        
        # Create branches
        self.branch1 = Branch.objects.create(organization=self.org1, code="POM", name="Port Moresby")
        self.branch2 = Branch.objects.create(organization=self.org2, code="BNE", name="Brisbane")
        
        # Create departments
        self.air_dept = Department.objects.create(organization=self.org1, code="AIR", name="Air Freight")
        self.sea_dept = Department.objects.create(organization=self.org2, code="SEA", name="Sea Freight")
        
        # Create users
        self.User = get_user_model()
        self.user1 = self.User.objects.create_user(
            username='pom_air_user',
            password='testpass123',
            role='sales'
        )
        self.user2 = self.User.objects.create_user(
            username='bne_sea_user',
            password='testpass123',
            role='sales'
        )
        self.admin_user = self.User.objects.create_user(
            username='admin_user',
            password='testpass123',
            role='admin'
        )
        
        # Create user memberships
        self.role, _ = Role.objects.get_or_create(code='sales', name='Sales')
        self.membership1 = UserMembership.objects.create(
            user=self.user1,
            organization=self.org1,
            branch=self.branch1,
            department=self.air_dept,
            role=self.role,
            is_active=True,
            is_primary=True
        )
        self.membership2 = UserMembership.objects.create(
            user=self.user2,
            organization=self.org2,
            branch=self.branch2,
            department=self.sea_dept,
            role=self.role,
            is_active=True,
            is_primary=True
        )
        self.admin_membership = UserMembership.objects.create(
            user=self.admin_user,
            organization=self.org1,
            branch=self.branch1,
            department=self.air_dept,
            role=self.role,
            is_active=True,
            is_primary=True
        )
        
        # Create companies
        self.company1 = Company.objects.create(
            name="POM Customer",
            organization=self.org1,
            branch=self.branch1,
            department=self.air_dept
        )
        self.company2 = Company.objects.create(
            name="BNE Customer", 
            organization=self.org2,
            branch=self.branch2,
            department=self.sea_dept
        )
        
        # Create quotes
        self.quote1 = Quote.objects.create(
            customer=self.company1,
            organization=self.org1,
            branch=self.branch1,
            department=self.air_dept,
            owner=self.user1,
            created_by=self.user1,
            quote_number="QT-TEST-0001",
            mode="AIR",
            shipment_type=Quote.ShipmentType.IMPORT,
            output_currency="PGK",
            status=Quote.Status.DRAFT
        )
        self.quote2 = Quote.objects.create(
            customer=self.company2,
            organization=self.org2,
            branch=self.branch2,
            department=self.sea_dept,
            owner=self.user2,
            created_by=self.user2,
            quote_number="QT-TEST-0002",
            mode="SEA",
            shipment_type=Quote.ShipmentType.EXPORT,
            output_currency="AUD",
            status=Quote.Status.DRAFT
        )
        
        # Create opportunities
        self.opportunity1 = Opportunity.objects.create(
            company=self.company1,
            title="POM Opportunity",
            service_type="AIR",
            organization=self.org1,
            branch=self.branch1,
            department=self.air_dept,
            owner=self.user1
        )
        self.opportunity2 = Opportunity.objects.create(
            company=self.company2,
            title="BNE Opportunity",
            service_type="SEA",
            organization=self.org2,
            branch=self.branch2,
            department=self.sea_dept,
            owner=self.user2
        )
        
        # Setup API clients
        self.client1 = APIClient()
        self.client2 = APIClient()
        self.admin_client = APIClient()

    def test_pom_user_cannot_access_bne_quote(self):
        """POM Air Freight user cannot access BNE Sea Freight quote"""
        # Authenticate user1 (POM Air)
        self.client1.force_authenticate(user=self.user1)
        
        # Try to access quote2 (BNE Sea) - should fail with 404
        url = reverse('quotes:quote-v3-detail', kwargs={'pk': self.quote2.pk})
        response = self.client1.get(url)
        
        # Should return 404, not 403, to prevent object existence leakage
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_pom_user_can_access_own_quote(self):
        """POM Air Freight user can access their own quote"""
        # Authenticate user1 (POM Air)
        self.client1.force_authenticate(user=self.user1)
        
        # Access quote1 (POM Air) - should succeed
        url = reverse('quotes:quote-v3-detail', kwargs={'pk': self.quote1.pk})
        response = self.client1.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['id'], str(self.quote1.pk))

    def test_bne_user_cannot_access_pom_quote(self):
        """BNE Sea Freight user cannot access POM Air Freight quote"""
        # Authenticate user2 (BNE Sea)
        self.client2.force_authenticate(user=self.user2)
        
        # Try to access quote1 (POM Air) - should fail with 404
        url = reverse('quotes:quote-v3-detail', kwargs={'pk': self.quote1.pk})
        response = self.client2.get(url)
        
        # Should return 404, not 403, to prevent object existence leakage
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_admin_can_access_cross_scope_quote(self):
        """Admin can access cross-scope quote"""
        # Authenticate admin
        self.admin_client.force_authenticate(user=self.admin_user)
        
        # Access quote2 (BNE Sea) - should succeed for admin
        url = reverse('quotes:quote-v3-detail', kwargs={'pk': self.quote2.pk})
        response = self.admin_client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['id'], str(self.quote2.pk))

    def test_pom_user_cannot_list_bne_quotes(self):
        """POM user cannot list BNE quotes in their view"""
        # Authenticate user1 (POM Air)
        self.client1.force_authenticate(user=self.user1)
        
        # List quotes - should only see their own
        url = reverse('quotes:quote-v3-list')
        response = self.client1.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        quote_ids = [item['id'] for item in response.data.get('results', [])]
        
        # Should contain quote1 but not quote2
        self.assertIn(str(self.quote1.pk), quote_ids)
        self.assertNotIn(str(self.quote2.pk), quote_ids)

    def test_pom_user_cannot_access_bne_opportunity(self):
        """POM Air Freight user cannot access BNE Sea Freight opportunity"""
        # Authenticate user1 (POM Air)
        self.client1.force_authenticate(user=self.user1)
        
        # Try to access opportunity2 (BNE Sea) - should fail with 404
        url = reverse('crm:opportunity-detail', kwargs={'pk': self.opportunity2.pk})
        response = self.client1.get(url)
        
        # Should return 404, not 403, to prevent object existence leakage
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_pom_user_can_access_own_opportunity(self):
        """POM Air Freight user can access their own opportunity"""
        # Authenticate user1 (POM Air)
        self.client1.force_authenticate(user=self.user1)
        
        # Access opportunity1 (POM Air) - should succeed
        url = reverse('crm:opportunity-detail', kwargs={'pk': self.opportunity1.pk})
        response = self.client1.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['id'], str(self.opportunity1.pk))

    def test_direct_id_guessing_blocked_for_quotes(self):
        """Direct ID guessing for quote returns 404 for unauthorized access"""
        # Authenticate user1 (POM Air)
        self.client1.force_authenticate(user=self.user1)
        
        # Try to access quote2 using its actual ID - should return 404
        url = reverse('quotes:quote-v3-detail', kwargs={'pk': self.quote2.pk})
        response = self.client1.get(url)
        
        # Should return 404 to prevent object existence leakage
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_direct_id_guessing_blocked_for_opportunities(self):
        """Direct ID guessing for opportunity returns 404 for unauthorized access"""
        # Authenticate user1 (POM Air)
        self.client1.force_authenticate(user=self.user1)
        
        # Try to access opportunity2 using its actual ID - should return 404
        url = reverse('crm:opportunity-detail', kwargs={'pk': self.opportunity2.pk})
        response = self.client1.get(url)
        
        # Should return 404 to prevent object existence leakage
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_cross_branch_entity_access_blocked(self):
        """Users cannot access entities from different branches"""
        # Authenticate user1 (POM Air)
        self.client1.force_authenticate(user=self.user1)
        
        # Try to access various entities from different branch
        test_cases = [
            ('quotes:quote-v3-detail', self.quote2.pk),
            ('crm:opportunity-detail', self.opportunity2.pk),
        ]
        
        for endpoint, obj_pk in test_cases:
            with self.subTest(endpoint=endpoint):
                url = reverse(endpoint, kwargs={'pk': obj_pk})
                response = self.client1.get(url)
                
                # Should return 404 to prevent object existence leakage
                self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)