import os
import sys
import django
from decimal import Decimal
from datetime import date
import uuid

# Setup Django environment
BACKEND_DIR = os.path.join(os.getcwd(), 'dev', 'Project-RateEngine', 'backend')
if not os.path.exists(BACKEND_DIR):
    BACKEND_DIR = os.path.join(os.getcwd(), 'backend')

sys.path.append(BACKEND_DIR)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rate_engine.settings')
django.setup()

from core.dataclasses import QuoteInput, ShipmentDetails, LocationRef, Piece
from pricing_v4.adapter import PricingServiceV4Adapter
from core.models import Location

def run_test_calculation(direction, scope, origin_code, dest_code):
    print("\n" + "="*60)
    print(f" TESTING: {direction} | Scope: {scope} | {origin_code} -> {dest_code}")
    print("="*60)
    
    # 1. Prepare Inputs
    origin_loc = Location.objects.filter(code=origin_code).first()
    dest_loc = Location.objects.filter(code=dest_code).first()
    
    if not origin_loc or not dest_loc:
        print(f"Error: Could not find locations for {origin_code} or {dest_code}")
        return

    origin_ref = LocationRef(
        id=origin_loc.id,
        code=origin_loc.code,
        name=origin_loc.name,
        country_code=origin_loc.country.code if origin_loc.country else "PG"
    )
    dest_ref = LocationRef(
        id=dest_loc.id,
        code=dest_loc.code,
        name=dest_loc.name,
        country_code=dest_loc.country.code if dest_loc.country else "PG"
    )

    shipment = ShipmentDetails(
        mode='AIR',
        shipment_type=direction,
        incoterm='EXW' if direction == 'EXPORT' else 'DAP',
        payment_term='PREPAID',
        is_dangerous_goods=False,
        pieces=[Piece(pieces=1, length_cm=Decimal("50"), width_cm=Decimal("50"), height_cm=Decimal("50"), gross_weight_kg=Decimal("100"))],
        service_scope=scope,
        direction=direction,
        origin_location=origin_ref,
        destination_location=dest_ref
    )

    quote_input = QuoteInput(
        customer_id=uuid.uuid4(),
        contact_id=uuid.uuid4(),
        output_currency='PGK',
        quote_date=date.today(),
        shipment=shipment
    )

    # 2. Execute Calculation
    adapter = PricingServiceV4Adapter(quote_input)
    result = adapter.calculate_charges()

    # 3. Audit Results
    print(f"\nResult Totals:")
    print(f" - Total Sell (PGK): {result.totals.total_sell_pgk}")
    print(f" - HAS MISSING RATES: {result.totals.has_missing_rates}")
    
    print("\nCharge Lines Audit:")
    for line in result.lines:
        status = "[MISSING]" if line.is_rate_missing else "[OK]"
        print(f" {status} {line.service_component_code:<25} | Sell: {line.sell_pgk:>8.2f} | Bucket: {line.bucket}")

    return result.totals.has_missing_rates

if __name__ == "__main__":
    # Test 1: Import D2D (Verify normal behavior)
    run_test_calculation('IMPORT', 'D2D', 'BNE', 'POM')
    
    # Test 2: Export D2A POM->SIN (The Reported Issue)
    run_test_calculation('EXPORT', 'D2A', 'POM', 'SIN')
