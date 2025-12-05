import os
import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "rate_engine.settings")
django.setup()

from ratecards.models import PartnerRateLane, PartnerRate
from services.models import ServiceComponent

def check_data():
    print("Checking Lanes...")
    lanes = PartnerRateLane.objects.filter(
        origin_airport__iata_code='POM',
        destination_airport__iata_code='BNE'
    )
    print(f"Found {lanes.count()} lanes for POM->BNE")
    for lane in lanes:
        print(f"Lane {lane.id}: mode={lane.mode}, shipment_type='{lane.shipment_type}'")
        rates = PartnerRate.objects.filter(lane=lane)
        print(f"  Rates: {rates.count()}")
        for rate in rates:
            print(f"    - {rate.service_component.code}: {rate.rate_per_kg_fcy} / {rate.rate_per_shipment_fcy}")

    print("\nChecking Components...")
    comps = ServiceComponent.objects.filter(code__in=['PICKUP_SELL', 'FRT_AIR_EXP'])
    for c in comps:
        print(f"Component {c.code} exists. ID: {c.id}")

if __name__ == "__main__":
    check_data()
