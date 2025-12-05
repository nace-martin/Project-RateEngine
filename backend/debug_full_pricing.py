import os
import django
import sys

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "rate_engine.settings")
django.setup()

from services.models import ServiceRule, ServiceComponent
from ratecards.models import PartnerRateCard, PartnerRateLane, PartnerRate
from core.models import Location

def debug_full_pricing():
    print("=" * 80)
    print("FULL PRICING DEBUG FOR POM → BNE EXPORT D2D EXW PREPAID")
    print("=" * 80)
    
    # 1. Check ServiceRule
    print("\n1. CHECKING SERVICE RULE...")
    rule = ServiceRule.objects.filter(
        mode='AIR',
        direction='EXPORT',
        incoterm='EXW',
        payment_term='PREPAID',
        service_scope='D2D',
        is_active=True
    ).first()
    
    if not rule:
        print("❌ CRITICAL: No ServiceRule found for AIR/EXPORT/EXW/PREPAID/D2D")
        return
    
    print(f"✓ Found ServiceRule: {rule.id}")
    print(f"  - Description: {rule.description}")
    print(f"  - Output Currency: {rule.output_currency_type}")
    
    # 2. Check Components in Rule
    print("\n2. CHECKING RULE COMPONENTS...")
    rule_components = rule.rule_components.all().select_related('service_component')
    print(f"  - Total components: {rule_components.count()}")
    
    component_codes = []
    for rc in rule_components:
        comp = rc.service_component
        print(f"  - {comp.code}: {comp.description}")
        print(f"    Active: {comp.is_active}, Cost Source: {comp.cost_source}")
        component_codes.append(comp.code)
    
    if not component_codes:
        print("❌ CRITICAL: No components in rule!")
        return
    
    # 3. Check Locations
    print("\n3. CHECKING LOCATIONS...")
    try:
        pom = Location.objects.get(code='POM')
        bne = Location.objects.get(code='BNE')
        print(f"✓ POM: {pom.name}, Airport: {pom.airport}")
        print(f"✓ BNE: {bne.name}, Airport: {bne.airport}")
        
        if not pom.airport or not bne.airport:
            print("❌ CRITICAL: Locations missing airport links!")
            return
            
        print(f"  - POM Airport IATA: {pom.airport.iata_code}")
        print(f"  - BNE Airport IATA: {bne.airport.iata_code}")
    except Location.DoesNotExist as e:
        print(f"❌ CRITICAL: Location not found: {e}")
        return
    
    # 4. Check Rate Cards
    print("\n4. CHECKING RATE CARDS...")
    rate_cards = PartnerRateCard.objects.all()
    print(f"  - Total rate cards: {rate_cards.count()}")
    for card in rate_cards:
        print(f"  - {card.name} ({card.currency_code})")
    
    # 5. Check Lanes
    print("\n5. CHECKING LANES FOR POM → BNE...")
    lanes = PartnerRateLane.objects.filter(
        origin_airport__iata_code='POM',
        destination_airport__iata_code='BNE'
    )
    print(f"  - Found {lanes.count()} lanes")
    
    for lane in lanes:
        print(f"  - Lane ID: {lane.id}")
        print(f"    Rate Card: {lane.rate_card.name}")
        print(f"    Mode: {lane.mode}")
        print(f"    Shipment Type: {lane.shipment_type}")
        print(f"    Origin: {lane.origin_airport}")
        print(f"    Destination: {lane.destination_airport}")
        
        # Check rates on this lane
        rates = PartnerRate.objects.filter(lane=lane)
        print(f"    Total rates: {rates.count()}")
        
        for rate in rates:
            print(f"      - {rate.service_component.code}: "
                  f"Unit={rate.unit}, "
                  f"Min={rate.min_charge_fcy}, "
                  f"PerKg={rate.rate_per_kg_fcy}, "
                  f"PerShipment={rate.rate_per_shipment_fcy}")
    
    if lanes.count() == 0:
        print("❌ CRITICAL: No lanes found for POM → BNE!")
        return
    
    # 6. Check if rates exist for each component
    print("\n6. CHECKING RATES FOR EACH COMPONENT...")
    lane = lanes.first()
    
    for comp_code in component_codes:
        comp = ServiceComponent.objects.filter(code=comp_code).first()
        if not comp:
            print(f"  ❌ {comp_code}: Component not found in database!")
            continue
            
        # Try to find rate
        rate = PartnerRate.objects.filter(
            lane__origin_airport__iata_code='POM',
            lane__destination_airport__iata_code='BNE',
            lane__mode='AIR',
            service_component=comp
        ).first()
        
        if rate:
            print(f"  ✓ {comp_code}: Rate found on lane {rate.lane.id}")
            print(f"    Min: {rate.min_charge_fcy}, PerKg: {rate.rate_per_kg_fcy}, "
                  f"PerShipment: {rate.rate_per_shipment_fcy}")
        else:
            print(f"  ❌ {comp_code}: NO RATE FOUND!")
            print(f"    Tried filter: lane__origin='POM', lane__dest='BNE', "
                  f"lane__mode='AIR', component={comp.id}")
    
    print("\n" + "=" * 80)
    print("DEBUG COMPLETE")
    print("=" * 80)

if __name__ == "__main__":
    debug_full_pricing()
