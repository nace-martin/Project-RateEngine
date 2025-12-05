import os
import django
from decimal import Decimal
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "rate_engine.settings")
django.setup()

from ratecards.models import PartnerRateLane, PartnerRate
from services.models import ServiceComponent
from core.models import Location

def check_import_rates():
    print("Checking BNE -> POM Import Rates...")
    
    try:
        bne = Location.objects.get(code='BNE')
        pom = Location.objects.get(code='POM')
    except Location.DoesNotExist:
        print("Locations not found")
        return

    lanes = PartnerRateLane.objects.filter(
        origin_airport=bne.airport,
        destination_airport=pom.airport,
        mode='AIR'
    )
    
    print(f"Found {lanes.count()} lanes.")
    
    for lane in lanes:
        print(f"\nLane {lane.id}: {lane.rate_card.name} ({lane.rate_card.currency_code})")
        print(f"Shipment Type: {lane.shipment_type}")
        
        # Check specific destination components
        dest_comps = ['AGENCY_IMP', 'CLEARANCE', 'DOC_IMP', 'HANDLING', 'TERM_INTL']
        
        for code in dest_comps:
            comp = ServiceComponent.objects.filter(code=code).first()
            if not comp:
                print(f"  Component {code} not found in DB")
                continue
                
            rates = PartnerRate.objects.filter(lane=lane, service_component=comp)
            if rates.exists():
                for rate in rates:
                    print(f"  - {code}: Min={rate.min_charge_fcy}, PerKg={rate.rate_per_kg_fcy}, Unit={rate.unit}")
            else:
                print(f"  - {code}: NO RATE")

if __name__ == "__main__":
    check_import_rates()
