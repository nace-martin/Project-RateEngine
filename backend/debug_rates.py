
import os
import django
import sys

# Setup Django environment
sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rate_engine.settings')
django.setup()

from core.models import Location
from pricing_v3.models import Zone, ZoneMember, RateCard, RateLine
from django.db.models import Q

def check_rates():
    print("--- Debugging Rates for BNE -> POM ---")

    bne = Location.objects.filter(code='BNE').first()
    pom = Location.objects.filter(code='POM').first()
    
    if not bne or not pom:
        print("Locations missing.")
        return

    bne_zones = Zone.objects.filter(members__location=bne)
    pom_zones = Zone.objects.filter(members__location=pom)

    cards = RateCard.objects.filter(
        origin_zone__in=bne_zones,
        destination_zone__in=pom_zones,
        mode='AIR'
    )

    print(f"Found {cards.count()} matching cards.")
    
    for card in cards:
        print(f"Card: {card.name} (ID: {card.id})")
        print(f"  Valid: {card.valid_from} to {card.valid_until}")
        print(f"  Currency: {card.currency}")
        
        lines = card.lines.all()
        print(f"  Lines ({lines.count()}):")

        for line in lines:
            print(f"    - {line.component.code}: {line.method}")
            if line.component.code == 'AGENCY_EXP':
                for b in line.breaks.all():
                    print(f"      Break: {b.from_value}-{b.to_value} = {b.rate}")

if __name__ == '__main__':
    check_rates()
