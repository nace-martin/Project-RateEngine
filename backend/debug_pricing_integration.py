
import os
import django
import sys
import uuid
from decimal import Decimal

# Setup Django environment
sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rate_engine.settings')
django.setup()

from pricing_v2.pricing_service_v3 import PricingServiceV3
from pricing_v2.dataclasses_v3 import QuoteInput, ShipmentDetails, Piece, LocationRef
from services.models import ServiceComponent

def debug_integration():
    print("Debugging Pricing Integration for 300kg Shipment...")
    
    # 1. Setup Mock Data
    syd_ref = LocationRef(
        id=uuid.uuid4(),
        code='SYD',
        name='Sydney',
        country_code='AU',
        currency_code='AUD'
    )
    
    pom_ref = LocationRef(
        id=uuid.uuid4(),
        code='POM',
        name='Port Moresby',
        country_code='PG',
        currency_code='PGK'
    )
    
    # 300kg shipment (1 piece)
    # Dimensions: 100x100x100cm (fits B737 dims, but weight 300kg > 250kg)
    piece = Piece(
        pieces=1,
        length_cm=Decimal("100.0"),
        width_cm=Decimal("100.0"),
        height_cm=Decimal("100.0"),
        gross_weight_kg=Decimal("300.0")
    )
    
    shipment = ShipmentDetails(
        mode='AIR',
        shipment_type='IMPORT',
        incoterm='EXW',
        payment_term='PREPAID',
        is_dangerous_goods=False,
        pieces=[piece],
        service_scope='D2D',
        origin_location=syd_ref,
        destination_location=pom_ref
    )
    
    quote_input = QuoteInput(
        customer_id=uuid.uuid4(),
        contact_id=uuid.uuid4(),
        output_currency='PGK',
        shipment=shipment
    )
    
    # 2. Instantiate Service
    print("\nInstantiating PricingServiceV3...")
    service = PricingServiceV3(quote_input)
    
    # 3. Check Routing Determination
    print(f"\nRequired Service Level: {service.required_service_level}")
    print(f"Routing Reason: {service.routing_reason}")
    
    if service.required_service_level == 'VIA_BNE':
        print("SUCCESS: Routing correctly determined as VIA_BNE.")
    else:
        print(f"FAILURE: Routing determined as {service.required_service_level}.")
        
    # 4. Check Rate Selection
    try:
        frt_air = ServiceComponent.objects.get(code='FRT_AIR')
        print(f"\nFetching Buy Rate for {frt_air.code}...")
        
        buy_rate = service._get_buy_rate(frt_air)
        
        if buy_rate:
            print(f"Rate Found: {buy_rate}")
            print(f"Rate Card: {buy_rate.lane.rate_card.name}")
            print(f"Service Level: {buy_rate.lane.rate_card.service_level}")
            
            if buy_rate.lane.rate_card.service_level == 'VIA_BNE':
                print("SUCCESS: Correct rate card selected.")
            else:
                print("FAILURE: Incorrect rate card selected.")
        else:
            print("FAILURE: No rate found.")
            
    except ServiceComponent.DoesNotExist:
        print("ERROR: FRT_AIR component not found.")

if __name__ == '__main__':
    debug_integration()
