"""
Update Export SELL rates with correct values from user's rate sheet.

Clearance and Cartage Charges:
- Customs Clearance: K300.00 per AWB
- Agency Fee: K250.00 per AWB

Pick up Fee:
- K1.50/kg, min K95.00, max K500.00
"""
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rate_engine.settings')
django.setup()

from decimal import Decimal
from ratecards.models import PartnerRateCard, PartnerRate
from services.models import ServiceComponent

# Get SELL rate card
sell_card = PartnerRateCard.objects.filter(rate_type='SELL_RATE', name__icontains='Export').first()
if not sell_card:
    sell_card = PartnerRateCard.objects.filter(rate_type='SELL_RATE').first()

print(f'SELL Card: {sell_card.name}')

# Define correct SELL rates
SELL_RATES = {
    'CLEARANCE_SELL': {
        'unit': 'SHIPMENT',
        'rate_per_shipment_fcy': Decimal('300.00'),
    },
    'AGENCY_EXP_SELL': {
        'unit': 'SHIPMENT',
        'rate_per_shipment_fcy': Decimal('250.00'),
    },
    'PICKUP': {
        'unit': 'KG',
        'rate_per_kg_fcy': Decimal('1.50'),
        'min_charge_fcy': Decimal('95.00'),
        'max_charge_fcy': Decimal('500.00'),
    },
}

for lane in sell_card.lanes.filter(direction='EXPORT'):
    print(f'Lane: {lane.origin_airport.iata_code} -> {lane.destination_airport.iata_code}')
    
    for code, config in SELL_RATES.items():
        comp = ServiceComponent.objects.filter(code=code).first()
        if not comp:
            print(f'  {code}: Component not found')
            continue
        
        defaults = {
            'unit': config['unit'],
            'rate_per_shipment_fcy': config.get('rate_per_shipment_fcy'),
            'rate_per_kg_fcy': config.get('rate_per_kg_fcy'),
            'min_charge_fcy': config.get('min_charge_fcy'),
            'max_charge_fcy': config.get('max_charge_fcy'),
        }
        
        rate, created = PartnerRate.objects.update_or_create(
            lane=lane,
            service_component=comp,
            defaults=defaults
        )
        print(f'  {code}: {"created" if created else "updated"} - {config}')

print()
print('=== Done ===')
