"""Add 10% fuel surcharge rates to ALL lanes (Import and Export)"""
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rate_engine.settings')
django.setup()

from decimal import Decimal
from services.models import ServiceComponent
from ratecards.models import PartnerRate, PartnerRateLane

fuel_org = ServiceComponent.objects.get(code='PICKUP_FUEL_ORG')
fuel_dst = ServiceComponent.objects.get(code='PICKUP_FUEL_DST')

print('=== Adding Fuel Surcharge Rates to ALL Lanes ===')
print(f'PICKUP_FUEL_ORG linked to: {fuel_org.percent_of_component}')
print(f'PICKUP_FUEL_DST linked to: {fuel_dst.percent_of_component}')
print()

# Get all active lanes
lanes = PartnerRateLane.objects.all()
print(f'Total lanes: {lanes.count()}')

added_org = 0
added_dst = 0

for lane in lanes:
    # Add PICKUP_FUEL_ORG rate if doesn't exist
    if not PartnerRate.objects.filter(lane=lane, service_component=fuel_org).exists():
        PartnerRate.objects.create(
            lane=lane,
            service_component=fuel_org,
            unit='SHIPMENT',
            rate_per_shipment_fcy=Decimal('10.00')  # 10% fuel surcharge
        )
        added_org += 1
        print(f'  ORG: {lane.origin_airport.iata_code}->{lane.destination_airport.iata_code} {lane.direction}')
    
    # Add PICKUP_FUEL_DST rate if doesn't exist
    if not PartnerRate.objects.filter(lane=lane, service_component=fuel_dst).exists():
        PartnerRate.objects.create(
            lane=lane,
            service_component=fuel_dst,
            unit='SHIPMENT',
            rate_per_shipment_fcy=Decimal('10.00')  # 10% fuel surcharge
        )
        added_dst += 1
        print(f'  DST: {lane.origin_airport.iata_code}->{lane.destination_airport.iata_code} {lane.direction}')

print()
print(f'Added {added_org} PICKUP_FUEL_ORG rates')
print(f'Added {added_dst} PICKUP_FUEL_DST rates')
print()
print('=== FINAL COUNTS ===')
print(f'PICKUP_FUEL_ORG: {PartnerRate.objects.filter(service_component=fuel_org).count()} rates')
print(f'PICKUP_FUEL_DST: {PartnerRate.objects.filter(service_component=fuel_dst).count()} rates')

# Show coverage by direction
print()
print('=== COVERAGE BY DIRECTION ===')
import_with_fuel = PartnerRate.objects.filter(service_component=fuel_org, lane__direction='IMPORT').count()
export_with_fuel = PartnerRate.objects.filter(service_component=fuel_org, lane__direction='EXPORT').count()
print(f'IMPORT lanes with fuel: {import_with_fuel}')
print(f'EXPORT lanes with fuel: {export_with_fuel}')
