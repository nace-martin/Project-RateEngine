# test_rate_availability.py
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rate_engine.settings')
django.setup()

from quotes.spot_services import RateAvailabilityService, SpotTriggerEvaluator

def test_db_availability(origin_airport, dest_airport, origin_country, dest_country, scope):
    direction = 'IMPORT'
    if origin_country == 'PG':
        direction = 'EXPORT'
    
    print(f"DEBUG: direction={direction}, scope={scope}, origin={origin_country}, dest={dest_country}")
    availability = RateAvailabilityService.get_availability(
        origin_airport=origin_airport,
        destination_airport=dest_airport,
        direction=direction,
        service_scope=scope
    )
    
    print(f"Availability Map: {list(availability.items())}")
    
    is_spot, result = SpotTriggerEvaluator.evaluate(
        origin_country=origin_country,
        destination_country=dest_country,
        direction=direction,
        service_scope=scope,
        component_availability=availability
    )
    
    print(f"SPOT Required: {is_spot}")
    if result:
        print(f"Reason: {result.code} - {result.text}")
    print("-" * 60)

if __name__ == "__main__":
    print("VERIFYING DB-DRIVEN SPOT TRIGGER\n")
    
    # Test Case: Export D2D POM to SIN
    # SIN likely has no destination charges in DB
    test_db_availability("POM", "SIN", "PG", "SG", "D2D")
    
    # Test Case: Export P2P POM to BNE (BNE should have airfreight)
    test_db_availability("POM", "BNE", "PG", "AU", "P2P")
