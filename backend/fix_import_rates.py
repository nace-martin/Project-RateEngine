import os
import django
from decimal import Decimal
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "rate_engine.settings")
django.setup()

from ratecards.models import PartnerRateCard, PartnerRateLane, PartnerRate
from services.models import ServiceComponent
from core.models import Location

def fix_import_rates():
    print("Fixing BNE -> POM Import Rates...")
    
    try:
        bne = Location.objects.get(code='BNE')
        pom = Location.objects.get(code='POM')
    except Location.DoesNotExist:
        print("Locations not found")
        return

    # 1. Create PGK Rate Card for Local Charges
    pgk_card, created = PartnerRateCard.objects.get_or_create(
        name="POM Import Local Charges (PGK)",
        defaults={
            "currency_code": "PGK",
            "description": "Local destination charges for Import to POM",
            "is_active": True
        }
    )
    if created:
        print(f"Created Rate Card: {pgk_card.name}")
    else:
        print(f"Found Rate Card: {pgk_card.name}")

    # 2. Create Lane BNE->POM in PGK Card
    # Note: We use 'GENERAL' shipment_type as per model
    pgk_lane, created = PartnerRateLane.objects.get_or_create(
        rate_card=pgk_card,
        origin_airport=bne.airport,
        destination_airport=pom.airport,
        defaults={
            "mode": "AIR",
            "shipment_type": "GENERAL"
        }
    )
    if created:
        print(f"Created Lane {pgk_lane.id} in PGK Card")
    else:
        print(f"Found Lane {pgk_lane.id} in PGK Card")

    # 3. Move Destination Charges to this Lane
    dest_comps = ['AGENCY_IMP', 'CLEARANCE', 'DOC_IMP', 'HANDLING', 'TERM_INTL']
    
    for code in dest_comps:
        comp = ServiceComponent.objects.filter(code=code).first()
        if not comp:
            print(f"Component {code} not found")
            continue
            
        # Find existing rates for this component on ANY BNE->POM lane
        # But exclude the PGK lane we just created/found (to avoid moving them if already there)
        rates = PartnerRate.objects.filter(
            lane__origin_airport=bne.airport,
            lane__destination_airport=pom.airport,
            service_component=comp
        ).exclude(lane=pgk_lane)
        
        count = rates.count()
        if count > 0:
            print(f"Moving {count} rates for {code} to PGK Lane...")
            # We can't just update the lane because 'lane' is a ForeignKey.
            # We can update the 'lane' field.
            rates.update(lane=pgk_lane)
            print("Done.")
        else:
            print(f"No rates found for {code} to move (or already in PGK lane).")

if __name__ == "__main__":
    fix_import_rates()
