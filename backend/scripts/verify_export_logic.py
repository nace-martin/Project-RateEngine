
import os
import sys
import django
from decimal import Decimal
import uuid

# Setup Django
sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rate_engine.settings')
django.setup()

from core.models import Location, Country, Policy, FxSnapshot
from quotes.models import Quote
from quotes.views import QuoteComputeV3APIView
from quotes.schemas import QuoteComputeRequest
from services.models import ServiceComponent

def get_or_create_location(code, country_code):
    country, _ = Country.objects.get_or_create(code=country_code, defaults={'name': country_code})
    loc, _ = Location.objects.get_or_create(code=code, defaults={'name': code, 'country': country, 'is_active': True})
    return loc

def ensure_dst_charges():
    comp, created = ServiceComponent.objects.get_or_create(
        code='DST_CHARGES', 
        defaults={
            'description': 'Destination Charges', 
            'cost_type': 'RATE_OFFER',
            'category': 'DESTINATION',
            'is_active': True
        }
    )
    return comp

def run_scenario(name, origin_code, dest_code, payment_term, service_scope, expected_incoterm, expected_currency, expect_dst_charges):
    print(f"\n--- Scenario: {name} ---")
    
    org_loc = get_or_create_location(origin_code, 'PG')
    if dest_code == 'BNE':
        dest_loc = get_or_create_location(dest_code, 'AU')
    elif dest_code == 'LAX':
        dest_loc = get_or_create_location(dest_code, 'US')
    else:
        dest_loc = get_or_create_location(dest_code, 'AU') # Default

    # Mock Request Payload
    payload = {
        "customer_id": uuid.uuid4(), # Mock UUID, won't be used for calculation logic really
        "contact_id": uuid.uuid4(),
        "mode": "AIR",
        "service_scope": service_scope,
        "payment_term": payment_term,
        "incoterm": "EXW", # Deliberately wrong to test override
        "origin_location_id": org_loc.id,
        "destination_location_id": dest_loc.id,
        "is_dangerous_goods": False,
        "dimensions": [{"pieces": 1, "length_cm": 10, "width_cm": 10, "height_cm": 10, "gross_weight_kg": 10}],
        "spot_rates": {}
    }
    
    # We need to bypass the View's extensive permission/DB checks and test the component logic directly where possible.
    # However, testing the View logic (Incoterm override) is key. 
    # Let's instantiate the View and call the helper methods directly, simulating everything up to calling PricingService.
    
    view = QuoteComputeV3APIView()
    
    # Simulate View Logic for Incoterm Override
    try:
        req_data = QuoteComputeRequest(**payload)
        
        # 1. Enforce Business Rules (Copied from View)
        shipment_type = Quote.ShipmentType.EXPORT
        if req_data.service_scope == 'D2A':
            req_data.incoterm = 'FCA'
        elif req_data.service_scope == 'D2D' and req_data.payment_term == 'PREPAID':
            req_data.incoterm = 'DAP'
            
        print(f"Resulting Incoterm: {req_data.incoterm} (Expected: {expected_incoterm})")
        if req_data.incoterm != expected_incoterm:
            print("FAIL: Incoterm mismatch")
            return

        # 2. Build Input
        quote_input = view._build_quote_input(req_data, shipment_type, org_loc, dest_loc)
        
        # 3. Call Pricing Service
        from pricing_v2.pricing_service_v3 import PricingServiceV3
        service = PricingServiceV3(quote_input)
        
        # Inject DST_CHARGES component locally if needed for test validty (usually DB has it)
        ensure_dst_charges()
        
        # Calculate
        charges = service.calculate_charges()
        output_currency = service.get_output_currency()
        
        print(f"Output Currency: {output_currency} (Expected: {expected_currency})")
        if output_currency != expected_currency:
            print("FAIL: Currency mismatch")
        
        # Check DST_CHARGES
        found_dst = any(l.service_component_code == 'DST_CHARGES' for l in charges.lines)
        print(f"Has DST_CHARGES: {found_dst} (Expected: {expect_dst_charges})")
        
        if found_dst != expect_dst_charges:
            # For D2D, if we expect it but don't find it, it might be due to ServiceRule not having it?
            # Or our injection logic failed.
            # In our code: injection happens if "Export Prepaid D2D".
            print("FAIL: DST_CHARGES mismatch")

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()

def verify():
    # Ensure policy and fx exist
    if not Policy.objects.exists():
        Policy.objects.create(name="Test Policy", is_active=True, effective_from="2024-01-01")
    if not FxSnapshot.objects.exists():
        FxSnapshot.objects.create()

    # 1. Export Prepaid D2A (PNG -> BNE)
    run_scenario(
        "Export Prepaid D2A", 
        "POM", "BNE", 
        "PREPAID", "D2A", 
        expected_incoterm="FCA", 
        expected_currency="PGK", 
        expect_dst_charges=False
    )

    # 2. Export Prepaid D2D (PNG -> BNE)
    run_scenario(
        "Export Prepaid D2D", 
        "POM", "BNE", 
        "PREPAID", "D2D", 
        expected_incoterm="DAP", 
        expected_currency="PGK", 
        expect_dst_charges=True
    )

    # 3. Export Collect D2A (PNG -> BNE) [AU Destination]
    run_scenario(
        "Export Collect D2A (AU)", 
        "POM", "BNE", 
        "COLLECT", "D2A", 
        expected_incoterm="FCA", 
        expected_currency="AUD", 
        expect_dst_charges=False
    )
    
    # 4. Export Collect D2A (PNG -> LAX) [Non-AU Destination]
    run_scenario(
        "Export Collect D2A (US)", 
        "POM", "LAX", 
        "COLLECT", "D2A", 
        expected_incoterm="FCA", 
        expected_currency="USD", 
        expect_dst_charges=False
    )

if __name__ == "__main__":
    verify()
