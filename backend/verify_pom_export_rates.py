
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
    output_path = r'c:\Users\commercial.manager\dev\Project-RateEngine\backend\verify_pom_internal_output.txt'
    try:
        with open(output_path, 'w') as f:
            def log(msg):
                print(msg)
                f.write(msg + '\n')
                
            log("Verifying EFM POM Export Sell Rates 2025...")
            
            cards = PartnerRateCard.objects.filter(name='EFM POM Export Sell Rates 2025')
            if not cards.exists():
                log("ERROR: No rate cards found!")
                return

            for card in cards:
                log(f"\nChecking Card: {card.name}")
                
                # Check Freight Rates
                rates = PartnerRate.objects.filter(lane__rate_card=card, service_component__code='FRT_AIR_EXP')
                log(f"Found {rates.count()} Freight Rates")
                for rate in rates:
                    log(f"  Dest: {rate.lane.destination_airport.code} | Min: {rate.min_charge_fcy} | Tiering: {rate.tiering_json is not None}")
                    
                # Check Additional Charges
                other_comps = [
                    'DOC_EXP_SELL', 'AWB_FEE_SELL', 'SECURITY_SELL', 'TERM_EXP_SELL', 
                    'BUILD_UP', 'VALUABLE_HANDLING', 'DG_ACCEPTANCE', 
                    'CLEARANCE_SELL', 'AGENCY_EXP_SELL', 'CUSTOMS_ENTRY', 'PICKUP_SELL'
                ]
                
                log("\nChecking Additional Charges:")
                for code in other_comps:
                    rates = PartnerRate.objects.filter(lane__rate_card=card, service_component__code=code)
                    if rates.exists():
                        rate = rates.first()
                        val = f"${rate.rate_per_kg_fcy}/kg" if rate.rate_per_kg_fcy else f"${rate.rate_per_shipment_fcy} FLAT"
                        log(f"  {code}: Found - {val} (Min: {rate.min_charge_fcy}, Max: {rate.max_charge_fcy})")
                    else:
                        log(f"  {code}: MISSING!")
    except Exception as e:
        print(f"ERROR: {e}")

if __name__ == '__main__':
    verify_rates()
