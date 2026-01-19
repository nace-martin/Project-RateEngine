from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status
from pricing_v3.models import RateCard, RateLine, RateBreak, Zone
from services.models import ServiceComponent
from parties.models import Company
from django.contrib.auth import get_user_model
from django.utils import timezone
import io

User = get_user_model()

class RateCardCSVImportTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpassword',
            role=User.ROLE_MANAGER
        )
        self.client.force_authenticate(user=self.user)
        
        self.origin = Zone.objects.create(code='BNE', name='Brisbane')
        self.destination = Zone.objects.create(code='POM', name='Port Moresby')
        self.supplier = Company.objects.create(name="Test Supplier", company_type="SUPPLIER")
        
        self.card = RateCard.objects.create(
            name="Test Card",
            origin_zone=self.origin,
            destination_zone=self.destination,
            currency="AUD",
            supplier=self.supplier
        )
        
        self.comp_freight = ServiceComponent.objects.create(code='FRT', description='Freight')
        self.comp_pickup = ServiceComponent.objects.create(code='P/C', description='Pickup')

    def test_import_csv_success(self):
        csv_content = (
            "Component,Method,MinCharge,Unit,Rates,Description\n"
            "FRT,WEIGHT_BREAK,50.00,,0-45:5.50;45-100:4.50;100-300:3.50,Air Freight\n"
            "P/C,FLAT,75.00,,,Pickup Fee\n"
        )
        
        file = io.BytesIO(csv_content.encode('utf-8'))
        file.name = 'rates.csv'
        
        url = f'/api/v3/rate-cards/{self.card.id}/import_csv/'
        response = self.client.post(url, {'file': file}, format='multipart')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['message'], "Imported 2 lines.")
        
        # Verify Lines
        lines = RateLine.objects.filter(card=self.card)
        self.assertEqual(lines.count(), 2)
        
        frt_line = lines.get(component__code='FRT')
        self.assertEqual(frt_line.method, 'WEIGHT_BREAK')
        self.assertEqual(frt_line.min_charge, 50.00)
        self.assertEqual(frt_line.breaks.count(), 3)
        
        pc_line = lines.get(component__code='P/C')
        self.assertEqual(pc_line.method, 'FLAT')
        self.assertEqual(pc_line.min_charge, 75.00)

    def test_import_csv_invalid_component(self):
        csv_content = (
            "Component,Method,MinCharge,Unit,Rates,Description\n"
            "INVALID,FLAT,50.00,,,\n"
        )
        file = io.BytesIO(csv_content.encode('utf-8'))
        file.name = 'rates.csv'
        
        url = f'/api/v3/rate-cards/{self.card.id}/import_csv/'
        response = self.client.post(url, {'file': file}, format='multipart')
        
        # Should return 207 or 200 with errors? Implementation returns 207 if errors exist.
        self.assertEqual(response.status_code, status.HTTP_207_MULTI_STATUS)
        self.assertIn("Row 1: Component 'INVALID' not found.", response.data['errors'])
