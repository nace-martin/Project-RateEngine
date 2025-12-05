
import os
import django
import sys
from decimal import Decimal

# Setup Django environment
sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rate_engine.settings')
django.setup()

from ratecards.models import PartnerRateCard, PartnerRate

def debug_rate_calculation():
    print("Debugging Rate Calculation for SYD-POM Direct...")
    
    # 1. Get the Direct Rate Card
    try:
        card = PartnerRateCard.objects.get(name='EFM AU Import Rates 2025 (Direct)')
    except PartnerRateCard.DoesNotExist:
        print("ERROR: Rate card not found!")
        return

    # 2. Get the FRT_AIR rate
    try:
        rate = PartnerRate.objects.get(lane__rate_card=card, service_component__code='FRT_AIR')
    except PartnerRate.DoesNotExist:
        print("ERROR: FRT_AIR rate not found!")
        return

    print(f"Rate found: {rate}")
    print(f"Tiering JSON: {rate.tiering_json}")

    # 3. Simulate Logic
    chargeable_weight = Decimal("100.00")
    print(f"\nSimulating for Chargeable Weight: {chargeable_weight} kg")

    data = rate.tiering_json
    if isinstance(data, dict) and data.get("type") == "weight_break":
        breaks = data.get("breaks", [])
        if breaks:
            selected_rate = None
            sorted_breaks = sorted(
                breaks,
                key=lambda x: Decimal(str(x.get("min_kg", "0"))),
                reverse=True,
            )
            
            print("Sorted Breaks:")
            for b in sorted_breaks:
                print(f"  Min: {b.get('min_kg')}, Rate: {b.get('rate_per_kg')}")

            for tier in sorted_breaks:
                min_kg = Decimal(str(tier.get("min_kg", "0")))
                if chargeable_weight >= min_kg:
                    selected_rate = Decimal(str(tier.get("rate_per_kg")))
                    print(f"  MATCH! {chargeable_weight} >= {min_kg}. Selected Rate: {selected_rate}")
                    break
            
            if selected_rate is None:
                print("  No match found, using Min Charge?")
            else:
                print(f"  Final Selected Rate: {selected_rate}")
                
                expected_rate = Decimal("6.75")
                if selected_rate == expected_rate:
                    print("  SUCCESS: Matches expected rate.")
                else:
                    print(f"  FAILURE: Expected {expected_rate}, got {selected_rate}")

if __name__ == '__main__':
    debug_rate_calculation()
