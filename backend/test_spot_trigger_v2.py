# test_spot_trigger_v2.py
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rate_engine.settings')
django.setup()

from quotes.spot_services import SpotTriggerEvaluator

def test_trigger(origin, dest, direction, scope, availability):
    is_spot, result = SpotTriggerEvaluator.evaluate(
        origin_country=origin,
        destination_country=dest,
        direction=direction,
        service_scope=scope,
        component_availability=availability
    )
    print(f"Route: {origin} -> {dest} | Direction: {direction} | Scope: {scope}")
    print(f"Availability: {availability}")
    print(f"SPOT Required: {is_spot}")
    if result:
        print(f"Reason: {result.code} - {result.text}")
    print("-" * 60)

if __name__ == "__main__":
    print("TESTING DETERMINISTIC RATE COVERAGE LOGIC\n")
    
    # Example 1: Export D2A - Complete Coverage
    test_trigger("PG", "SG", "EXPORT", "D2A", {
        "AIRFREIGHT": True,
        "EXPORT_CLEARANCE": True
    })
    
    # Example 2: Export D2A - Missing Clearance
    test_trigger("PG", "SG", "EXPORT", "D2A", {
        "AIRFREIGHT": True,
        "EXPORT_CLEARANCE": False
    })
    
    # Example 3: Export D2D - Missing Destination Charges
    test_trigger("PG", "SG", "EXPORT", "D2D", {
        "ORIGIN_PICKUP": True,
        "EXPORT_CLEARANCE": True,
        "AIRFREIGHT": True,
        "DEST_CLEARANCE": False,
        "DEST_DELIVERY": False
    })
    
    # Example 4: Import A2D - Complete Coverage
    test_trigger("CN", "PG", "IMPORT", "A2D", {
        "AIRFREIGHT": True,
        "DEST_CLEARANCE": True,
        "DEST_DELIVERY": True
    })

    # Example 5: Out of Scope
    test_trigger("AU", "SG", "CROSS_TRADE", "P2P", {})
