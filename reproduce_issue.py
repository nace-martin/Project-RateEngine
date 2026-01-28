
import os
import sys
import django
from decimal import Decimal
from datetime import date

# Setup Django environment
sys.path.append(os.path.join(os.getcwd(), 'backend'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rate_engine.settings')
django.setup()

from pricing_v4.engine.export_engine import ExportPricingEngine
from pricing_v4.models import ProductCode

def test_export_quote(scope):
    print(f"\n--- Testing Export Quote with Scope: {scope} ---")
    
    # Mock inputs
    quote_date = date.today()
    origin = 'POM'
    destination = 'BNE'
    weight = Decimal('100.00')
    
    # Get product codes
    codes = ExportPricingEngine.get_product_codes(is_dg=False, service_scope=scope)
    print(f"Product Codes: {codes}")
    
    # Helper to print code names
    named_codes = []
    for c in codes:
        try:
            pc = ProductCode.objects.get(id=c)
            named_codes.append(f"{c} ({pc.code})")
            if c in [1050, 1060]:
                print(f"  -> FOUND: {c} ({pc.code}) - {pc.description}")
        except ProductCode.DoesNotExist:
            named_codes.append(str(c))
    
    # Check if Pickup (1050) and FSC Pickup (1060) are present
    has_pickup = 1050 in codes
    has_fsc = 1060 in codes
    
    print(f"Contains Pickup (1050): {has_pickup}")
    print(f"Contains FSC Pickup (1060): {has_fsc}")

    # Use the engine (might need DB data to work fully, but we can verify code list first)
    engine = ExportPricingEngine(quote_date, origin, destination, weight)
    # We won't call calculate_quote because we might not have rates seeded, 
    # but the get_product_codes logic is what we want to test first.
    
    return has_pickup and has_fsc

if __name__ == "__main__":
    test_export_quote('P2P')
    test_export_quote('D2A')
    test_export_quote('D2D')
    test_export_quote('A2D')
