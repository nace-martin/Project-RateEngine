"""
Test script to create an Export D2A Prepaid quote via API.
"""
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rate_engine.settings')
django.setup()

from quotes.views import QuoteV3ComputeAPIView
from django.test import RequestFactory
from accounts.models import CustomUser
import json

def create_quote():
    # Get admin user
    user = CustomUser.objects.first()
    print(f"User: {user}")

    # Create request factory
    factory = RequestFactory()

    # Create payload
    payload = {
        'origin_code': 'POM',
        'destination_code': 'BNE',
        'mode': 'AIR',
        'service_scope': 'D2A',
        'payment_term': 'PREPAID',
        'gross_weight': 100,
        'chargeable_weight': 100,
        'pieces': 1,
        'length': 50,
        'width': 50,
        'height': 50
    }

    # Make request
    request = factory.post('/api/quotes/v3/compute/', json.dumps(payload), content_type='application/json')
    request.user = user

    view = QuoteV3ComputeAPIView.as_view()
    response = view(request)

    print(f"Status Code: {response.status_code}")
    if response.status_code == 201:
        data = response.data
        print(f"Quote: {data.get('quote_number')}")
        print(f"Status: {data.get('status')}")
        
        # Check for missing rates
        if data.get('latest_version') and data['latest_version'].get('lines'):
            missing = [l for l in data['latest_version']['lines'] if l.get('is_rate_missing')]
            if missing:
                print(f"Missing rates: {[l.get('description') for l in missing]}")
            else:
                print("All rates found!")
    else:
        print(f"Error: {response.data}")

if __name__ == "__main__":
    create_quote()
