"""Add 10% fuel surcharge rates for PICKUP_FUEL_DST"""
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rate_engine.settings')
django.setup()

from decimal import Decimal
from services.models import ServiceComponent
from ratecards.models import PartnerRate

fuel_dst = ServiceComponent.objects.get(code='PICKUP_FUEL_DST')
cartage_rates = PartnerRate.objects.filter(service_component__code='CARTAGE')

print(f'Found {cartage_rates.count()} CARTAGE rates')
print('Adding 10% fuel rates for PICKUP_FUEL_DST...')

added = 0
for cr in cartage_rates:
    lane = cr.lane
    if not PartnerRate.objects.filter(lane=lane, service_component=fuel_dst).exists():
        PartnerRate.objects.create(
            lane=lane, 
            service_component=fuel_dst, 
            unit='SHIPMENT',
            rate_per_shipment_fcy=Decimal('10.00')  # 10% fuel surcharge
        )
        added += 1
        print(f'  Created rate on lane {lane.id}')

print(f'\nAdded {added} fuel surcharge rates')
print(f'Total PICKUP_FUEL_DST rates: {PartnerRate.objects.filter(service_component=fuel_dst).count()}')
