"""
Seed Export SELL - PREPAID D2A rate card data
Source: User-provided rate sheet images

Destinations: BNE, CNS, SYD, HKG, MNL, HIR, SIN, VLI, NAN
All rates in PGK
"""
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rate_engine.settings')
django.setup()

from decimal import Decimal
from django.utils import timezone
from core.models import Location, Airport, City, Country
from ratecards.models import PartnerRateCard, PartnerRateLane, PartnerRate
from services.models import ServiceComponent
from parties.models import Company

# =============================================================================
# STEP 1: Add missing Locations
# =============================================================================
print('=== STEP 1: Adding Missing Locations ===')

# Country mappings
COUNTRY_CODES = {
    'AU': 'Australia',
    'HK': 'Hong Kong',
    'PH': 'Philippines', 
    'SB': 'Solomon Islands',
    'SG': 'Singapore',
    'VU': 'Vanuatu',
    'FJ': 'Fiji',
    'PG': 'Papua New Guinea',
}

# Airport data to add as Locations
AIRPORTS_TO_ADD = [
    ('CNS', 'Cairns Airport', 'Cairns', 'AU'),
    ('HKG', 'Hong Kong Intl', 'Hong Kong', 'HK'),
    ('MNL', 'Ninoy Aquino Intl', 'Manila', 'PH'),
    ('HIR', 'Honiara Intl', 'Honiara', 'SB'),
    ('SIN', 'Singapore Changi', 'Singapore', 'SG'),
    ('VLI', 'Port Vila Bauerfield', 'Port Vila', 'VU'),
    ('NAN', 'Nadi Intl', 'Nadi', 'FJ'),
]

for iata, name, city_name, country_code in AIRPORTS_TO_ADD:
    # Check if Location exists
    if Location.objects.filter(code=iata).exists():
        print(f'  {iata}: Already exists')
        continue
    
    # Get or create country
    country, _ = Country.objects.get_or_create(
        code=country_code,
        defaults={'name': COUNTRY_CODES.get(country_code, country_code)}
    )
    
    # Get or create city
    city, _ = City.objects.get_or_create(
        name=city_name,
        country=country
    )
    
    # Get or create airport
    airport, _ = Airport.objects.get_or_create(
        iata_code=iata,
        defaults={'name': name, 'city': city}
    )
    
    # Create Location with minimal fields
    loc = Location.objects.create(
        code=iata,
        name=name,
        is_active=True
    )
    print(f'  {iata}: Created Location')


# =============================================================================
# STEP 2: Create/Update EXPORT SELL Rate Card
# =============================================================================
print()
print('=== STEP 2: Export Sell Rate Card ===')

# Get or create the rate card
card, created = PartnerRateCard.objects.get_or_create(
    name='PX Export Sell Rates 2024',
    defaults={
        'rate_type': 'SELL_RATE',
        'currency_code': 'PGK',
        'valid_from': timezone.now().date(),
        'is_active': True,
    }
)
print(f'Rate Card: {card.name} ({"created" if created else "exists"})')

# Get POM airport
pom = Airport.objects.get(iata_code='POM')

# Export freight rates (POM -> destinations) with weight breaks
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

# Terminal Service Fees (per shipment unless noted)
TERMINAL_FEES = {
    'AWB_EXP': Decimal('35.00'),       # Export AWB Fee
    'DOC_EXP': Decimal('35.00'),       # Export Documentation Fee (BIC)
    'SEC_EXP_MXC': None,               # Export Security Surcharge - composite rate
    'TERM_EXP': Decimal('35.00'),      # Export Terminal Fee (BSC)
    'BUP_EXP': None,                   # Export Build-Up Fee - composite rate
}

# Clearance and Cartage Charges
CLEARANCE_CHARGES = {
    'CLEAR_EXP': Decimal('300.00'),    # Customs Clearance per AWB
    'AGENCY_EXP': Decimal('250.00'),   # Agency Fee per AWB
    # 'CUSTOMS_ENTRY': skip per user request
    'PICKUP': None,                     # Pick up Fee - 1.50/kg min 95, max 500
    'PICKUP_FUEL_ORG': Decimal('10.00'), # 10% fuel surcharge
}

