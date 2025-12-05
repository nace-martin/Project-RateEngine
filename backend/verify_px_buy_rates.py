
import os
import django
import sys
from decimal import Decimal

# Setup Django environment
sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rate_engine.settings')
django.setup()

from ratecards.models import PartnerRateCard, PartnerRate

def verify_px_buy_rates():
    output_path = r'c:\Users\commercial.manager\dev\Project-RateEngine\backend\verify_px_output.txt'
    try:
        with open(output_path, 'w') as f:
            def log(msg):
                print(msg)
                f.write(msg + '\n')
                
            log("Verifying PX Export Buy Rates 2025...")
            
            cards = PartnerRateCard.objects.filter(name='PX Export Buy Rates 2025')
            if not cards.exists():
                log("ERROR: No rate cards found!")
                return

            card = cards.first()
            log(f"Found Card: {card.name}")

            # Check Security Surcharge (Composite)
            sec_rates = PartnerRate.objects.filter(lane__rate_card=card, service_component__code='SECURITY_SELL')
            if sec_rates.exists():
                rate = sec_rates.first()
                log(f"SECURITY_SELL: Kg={rate.rate_per_kg_fcy}, Shipment={rate.rate_per_shipment_fcy}, Min={rate.min_charge_fcy}")
                if rate.rate_per_kg_fcy and rate.rate_per_shipment_fcy:
                    log("  SUCCESS: Composite rate detected.")
                else:
                    log("  FAILURE: Composite rate missing.")
            else:
                log("SECURITY_SELL: MISSING!")

            # Check Tiered Build-Up
            bu_rates = PartnerRate.objects.filter(lane__rate_card=card, service_component__code='BUILD_UP')
            if bu_rates.exists():
                rate = bu_rates.first()
                log(f"BUILD_UP: Tiering={rate.tiering_json is not None}")
                if rate.tiering_json:
                    log(f"  Breaks: {len(rate.tiering_json.get('breaks', []))}")
            else:
                log("BUILD_UP: MISSING!")

    except Exception as e:
        print(f"ERROR: {e}")

if __name__ == '__main__':
    verify_px_buy_rates()
