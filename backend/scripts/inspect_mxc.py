
import os
import sys
import django
from decimal import Decimal

sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rate_engine.settings')
django.setup()

from ratecards.models import PartnerRate, PartnerRateLane
from services.models import ServiceComponent

def run():
    print("--- Inspecting SEC_EXP_MXC Rate Data ---")
    
    # Get component
    try:
        comp = ServiceComponent.objects.get(code='SEC_EXP_MXC')
        print(f"Component: {comp.description} (cost_type={comp.cost_type})")
    except ServiceComponent.DoesNotExist:
        print("SEC_EXP_MXC not found!")
        return
    
    # Get lane for POM->BNE
    lanes = PartnerRateLane.objects.filter(
        origin_airport__iata_code='POM',
        destination_airport__iata_code='BNE'
    )
    
    if not lanes.exists():
        print("No lanes found for POM->BNE")
        return
    
    for lane in lanes:
        print(f"\nLane: {lane} (Card: {lane.rate_card.name})")
        
        rates = PartnerRate.objects.filter(lane=lane, service_component=comp)
        for r in rates:
            print(f"  Rate per KG: {r.rate_per_kg_fcy}")
            print(f"  Rate per Shipment: {r.rate_per_shipment_fcy}")
            print(f"  Min Charge: {r.min_charge_fcy}")
            print(f"  Max Charge: {r.max_charge_fcy}")
            
            # Simulate calculation for 166.67 kg (the test case)
            cw = Decimal("166.67")
            cost = Decimal("0.00")
            
            if r.rate_per_kg_fcy:
                cost += r.rate_per_kg_fcy * cw
                print(f"  -> Per KG Calc: {r.rate_per_kg_fcy} * {cw} = {r.rate_per_kg_fcy * cw}")
            
            if r.rate_per_shipment_fcy:
                cost += r.rate_per_shipment_fcy
                print(f"  -> Per Shipment Add: {r.rate_per_shipment_fcy}")
            
            print(f"  -> Raw Cost: {cost}")
            
            if r.min_charge_fcy and cost < r.min_charge_fcy:
                print(f"  -> Min Charge Applied: {r.min_charge_fcy}")
                cost = r.min_charge_fcy
            
            print(f"  => FINAL COST: {cost}")

if __name__ == "__main__":
    run()
