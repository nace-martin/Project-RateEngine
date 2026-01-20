"""Fix Location records to have country, city, airport relationships"""
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rate_engine.settings')
django.setup()

from core.models import Location, Airport, City, Country

# Mapping of airport codes to country codes
AIRPORT_COUNTRIES = {
    'BNE': 'AU',
    'CNS': 'AU',
    'SYD': 'AU',
    'LAX': 'US',
    'POM': 'PG',
    'HKG': 'HK',
    'MNL': 'PH',
    'HIR': 'SB',
    'SIN': 'SG',
    'VLI': 'VU',
    'NAN': 'FJ',
}

COUNTRY_NAMES = {
    'AU': 'Australia',
    'US': 'United States',
    'PG': 'Papua New Guinea',
    'HK': 'Hong Kong',
    'PH': 'Philippines',
    'SB': 'Solomon Islands',
    'SG': 'Singapore',
    'VU': 'Vanuatu',
    'FJ': 'Fiji',
}

print('=== Fixing Location Relationships ===')

for location in Location.objects.all():
    country_code = AIRPORT_COUNTRIES.get(location.code)
    if not country_code:
        print(f'  {location.code}: No mapping found, skipping')
        continue
    
    # Get or create country
    country, _ = Country.objects.get_or_create(
        code=country_code,
        defaults={'name': COUNTRY_NAMES.get(country_code, country_code)}
    )
    
    # Get airport
    airport = Airport.objects.filter(iata_code=location.code).first()
    
    # Get city from airport
    city = airport.city if airport else None
    
    # Update location
    location.country = country
    location.airport = airport
    location.city = city
    location.save()
    
    print(f'  {location.code}: country={country.code}, airport={airport.iata_code if airport else None}, city={city.name if city else None}')

print()
print('=== Verification ===')
for loc in Location.objects.all():
    print(f'{loc.code}: country={loc.country.code if loc.country else None}')
