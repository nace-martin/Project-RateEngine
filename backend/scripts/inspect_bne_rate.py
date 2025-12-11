
import os
import sys
import django
import json

# Setup Django
sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rate_engine.settings')
django.setup()

from ratecards.models import PartnerRate, PartnerRateLane

def run():
    print("--- Inspecting BNE PartnerRate ---")
    
    # Get Lane: POM -> BNE (Air, General)
    # We want the SELL lane (PX Export Sell Rates 2024)
    lanes = PartnerRateLane.objects.filter(
        rate_card__name="PX Export Sell Rates 2024",
        destination_airport__iata_code='BNE'
    )
    
    if not lanes.exists():
        print("BNE Lane not found!")
        return

    lane = lanes.first()
    print(f"Lane: {lane}")
    
    # Get Freight Rate
    rates = PartnerRate.objects.filter(lane=lane, service_component__code='FRT_AIR_EXP')
    
    for rate in rates:
        print(f"ID: {rate.id}")
        print(f"Tiering JSON: {json.dumps(rate.tiering_json, indent=2)}")

if __name__ == "__main__":
    run()
