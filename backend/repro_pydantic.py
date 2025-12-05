import os
import django
from decimal import Decimal
import uuid

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rate_engine.settings')
django.setup()

from quotes.schemas import QuoteComputeRequest, V3ManualOverride

payload = {
    "customer_id": str(uuid.uuid4()),
    "contact_id": str(uuid.uuid4()),
    "mode": "AIR",
    "incoterm": "DAP",
    "service_scope": "A2A",
    "origin_location_id": str(uuid.uuid4()),
    "destination_location_id": str(uuid.uuid4()),
    "dimensions": [
        {
            "pieces": 1,
            "length_cm": "120",
            "width_cm": "80",
            "height_cm": "70",
            "gross_weight_kg": "85.00",
        }
    ],
    "payment_term": "PREPAID",
    "overrides": [
        {
            "service_component_id": str(uuid.uuid4()),
            "cost_fcy": "7.10",
            "currency": "AUD",
            "unit": "PER_KG",
        },
        {
            "service_component_id": str(uuid.uuid4()),
            "cost_fcy": "120.00",
            "currency": "AUD",
            "unit": "PER_SHIPMENT",
        }
    ]
}

try:
    print("Attempting validation...")
    validated = QuoteComputeRequest(**payload)
    print("Validation SUCCESS!")
    print(validated)
except Exception as e:
    print(f"Validation FAILED: {e}")
    if hasattr(e, 'errors'):
        print(e.errors())
