
import os
import django
import sys
import uuid

# Add the backend directory to sys.path
sys.path.append(os.path.abspath('backend'))

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rate_engine.settings')
django.setup()

from core.models import Airport, Location

def fix_missing_locations():
    airports = Airport.objects.all()
    fixed_count = 0
    
    for airport in airports:
        if not Location.objects.filter(airport=airport).exists():
            print(f"Creating Location for Airport: {airport.iata_code} - {airport.name}")
            
            # Use city from airport if available
            city = airport.city
            country = city.country if city else None
            
            Location.objects.create(
                id=uuid.uuid4(),
                kind=Location.Kind.AIRPORT,
                name=airport.name,
                code=airport.iata_code,
                country=country,
                city=city,
                airport=airport,
                is_active=True
            )
            fixed_count += 1
            
    if fixed_count > 0:
        print(f"Successfully created {fixed_count} missing locations.")
    else:
        print("No missing locations found.")

if __name__ == "__main__":
    fix_missing_locations()
