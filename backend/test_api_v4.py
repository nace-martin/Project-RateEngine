import os
import django
import json
from decimal import Decimal

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rate_engine.settings')
django.setup()

from django.test import Client
from rest_framework.test import APIRequestFactory, force_authenticate
from django.contrib.auth import get_user_model
from quotes.views import QuoteComputeV3APIView
from core.models import Location, Country, City

User = get_user_model()

def test_api():
    print("="*60)
    print("Testing API Integration (V4 Engine via View)")
    print("="*60)
    
    # Setup Data
    user = User.objects.first()
    if not user:
        print("No user found!")
        return

    # POM and LAE locations
    pg, _ = Country.objects.get_or_create(code='PG', defaults={'name': 'Papua New Guinea'})
    
    pom_city, _ = City.objects.get_or_create(country=pg, name='Port Moresby')
    lae_city, _ = City.objects.get_or_create(country=pg, name='Lae')
    
    # Create Locations
    # Check if they exist first by code
    pom = Location.objects.filter(code='POM').first()
    if not pom:
        pom = Location.objects.create(
            code='POM', 
            name='Port Moresby', 
            country=pg,
            city=pom_city
        )
        
    lae = Location.objects.filter(code='LAE').first()
    if not lae:
        lae = Location.objects.create(
            code='LAE', 
            name='Lae', 
            country=pg,
            city=lae_city
        )
    
     # DEBUG: Check Rate Data
    from pricing_v4.models import DomesticCOGS, ProductCode
    pc = ProductCode.objects.filter(code='DOM-FRT-AIR').first()
    print(f"DEBUG: ProductCode DOM-FRT-AIR exists: {pc is not None}")
    
    cogs_count = DomesticCOGS.objects.filter(origin_zone='POM', destination_zone='LAE').count()
    print(f"DEBUG: DomesticCOGS POM->LAE count: {cogs_count}")
    if cogs_count > 0:
        cogs = DomesticCOGS.objects.filter(origin_zone='POM', destination_zone='LAE').first()
        print(f"DEBUG: COGS Rate: {cogs.rate_per_kg}, Carrier: {cogs.carrier}")
    else:
        print("DEBUG: NO COGS FOUND!")

    from services.models import ServiceComponent
    sc = ServiceComponent.objects.filter(code='DOM-FRT-AIR').first()
    print(f"DEBUG: ServiceComponent DOM-FRT-AIR exists: {sc is not None}")

    # Payload
    payload = {
        "customer_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6", # Dummy UUIDs?
                                                                 # Need real customer ID or mocking
                                                                 # View will 404 if customer missing.
    }
    
    # Actually, simpler to call the View method directly if we want to avoid DB dep hell for customer?
    # No, View does `get_object_or_404(Company)`.
    # Let's just instantiate the Adapter directly in the script to verify IT works?
    # No, we want to test the VIEW integration.
    
    # Check if we have a customer
    from parties.models import Company, Contact
    cust = Company.objects.filter(company_type='CUSTOMER').first()
    if not cust:
        # Create one
        cust = Company.objects.create(name="Test Customer", company_type='CUSTOMER')
        
    cont = Contact.objects.filter(company=cust).first()
    if not cont:
        cont = Contact.objects.create(company=cust, first_name="Test", last_name="User", email="test@test.com")
        
    data = {
        "customer_id": str(cust.id),
        "contact_id": str(cont.id),
        "origin_location_id": str(pom.id),
        "destination_location_id": str(lae.id),
        "mode": "AIR",
        "incoterm": "FCA", # Irrelevant for Domestic?
        "payment_term": "PREPAID",
        "service_scope": "A2A",
        "is_dangerous_goods": False,
        "dimensions": [
            {
                "pieces": 1,
                "length_cm": 100,
                "width_cm": 100,
                "height_cm": 100,
                "gross_weight_kg": 100
            }
        ]
    }
    
    factory = APIRequestFactory()
    request = factory.post(
        '/api/quotes/compute/',
        data=data, # DRF factory handles dict as JSON default or form? verify. 
                   # data=json.dumps(data) with content_type is safer or format='json'
        format='json'
    )
    force_authenticate(request, user=user)
    
    view = QuoteComputeV3APIView.as_view()
    response = view(request)
    
    print(f"Status Code: {response.status_code}")
    if response.status_code == 201:
        data = response.data
        print("Quote Created Successfully!")
        print(f"Quote ID: {data.get('id')}")
        print(f"Total Sell: {data.get('total_sell_pgk')}")
        print("-" * 20)
        print("Line Items:")
        # Serializer returns 'latest_version' object
        latest_version = data.get('latest_version', {})
        lines = latest_version.get('lines', [])
        
        if not lines:
            print("WARNING: No lines in latest_version!")
            print(f"Full Data Keys: {list(data.keys())}")
            print(f"Latest Version Keys: {list(latest_version.keys())}")

        for line in lines:
            print(f"- {line.get('service_component').get('description')}: K{line.get('sell_pgk')}")
    else:
        print("Error:")
        print(response.data)

if __name__ == '__main__':
    test_api()
