import os
import sys
import django

# Setup Django
sys.path.append('c:\\Users\\commercial.manager\\dev\\Project-RateEngine\\backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rate_engine.settings')
django.setup()

import json
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model

User = get_user_model()
user = User.objects.first()

client = APIClient()
client.force_authenticate(user=user)

spe_id = '4fb74259-eb17-47ea-95d0-d8eda22d0acd'
response = client.get(f'/api/v3/spot/envelopes/{spe_id}/')
print("Status Code:", response.status_code)

data = response.json()
charges = data.get('charges', [])
print(f"Number of charges returned by API: {len(charges)}")
for c in charges:
    print(f" - {c.get('bucket')} | {c.get('code')} | {c.get('description')} | {c.get('amount')}")