# =============================================================================
# STEP 3: Create Lanes and Rates
# =============================================================================
print()
print('=== STEP 3: Creating Lanes and Rates ===')

for dest_code, rates in FREIGHT_RATES.items():
    # Get destination airport
    dest = Airport.objects.filter(iata_code=dest_code).first()
    if not dest:
        print(f'  {dest_code}: Airport not found, skipping')
        continue
    
    # Get or create lane
    lane, lane_created = PartnerRateLane.objects.get_or_create(
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
    if lane_created:
        print(f'  Created lane: POM -> {dest_code}')
    
    # Add freight rate (using normal rate as base, weight breaks in tiering_json)
    frt = ServiceComponent.objects.filter(code='FRT_AIR_EXP').first()
    if frt:
        rate, _ = PartnerRate.objects.update_or_create(
            lane=lane,
            service_component=frt,
            defaults={
                'unit': 'KG',
                'rate_per_kg_fcy': Decimal(str(rates['normal'])),
                'min_charge_fcy': Decimal(str(rates['min'])),
                'weight_breaks': {
                    'breaks': [
                        {'min_kg': 0, 'rate_per_kg': rates['normal']},
                        {'min_kg': 100, 'rate_per_kg': rates['100kg']},
                        {'min_kg': 200, 'rate_per_kg': rates['200kg']},
                        {'min_kg': 500, 'rate_per_kg': rates['500kg']},
                    ]
                }
            }
        )
    
    # Add terminal fees (flat per shipment)
    for comp_code, amount in TERMINAL_FEES.items():
        if amount is None:
            continue
        comp = ServiceComponent.objects.filter(code=comp_code).first()
        if comp:
            PartnerRate.objects.update_or_create(
                lane=lane,
                service_component=comp,
                defaults={
                    'unit': 'SHIPMENT',
                    'rate_per_shipment_fcy': amount,
                }
            )
    
    # Add Security Surcharge (0.17/kg + 35.00 flat)
    sec = ServiceComponent.objects.filter(code='SEC_EXP_MXC').first()
    if sec:
        PartnerRate.objects.update_or_create(
            lane=lane,
            service_component=sec,
            defaults={
                'unit': 'KG',
                'rate_per_kg_fcy': Decimal('0.17'),
                'rate_per_shipment_fcy': Decimal('35.00'),
            }
        )
    
    # Add Build-Up Fee (0.15/kg min 30.00)
    bup = ServiceComponent.objects.filter(code='BUP_EXP').first()
    if bup:
        PartnerRate.objects.update_or_create(
            lane=lane,
            service_component=bup,
            defaults={
                'unit': 'KG',
                'rate_per_kg_fcy': Decimal('0.15'),
                'min_charge_fcy': Decimal('30.00'),
            }
        )
    
    # Add clearance charges
    for comp_code, amount in CLEARANCE_CHARGES.items():
        if amount is None:
            continue
        comp = ServiceComponent.objects.filter(code=comp_code).first()
        if comp:
            PartnerRate.objects.update_or_create(
                lane=lane,
                service_component=comp,
                defaults={
                    'unit': 'SHIPMENT',
                    'rate_per_shipment_fcy': amount,
                }
            )
    
    # Add Pickup Fee (1.50/kg min 95, max 500)
    pickup = ServiceComponent.objects.filter(code='PICKUP').first()
    if pickup:
        PartnerRate.objects.update_or_create(
            lane=lane,
            service_component=pickup,
            defaults={
                'unit': 'KG',
                'rate_per_kg_fcy': Decimal('1.50'),
                'rate_per_shipment_fcy': Decimal('95.00'),  # Flat component
                'min_charge_fcy': Decimal('95.00'),
                'max_charge_fcy': Decimal('500.00'),
            }
        )

print()
print('=== DONE ===')
print(f'Locations: {Location.objects.count()}')
print(f'Export lanes in {card.name}: {card.lanes.filter(direction="EXPORT").count()}')
