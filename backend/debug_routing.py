
import os
import django
import sys
from decimal import Decimal

# Setup Django environment
sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rate_engine.settings')
django.setup()

from core.models import AircraftType, RouteLaneConstraint
from core.routing import RoutingValidator

def debug_routing():
    print("Debugging Routing Logic for 300kg Shipment...")
    
    # 1. Check B737 Constraints
    try:
        b737 = AircraftType.objects.get(code='B737')
        print(f"B737 Found: {b737}")
        print(f"  Max Weight: {b737.max_piece_weight_kg}")
        print(f"  Max Dims: {b737.max_length_cm}x{b737.max_width_cm}x{b737.max_height_cm}")
    except AircraftType.DoesNotExist:
        print("ERROR: B737 AircraftType not found!")
        return

    # 2. Check Route Lane Constraints
    lanes = RouteLaneConstraint.objects.filter(
        origin__code='SYD',
        destination__code='POM'
    ).order_by('priority')
    
    print("\nRoute Lanes for SYD->POM:")
    for lane in lanes:
        print(f"  Priority {lane.priority}: {lane.service_level} (Aircraft: {lane.aircraft_type})")

    # 3. Test Validator
    print("\nTesting Validator with 300kg...")
    validator = RoutingValidator()
    
    # Mock pieces: 1 piece, 300kg. Dimensions small enough to fit.
    pieces = [
        {
            "weight_kg": 300,
            "length_cm": 100,
            "width_cm": 100,
            "height_cm": 100,
            "quantity": 1
        }
    ]
    
    service_level, reason, violations = validator.determine_required_service_level(
        origin_code='SYD',
        destination_code='POM',
        pieces=pieces
    )
    
    print("\nValidator Result:")
    print(f"  Service Level: {service_level}")
    print(f"  Reason: {reason}")
    print(f"  Violations: {violations}")
    
    if service_level == 'VIA_BNE':
        print("\nSUCCESS: Validator correctly selected VIA_BNE.")
    else:
        print("\nFAILURE: Validator selected DIRECT (or other) instead of VIA_BNE.")

if __name__ == '__main__':
    debug_routing()
