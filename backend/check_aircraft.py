
import os
import django
import sys

# Setup Django environment
sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rate_engine.settings')
django.setup()

from core.models import AircraftType

def check_aircraft_data():
    print("Checking AircraftType Data...")
    aircrafts = AircraftType.objects.all()
    for ac in aircrafts:
        print(f"Aircraft: {ac.code} ({ac.name})")
        print(f"  Max Weight: {ac.max_piece_weight_kg} kg")
        print(f"  Max Dims: {ac.max_length_cm}x{ac.max_width_cm}x{ac.max_height_cm} cm")
        print("-" * 20)

if __name__ == '__main__':
    check_aircraft_data()
