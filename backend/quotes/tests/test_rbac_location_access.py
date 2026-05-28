# backend/quotes/tests/test_rbac_location_access.py
"""
RBAC & Location-based access visibility and security tests.
Verifies Phase 1 access boundaries and enforcements on all quote workflows.
"""

from datetime import date, timedelta
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from core.models import Country, City, Airport, Location, FxSnapshot
from parties.models import Company, Contact
from quotes.models import Quote, QuoteTotal, QuoteVersion
from services.models import ServiceComponent

User = get_user_model()

def create_test_location(code, name, country_code='PG'):
    """Helper to cleanly bootstrap a Location in tests."""
    country, _ = Country.objects.get_or_create(code=country_code, defaults={'name': 'Test Country'})
    city, _ = City.objects.get_or_create(name=name, country=country)
    airport, _ = Airport.objects.get_or_create(iata_code=code, defaults={'name': f'{name} Airport', 'city': city})
    loc, _ = Location.objects.get_or_create(
        code=code,
        defaults={
            'name': name,
            'airport': airport,
            'country': country,
            'city': city,
            'kind': 'AIRPORT',
            'is_active': True
        }
    )
    return loc


class QuoteRbacLocationAccessTests(APITestCase):
    """
    Test suite for verifying that users can only access departments and locations they are authorized for.
    """
    
    @classmethod
    def setUpTestData(cls):
        # 1. Create Locations (POM, LAE, BNE)
        cls.loc_pom = create_test_location('POM', 'Port Moresby', 'PG')
        cls.loc_lae = create_test_location('LAE', 'Lae', 'PG')
        cls.loc_bne = create_test_location('BNE', 'Brisbane', 'AU')

        # 2. Create customer organization & contacts
        cls.customer = Company.objects.create(name='RBAC test customer', is_customer=True)
        cls.contact = Contact.objects.create(
            company=cls.customer,
            first_name='Rbac',
            last_name='User',
            email='rbac@example.com'
        )

        # 3. Create Users with different role, department, and location scopes
        # A. Air POM Sales User
        cls.air_pom_sales = User.objects.create_user(
            username='air_pom_sales',
            password='password123',
            role=User.ROLE_SALES,
            department='AIR',
            primary_location=cls.loc_pom
        )
        cls.air_pom_sales.authorised_locations.add(cls.loc_pom)

        # B. Sea POM Sales User
        cls.sea_pom_sales = User.objects.create_user(
            username='sea_pom_sales',
            password='password123',
            role=User.ROLE_SALES,
            department='SEA',
            primary_location=cls.loc_pom
        )
        cls.sea_pom_sales.authorised_locations.add(cls.loc_pom)

        # C. Air LAE Sales User
        cls.air_lae_sales = User.objects.create_user(
            username='air_lae_sales',
            password='password123',
            role=User.ROLE_SALES,
            department='AIR',
            primary_location=cls.loc_lae
        )
        cls.air_lae_sales.authorised_locations.add(cls.loc_lae)

        # D. Air POM Manager
        cls.air_pom_manager = User.objects.create_user(
            username='air_pom_manager',
            password='password123',
            role=User.ROLE_MANAGER,
            department='AIR',
            primary_location=cls.loc_pom
        )
        cls.air_pom_manager.authorised_locations.add(cls.loc_pom)

        # E. Sea LAE Sales User
        cls.sea_lae_sales = User.objects.create_user(
            username='sea_lae_sales',
            password='password123',
            role=User.ROLE_SALES,
            department='SEA',
            primary_location=cls.loc_lae
        )
        cls.sea_lae_sales.authorised_locations.add(cls.loc_lae)

        # F. National Air Manager (Authorized for both POM and LAE)
        cls.national_air_manager = User.objects.create_user(
            username='national_air_manager',
            password='password123',
            role=User.ROLE_MANAGER,
            department='AIR',
            primary_location=cls.loc_pom
        )
        cls.national_air_manager.authorised_locations.add(cls.loc_pom, cls.loc_lae)

        # G. Superuser / Admin
        cls.admin_user = User.objects.create_superuser(
            username='admin_user',
            password='password123',
            email='admin@example.com',
            role=User.ROLE_ADMIN
        )

        # 4. Create Quotes belonging to different departments and locations
        # A. Air POM Quote (Created by air_pom_sales)
        cls.quote_air_pom = Quote.objects.create(
            customer=cls.customer,
            contact=cls.contact,
            mode='AIR',
            owning_location=cls.loc_pom,
            origin_location=cls.loc_bne,
            destination_location=cls.loc_pom,
            created_by=cls.air_pom_sales,
            status=Quote.Status.DRAFT
        )
        # Setup version + totals so list/retrieve views serialization works
        version_1 = QuoteVersion.objects.create(quote=cls.quote_air_pom, version_number=1)
        QuoteTotal.objects.create(quote_version=version_1, total_sell_pgk=Decimal('100.00'))

        # B. Sea POM Quote (Created by sea_pom_sales)
        cls.quote_sea_pom = Quote.objects.create(
            customer=cls.customer,
            contact=cls.contact,
            mode='SEA',
            owning_location=cls.loc_pom,
            origin_location=cls.loc_bne,
            destination_location=cls.loc_pom,
            created_by=cls.sea_pom_sales,
            status=Quote.Status.DRAFT
        )
        version_2 = QuoteVersion.objects.create(quote=cls.quote_sea_pom, version_number=1)
        QuoteTotal.objects.create(quote_version=version_2, total_sell_pgk=Decimal('200.00'))

        # C. Air LAE Quote (Created by air_lae_sales)
        cls.quote_air_lae = Quote.objects.create(
            customer=cls.customer,
            contact=cls.contact,
            mode='AIR',
            owning_location=cls.loc_lae,
            origin_location=cls.loc_bne,
            destination_location=cls.loc_lae,
            created_by=cls.air_lae_sales,
            status=Quote.Status.DRAFT
        )
        version_3 = QuoteVersion.objects.create(quote=cls.quote_air_lae, version_number=1)
        QuoteTotal.objects.create(quote_version=version_3, total_sell_pgk=Decimal('300.00'))

        # D. Sea LAE Quote (Created by sea_lae_sales)
        cls.quote_sea_lae = Quote.objects.create(
            customer=cls.customer,
            contact=cls.contact,
            mode='SEA',
            owning_location=cls.loc_lae,
            origin_location=cls.loc_bne,
            destination_location=cls.loc_lae,
            created_by=cls.sea_lae_sales,
            status=Quote.Status.DRAFT
        )
        version_4 = QuoteVersion.objects.create(quote=cls.quote_sea_lae, version_number=1)
        QuoteTotal.objects.create(quote_version=version_4, total_sell_pgk=Decimal('400.00'))

        # FX snapshot setup for calculations
        FxSnapshot.objects.create(
            as_of_timestamp=timezone_now(),
            source='test',
            rates={'PGK': {'tt_buy': '1.0', 'tt_sell': '1.0'}}
        )

    def test_air_pom_user_sees_only_air_pom_quotes(self):
        """Air POM Sales User must only see Air POM quotes that they created."""
        self.client.force_authenticate(user=self.air_pom_sales)
        response = self.client.get('/api/v3/quotes/')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.json().get('results', [])
        
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['id'], str(self.quote_air_pom.id))

    def test_air_pom_user_cannot_access_sea_pom_quote(self):
        """Air POM Sales User must not see or access Sea POM quotes."""
        self.client.force_authenticate(user=self.air_pom_sales)
        response = self.client.get(f'/api/v3/quotes/{self.quote_sea_pom.id}/')
        
        self.assertIn(response.status_code, [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND])

    def test_air_pom_user_cannot_access_air_lae_quote(self):
        """Air POM Sales User must not see or access Air LAE quotes."""
        self.client.force_authenticate(user=self.air_pom_sales)
        response = self.client.get(f'/api/v3/quotes/{self.quote_air_lae.id}/')
        
        self.assertIn(response.status_code, [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND])

    def test_sea_lae_user_sees_only_sea_lae_quotes(self):
        """Sea LAE Sales User must only see Sea LAE quotes that they created."""
        self.client.force_authenticate(user=self.sea_lae_sales)
        response = self.client.get('/api/v3/quotes/')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.json().get('results', [])
        
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['id'], str(self.quote_sea_lae.id))

    def test_manager_limited_to_authorised_department_location_scope(self):
        """Air POM Manager must see all AIR POM quotes but not LAE or SEA quotes."""
        self.client.force_authenticate(user=self.air_pom_manager)
        response = self.client.get('/api/v3/quotes/')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.json().get('results', [])
        
        # Should see all AIR POM quotes (which matches self.quote_air_pom)
        quote_ids = [r['id'] for r in results]
        self.assertIn(str(self.quote_air_pom.id), quote_ids)
        
        # Managers must not see wrong department (SEA POM) or wrong location (AIR LAE)
        self.assertNotIn(str(self.quote_sea_pom.id), quote_ids)
        self.assertNotIn(str(self.quote_air_lae.id), quote_ids)

    def test_national_manager_sees_multiple_locations(self):
        """National Air Manager must see AIR POM and AIR LAE quotes but not SEA quotes."""
        self.client.force_authenticate(user=self.national_air_manager)
        response = self.client.get('/api/v3/quotes/')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.json().get('results', [])
        
        quote_ids = [r['id'] for r in results]
        self.assertEqual(len(quote_ids), 2)
        self.assertIn(str(self.quote_air_pom.id), quote_ids)
        self.assertIn(str(self.quote_air_lae.id), quote_ids)
        self.assertNotIn(str(self.quote_sea_pom.id), quote_ids)

    def test_admin_sees_all_quotes(self):
        """Global Admin sees everything."""
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get('/api/v3/quotes/')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.json().get('results', [])
        
        self.assertEqual(len(results), 4)

    def test_create_quote_rejects_unauthorised_department_location(self):
        """Creating a quote outside authorized department/location returns 403."""
        self.client.force_authenticate(user=self.air_pom_sales)
        
        response = self.client.post(
            reverse("quotes:quote-compute-v3"),
            {
                "customer_id": str(self.customer.id),
                "contact_id": str(self.contact.id),
                "mode": "SEA",  # SEA is unauthorized for self.air_pom_sales
                "service_scope": "A2A",
                "origin_location_id": str(self.loc_pom.id),
                "destination_location_id": str(self.loc_bne.id),
                "incoterm": "FOB",
                "payment_term": "PREPAID",
                "dimensions": [
                    {
                        "pieces": 1,
                        "length_cm": "10",
                        "width_cm": "10",
                        "height_cm": "10",
                        "gross_weight_kg": "10",
                    }
                ],
            },
            format="json",
        )
        
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("not authorized", response.json().get('detail', '').lower())

    def test_dashboard_respects_filters(self):
        """Reports & dashboards partition aggregates strictly by authorized departments/locations."""
        self.client.force_authenticate(user=self.air_pom_manager)
        response = self.client.get('/api/v3/reports/funnel_metrics/')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        
        # Only 1 quote (quote_air_pom) matches AIR + POM. The others are excluded!
        self.assertEqual(data.get('quotes_created'), 1)

    def test_pdf_export_blocks_unauthorised_quotes(self):
        """PDF exports return 403 for quotes outside authorized scope."""
        self.client.force_authenticate(user=self.air_pom_sales)
        
        # Try to export Sea POM quote (unauthorized)
        response = self.client.get(reverse("quotes:quote-pdf", kwargs={"quote_id": self.quote_sea_pom.id}))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_production_fail_closed_unassigned_user(self):
        """Verify that when RBAC_COMPAT_MODE is False, unassigned users are strictly blocked (production fail-closed)."""
        from django.test import override_settings
        
        # Create a completely unassigned user
        unassigned_user = User.objects.create_user(
            username='strictly_unassigned',
            password='password123',
            role=User.ROLE_SALES,
            department=None,
            primary_location=None
        )
        
        # When RBAC_COMPAT_MODE is False (production simulation)
        with override_settings(RBAC_COMPAT_MODE=False):
            self.client.force_authenticate(user=unassigned_user)
            
            # 1. Direct Detail Fetch -> Returns 404 (or 403)
            response = self.client.get(reverse("quotes:quote-v3-detail", kwargs={"pk": self.quote_air_pom.id}))
            self.assertIn(response.status_code, [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND])
            
            # 2. Quote List -> Returns empty list
            response = self.client.get('/api/v3/quotes/')
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(response.json().get('count', 0), 0)


def timezone_now():
    from django.utils import timezone
    return timezone.now()
