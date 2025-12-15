"""
Create BUY_RATE card for Export lanes.
The pricing engine's _get_buy_rate() filters by rate_type='BUY_RATE'.
"""
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rate_engine.settings')
django.setup()

from decimal import Decimal
from django.utils import timezone
from core.models import Airport
from ratecards.models import PartnerRateCard, PartnerRateLane, PartnerRate
from services.models import ServiceComponent

# Get supplier from existing card
from parties.models import Company
existing_card = PartnerRateCard.objects.first()
supplier = existing_card.supplier

# Create Export BUY_RATE card
card, created = PartnerRateCard.objects.get_or_create(
    name='PX Export Buy Rates 2024',
    defaults={
        'rate_type': 'BUY_RATE',
        'currency_code': 'PGK',
        'valid_from': timezone.now().date(),
        'supplier': supplier,
    }
)
print(f'BUY Rate Card: {card.name} ({"created" if created else "exists"})')



# Get POM airport
pom = Airport.objects.get(iata_code='POM')

# Export freight rates (POM -> destinations)
FREIGHT_RATES = {
    'BNE': {'min': 200, 'normal': 7.90, '100kg': 7.40, '200kg': 7.15, '500kg': 6.75},
    'CNS': {'min': 200, 'normal': 6.25, '100kg': 6.15, '200kg': 5.90, '500kg': 5.90},
    'SYD': {'min': 200, 'normal': 10.00, '100kg': 9.40, '200kg': 8.90, '500kg': 8.50},
    'HKG': {'min': 200, 'normal': 25.65, '100kg': 19.25, '200kg': 19.25, '500kg': 19.25},
    'MNL': {'min': 200, 'normal': 13.00, '100kg': 10.00, '200kg': 10.00, '500kg': 10.00},
    'HIR': {'min': 200, 'normal': 7.95, '100kg': 6.00, '200kg': 6.00, '500kg': 6.00},
    'SIN': {'min': 200, 'normal': 17.65, '100kg': 13.25, '200kg': 13.25, '500kg': 13.25},
    'VLI': {'min': 200, 'normal': 17.50, '100kg': 12.00, '200kg': 10.90, '500kg': 10.90},
    'NAN': {'min': 200, 'normal': 20.40, '100kg': 15.25, '200kg': 15.25, '500kg': 15.25},
}

print('Creating Export BUY lanes...')

for dest_code, rates in FREIGHT_RATES.items():
    dest = Airport.objects.filter(iata_code=dest_code).first()
    if not dest:
        print(f'  {dest_code}: Airport not found')
        continue
    
    # Create lane
    lane, _ = PartnerRateLane.objects.get_or_create(
        rate_card=card,
        origin_airport=pom,
        destination_airport=dest,
        mode='AIR',
        direction='EXPORT',
        defaults={
            'payment_term': 'ANY',
            'shipment_type': 'GENERAL',
        }
    )
    print(f'  Lane: POM -> {dest_code}')
    
    # FRT_AIR or FRT_AIR_EXP
    frt = ServiceComponent.objects.filter(code='FRT_AIR').first()
    if frt:
        PartnerRate.objects.update_or_create(
            lane=lane,
            service_component=frt,
            defaults={
                'unit': 'KG',
                'rate_per_kg_fcy': Decimal(str(rates['normal'])),
                'min_charge_fcy': Decimal(str(rates['min'])),
            }
        )
    
    # Add terminal/clearance/pickup as needed for cost calculation
    # AWB Fee
    awb = ServiceComponent.objects.filter(code='AWB_FEE').first()
    if awb:
        PartnerRate.objects.update_or_create(
            lane=lane, service_component=awb,
            defaults={'unit': 'SHIPMENT', 'rate_per_shipment_fcy': Decimal('35.00')}
        )
    
    # Pickup 
    pickup = ServiceComponent.objects.filter(code='PICKUP').first()
    if pickup:
        PartnerRate.objects.update_or_create(
            lane=lane, service_component=pickup,
            defaults={
                'unit': 'KG',
                'rate_per_kg_fcy': Decimal('1.50'),
                'min_charge_fcy': Decimal('95.00'),
                'max_charge_fcy': Decimal('500.00'),
            }
        )
    
    # Pickup Fuel
    fuel_org = ServiceComponent.objects.filter(code='PICKUP_FUEL_ORG').first()
    if fuel_org:
        PartnerRate.objects.update_or_create(
            lane=lane, service_component=fuel_org,
            defaults={'unit': 'SHIPMENT', 'rate_per_shipment_fcy': Decimal('10.00')}
        )

print()
print(f'BUY lanes created: {card.lanes.count()}')
print(f'Total rates: {PartnerRate.objects.filter(lane__rate_card=card).count()}')
