import os
import django
from decimal import Decimal

# Setup Django Environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rate_engine.settings')
django.setup()

from rest_framework.test import APIRequestFactory
from rest_framework.test import force_authenticate
from django.contrib.auth import get_user_model
from quotes.views import QuoteComputeV3APIView
from core.models import Location
from quotes.models import Quote

def test_api():
    factory = APIRequestFactory()
    User = get_user_model()
    
    # Get or create a test user
    user, _ = User.objects.get_or_create(username='admin', defaults={'email': 'admin@example.com'})

    print(f"User: {user.username}")

    try:
        pom_loc = Location.objects.get(code='POM')
        bne_loc = Location.objects.get(code='BNE')
    except Location.DoesNotExist:
        print("ERROR: POM or BNE location not found.")
        return

    # Define the payload for EXPORT Quote
    payload = {
        "mode": "AIR",
        "service_scope": "D2A",  # Door to Airport
        "incoterm": "CIF",       # Example
        "origin_location_id": str(pom_loc.id),      # POM
        "destination_location_id": str(bne_loc.id), # BNE
        "customer_id": "c96c04be-2448-4857-83f7-8d10669595a2", # Seed Customer Pty Ltd
        "contact_id": "889de458-162f-495b-8f31-a928f28deaa7", # Seed
        "cargo_type": "GENERAL",
        "container_type": "LCL",
        "dimensions": [
            {
                "length_cm": 100,
                "width_cm": 100,
                "height_cm": 100,
                "gross_weight_kg": 150, # 150kg
                "pieces": 1,
            }
        ],
        "payment_term": "PREPAID",
        "currency": "PGK"
    }

    # Make the POST request
    print("\nSending POST request to /api/v3/quotes/compute/...")
    
    request = factory.post(
        '/api/v3/quotes/compute/',
        data=payload,
        format='json'
    )
    force_authenticate(request, user=user)
    
    # Process request via View
    view = QuoteComputeV3APIView.as_view()
    
    try:
        response = view(request)
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 201:
            print("Quote Created Successfully!")
            print(f"Quote ID: {response.data.get('id')}")
            print(f"Total Sell: {response.data.get('total_sell')}")
        else:
            print("Failed to create quote.")
            print(response.data)

    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_api()
