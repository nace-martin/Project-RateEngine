"""Check fuel surcharge coverage across all quote types"""
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rate_engine.settings')
django.setup()

from services.models import ServiceRule, ServiceRuleComponent
from ratecards.models import PartnerRate, PartnerRateLane

print('=== SERVICE RULES WITH FUEL SURCHARGES ===')
rules = ServiceRule.objects.filter(is_active=True, mode='AIR')
for r in rules:
    org = ServiceRuleComponent.objects.filter(service_rule=r, service_component__code='PICKUP_FUEL_ORG').exists()
    dst = ServiceRuleComponent.objects.filter(service_rule=r, service_component__code='PICKUP_FUEL_DST').exists()
    print(f'{r.direction} {r.payment_term} {r.service_scope}: ORG={org} DST={dst}')

print()
print('=== FUEL RATE COUNTS ===')
print(f'PICKUP_FUEL_ORG rates: {PartnerRate.objects.filter(service_component__code="PICKUP_FUEL_ORG").count()}')
print(f'PICKUP_FUEL_DST rates: {PartnerRate.objects.filter(service_component__code="PICKUP_FUEL_DST").count()}')

print()
print('=== LANES WITH FUEL_ORG RATES ===')
for r in PartnerRate.objects.filter(service_component__code='PICKUP_FUEL_ORG').select_related('lane', 'lane__origin_airport', 'lane__destination_airport'):
    print(f'  {r.lane.origin_airport.iata_code}->{r.lane.destination_airport.iata_code} {r.lane.direction} | {r.rate_per_shipment_fcy}%')

print()
print('=== LANES WITH FUEL_DST RATES ===')
for r in PartnerRate.objects.filter(service_component__code='PICKUP_FUEL_DST').select_related('lane', 'lane__origin_airport', 'lane__destination_airport'):
    print(f'  {r.lane.origin_airport.iata_code}->{r.lane.destination_airport.iata_code} {r.lane.direction} | {r.rate_per_shipment_fcy}%')

print()
print('=== COVERAGE GAP ANALYSIS ===')
# Check which directions have rates
import_lanes_with_fuel = set()
export_lanes_with_fuel = set()

for r in PartnerRate.objects.filter(service_component__code__startswith='PICKUP_FUEL').select_related('lane'):
    lane_key = f"{r.lane.origin_airport_id}->{r.lane.destination_airport_id}"
    if r.lane.direction == 'IMPORT':
        import_lanes_with_fuel.add(lane_key)
    else:
        export_lanes_with_fuel.add(lane_key)

# Get all lanes
all_import_lanes = set()
all_export_lanes = set()
for lane in PartnerRateLane.objects.all():
    lane_key = f"{lane.origin_airport_id}->{lane.destination_airport_id}"
    if lane.direction == 'IMPORT':
        all_import_lanes.add(lane_key)
    else:
        all_export_lanes.add(lane_key)

print(f'IMPORT lanes with fuel rates: {len(import_lanes_with_fuel)}/{len(all_import_lanes)}')
print(f'EXPORT lanes with fuel rates: {len(export_lanes_with_fuel)}/{len(all_export_lanes)}')
