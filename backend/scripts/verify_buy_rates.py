
import os
import sys
import django

sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rate_engine.settings')
django.setup()

from ratecards.models import PartnerRate, PartnerRateLane, PartnerRateCard

def run():
    print("--- Verifying Buy Rates ---")
    card = PartnerRateCard.objects.get(name__contains='Buy')
    print(f"Card: {card.name}")
    
    lanes = PartnerRateLane.objects.filter(rate_card=card)
    print(f"Lanes: {lanes.count()}")
    
    # Check one lane (BNE)
    bne_lane = lanes.filter(destination_airport__iata_code='BNE').first()
    if bne_lane:
        print(f"\n{bne_lane}:")
        rates = PartnerRate.objects.filter(lane=bne_lane)
        for r in rates:
            print(f"  {r.service_component.code}: kg={r.rate_per_kg_fcy}, flat={r.rate_per_shipment_fcy}, min={r.min_charge_fcy}")

if __name__ == "__main__":
    run()
