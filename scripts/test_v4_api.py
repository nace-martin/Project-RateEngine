import os
import sys
import json
from decimal import Decimal

# Setup Django Environment
sys.path.append(os.path.join(os.path.dirname(__file__), '../backend'))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "rate_engine.settings")

import django
django.setup()

from django.conf import settings
if not 'testserver' in settings.ALLOWED_HOSTS:
    # Handle tuple or list
    hosts = list(settings.ALLOWED_HOSTS)
    hosts.append('testserver')
    settings.ALLOWED_HOSTS = hosts

from rest_framework.test import APIClient
from rest_framework import status
from parties.models import Company

def test_v4_api():
    print("Testing V4 API using Django Test Client...")
    client = APIClient()
    endpoint = "/api/v4/quote/calculate/"
    
    # 1. Invalid Payload
    print("\n[TEST 1] Invalid Payload (Empty)...")
    response = client.post(endpoint, {}, format='json')
    if response.status_code == 400:
        print("PASS: Got 400 Bad Request.")
    else:
        print(f"FAIL: Expected 400, got {response.status_code}")
        print(response.content)

    # 2. Valid Payload (Domestic)
    # Ensure a customer exists
    customer = Company.objects.filter(company_type='CUSTOMER').first()
    if not customer:
        print("WARNING: No customer found. Creating dummy customer for test.")
        customer = Company.objects.create(name="Test Customer", company_type='CUSTOMER', code="TEST001")
        
    payload = {
        "service_type": "DOMESTIC",
        "origin": "POM",
        "destination": "LAE",
        "customer_id": customer.id,
        "cargo_details": {
            "weight_kg": 100.0,
            "volume_m3": 1.0,
            "quantity": 10
        },
        "service_scope": "A2A",
        "incoterms": None
    }
    
    print(f"\n[TEST 2] Valid Payload (Domestic) with Customer {customer.id}...")
    response = client.post(endpoint, payload, format='json')
    
    if response.status_code == 200:
        print("PASS: Got 200 OK.")
        data = response.json()
        print(f"Total Sell: {data.get('total_sell')} {data.get('currency')}")
        # print(json.dumps(data, indent=2))
    elif response.status_code == 400:
        print("INFO: Got 400 (Expected if no rates exist yet).")
        print(response.json())
    else:
        print(f"FAIL: Unexpected status {response.status_code}")
        print(response.content)

if __name__ == "__main__":
    test_v4_api()
