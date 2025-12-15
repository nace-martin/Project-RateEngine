"""Comprehensive check of locations, rate cards, and fuel surcharge data"""
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rate_engine.settings')
django.setup()

from core.models import Location, Airport
from ratecards.models import PartnerRateCard, PartnerRateLane, PartnerRate
from services.models import ServiceComponent

print('=== LOCATIONS IN DB ===')
locs = Location.objects.all()
print(f'Total: {locs.count()}')
for l in locs:
    print(f'  {l.code} - {l.name}')

print()
print('=== AIRPORTS IN DB ===')
airports = Airport.objects.all()
print(f'Total: {airports.count()}')
for a in airports:
    print(f'  {a.iata_code} - {a.name}')

print()
print('=== RATE CARDS ===')
cards = PartnerRateCard.objects.all()
for c in cards:
    lanes = c.lanes.count()
    print(f'  {c.name} ({c.rate_type}, {c.currency_code}): {lanes} lanes')

print()
print('=== EXPORT LANES (POM origin) ===')
export_lanes = PartnerRateLane.objects.filter(direction='EXPORT')
for lane in export_lanes:
    print(f'  {lane.origin_airport.iata_code}->{lane.destination_airport.iata_code}: {lane.rate_card.name}')

print()
print('=== INCORRECT FUEL_DST RATES TO REMOVE ===')
# For Export lanes, PICKUP_FUEL_DST should NOT exist for overseas destinations
fuel_dst = ServiceComponent.objects.get(code='PICKUP_FUEL_DST')
incorrect = PartnerRate.objects.filter(
    service_component=fuel_dst,
    lane__direction='EXPORT'
).exclude(lane__destination_airport__iata_code__in=['POM'])  # Only PNG dest should have DST fuel

print(f'Incorrect PICKUP_FUEL_DST rates for Export overseas: {incorrect.count()}')
for r in incorrect[:10]:
    print(f'  {r.lane.origin_airport.iata_code}->{r.lane.destination_airport.iata_code}')

# Delete incorrect rates
deleted = incorrect.delete()
print(f'Deleted: {deleted}')
