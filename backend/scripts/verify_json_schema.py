
import os
import sys
import django
import json

sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rate_engine.settings')
django.setup()

from ratecards.models import PartnerRate
from ratecards.schemas import TieringJsonSchema

def run():
    print("--- Verifying TieringJsonSchema ---")
    # Find a rate with tiering_json
    rate = PartnerRate.objects.exclude(tiering_json__isnull=True).exclude(tiering_json={}).first()
    
    if rate:
        print(f"Testing Schema against Rate: {rate}")
        try:
            # Validate!
            validated = TieringJsonSchema(**rate.tiering_json)
            print("✓ Validation Successful!")
            print(f"Validated Model: {validated}")
        except Exception as e:
            print(f"❌ Validation Failed: {e}")
            print(f"Raw JSON: {json.dumps(rate.tiering_json, indent=2)}")
    else:
        print("No tiered rates found to test.")

if __name__ == "__main__":
    run()
