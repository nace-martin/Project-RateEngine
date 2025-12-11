
import os
import sys
import django
import json

sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rate_engine.settings')
django.setup()

from ratecards.models import PartnerRate

def run():
    print("--- Inspecting Tiering JSON ---")
    # Find a rate with tiering_json
    rate = PartnerRate.objects.exclude(tiering_json__isnull=True).exclude(tiering_json={}).first()
    
    if rate:
        print(f"Found Rate: {rate}")
        print(f"JSON Structure: {json.dumps(rate.tiering_json, indent=2)}")
    else:
        print("No tiered rates found.")

if __name__ == "__main__":
    run()
