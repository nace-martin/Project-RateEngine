import os
import sys
import django
import json

# Setup Django
sys.path.append('c:\\Users\\commercial.manager\\dev\\Project-RateEngine\\backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rate_engine.settings')
django.setup()

from quotes.models import SpotPricingEnvelopeDB

spe_id = '4fb74259-eb17-47ea-95d0-d8eda22d0acd'
try:
    spe = SpotPricingEnvelopeDB.objects.get(id=spe_id)
    print("SPE ID:", spe.id)
    print("Shipment Context:", spe.shipment_context_json)
    print("Trigger Code:", spe.spot_trigger_reason_code)
    
    print("\nCharges:")
    for charge in spe.charge_lines.all():
        print(f" - [{charge.bucket}] {charge.code}: {charge.description} | {charge.amount} {charge.currency} /{charge.unit} (Source: {charge.source_reference})")
        
except Exception as e:
    print("Error:", e)
