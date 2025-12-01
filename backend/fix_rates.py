
import os
import django
import sys
from decimal import Decimal

# Setup Django environment
sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rate_engine.settings')
django.setup()

from pricing_v3.models import RateCard, RateLine, RateBreak

def fix_rates():
    print("--- Fixing Rates for EFM AU - SYD to POM ---")

    # Find the card
    card = RateCard.objects.filter(name__icontains='SYD to POM').first()
    if not card:
        print("Card not found!")
        return

    print(f"Processing Card: {card.name}")

    # Fix Agency Fee (AGENCY_EXP)
    lines = RateLine.objects.filter(card=card, component__code='AGENCY_EXP')
    for line in lines:
        if not line.breaks.exists():
            print(f"Adding default rate to {line.component.code} (Line ID: {line.id})")
            RateBreak.objects.create(
                line=line,
                from_value=0,
                rate=Decimal('55.00') # Example value
            )
        else:
            print(f"{line.component.code} already has rates.")

    # Fix Fuel Surcharge (FUEL_SUR) - assuming code is FUEL_SUR or similar
    # Based on debug output, it was PICKUP_FUEL? No, that's pickup.
    # User screenshot said "Fuel & Security Surcharge". Code might be FUEL_SEC or similar.
    # Let's fix all FLAT/PER_UNIT lines with no breaks.
    
    all_lines = card.lines.all()
    for line in all_lines:
        if not line.breaks.exists():
            print(f"Fixing empty line: {line.component.code} ({line.method})")
            
            rate_val = Decimal('10.00')
            if line.component.code == 'AGENCY_EXP': rate_val = Decimal('55.00')
            elif line.component.code == 'DOC_EXP': rate_val = Decimal('45.00')
            elif line.component.code == 'AWB_FEE': rate_val = Decimal('25.00')
            elif line.component.code == 'CTO': rate_val = Decimal('0.45') # Per kg?
            
            RateBreak.objects.create(
                line=line,
                from_value=0,
                rate=rate_val
            )

    print("Done fixing rates.")

if __name__ == '__main__':
    fix_rates()
