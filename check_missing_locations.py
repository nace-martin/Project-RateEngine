
import os
import django
import sys

# Add the backend directory to sys.path
sys.path.append(os.path.abspath('backend'))

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rate_engine.settings')
django.setup()

from core.models import Airport, Location

def check_missing_locations():
    airports = Airport.objects.all()
    missing_count = 0
    print(f"Total Airports: {airports.count()}")
    
    for airport in airports:
        # Check if a Location exists for this airport
        # Location has a foreign key to Airport named 'airport'
        if not Location.objects.filter(airport=airport).exists():
            print(f"Missing Location for Airport: {airport.iata_code} - {airport.name}")
            missing_count += 1
            
    if missing_count == 0:
        print("All airports have corresponding locations.")
    else:
        print(f"Found {missing_count} airports without locations.")

if __name__ == "__main__":
    check_missing_locations()
