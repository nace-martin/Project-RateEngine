
import os
import sys
import django
from decimal import Decimal

sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rate_engine.settings')
django.setup()

from ratecards.models import PartnerRate, PartnerRateLane, PartnerRateCard
from services.models import ServiceComponent

def run():
    print("--- Inspecting Sell Rates for POM->BNE ---")
    
    card_name = "PX Export Sell Rates 2024"
    try:
        card = PartnerRateCard.objects.get(name=card_name)
    except PartnerRateCard.DoesNotExist:
        print(f"Card {card_name} not found!")
        return

    # Find lane POM -> BNE
    lanes = PartnerRateLane.objects.filter(
        rate_card=card, 
        origin_airport__iata_code='POM', 
        destination_airport__iata_code='BNE'
    )
    if not lanes.exists():
        print("No Lane found for POM->BNE")
        return
        
    lane = lanes.first()
    print(f"Lane: {lane}")
    
    components = ['SEC_EXP_MXC', 'HND_EXP_BPC', 'DOC_EXP_AWB', 'AGENCY_EXP', 'CLEAR_EXP']
    
    for code in components:
        try:
            comp = ServiceComponent.objects.get(code=code)
            rates = PartnerRate.objects.filter(lane=lane, service_component=comp)
            
            sc_str = "None"
            if comp.service_code:
                sc_str = f"{comp.service_code.code} (Method: {comp.service_code.pricing_method})"
            
            for r in rates:
                print(f"[{code}] Rate: Kg={r.rate_per_kg_fcy} Shipment={r.rate_per_shipment_fcy} Min={r.min_charge_fcy} CostType={comp.cost_type} SC={sc_str}")
        except ServiceComponent.DoesNotExist:
            print(f"Component {code} not found")

if __name__ == "__main__":
    run()
