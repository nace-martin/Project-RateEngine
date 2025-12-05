
import os
import django
import sys
from decimal import Decimal

# Setup Django environment
sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rate_engine.settings')
django.setup()

from ratecards.models import PartnerRateCard, PartnerRate

def verify_rates():
    print("Verifying EFM AU Import Rates 2025...")
    
    cards = PartnerRateCard.objects.filter(name__startswith='EFM AU Import Rates 2025')
    if not cards.exists():
        print("ERROR: No rate cards found!")
        return

    for card in cards:
        print(f"\nChecking Card: {card.name}")
        print(f"  Service Level: {card.service_level}")
        
        rates = PartnerRate.objects.filter(lane__rate_card=card, service_component__code='FRT_AIR')
        for rate in rates:
            print(f"  FRT_AIR Rate:")
            print(f"    Min Charge: {rate.min_charge_fcy}")
            print(f"    Base Rate: {rate.rate_per_kg_fcy}")
            print(f"    Tiering JSON: {rate.tiering_json}")
            
            if not rate.tiering_json:
                print("    ERROR: Missing tiering_json!")
            else:
                print("    Tiering JSON present.")

        # Check other components
        other_comps = ['PICKUP', 'XRAY', 'CTO', 'DOC_EXP', 'AGENCY_EXP', 'AWB_FEE', 'CLEARANCE', 'AGENCY_IMP', 'DOC_IMP', 'HANDLING', 'TERM_INT', 'CARTAGE']
        for code in other_comps:
            rates = PartnerRate.objects.filter(lane__rate_card=card, service_component__code=code)
            if rates.exists():
                rate = rates.first()
                print(f"  {code} Rate: Found - ${rate.min_charge_fcy} MIN / {f'${rate.rate_per_kg_fcy}/kg' if rate.rate_per_kg_fcy else f'${rate.rate_per_shipment_fcy} FLAT'}")
            else:
                print(f"  {code} Rate: MISSING!")

if __name__ == '__main__':
    verify_rates()
