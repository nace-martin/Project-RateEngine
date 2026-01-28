
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

def verify_p2p_pickup():
    print(f"\n--- Verifying P2P Export Quote Includes Pickup ---")
    
    # Get product codes for P2P scope
    codes = ExportPricingEngine.get_product_codes(is_dg=False, service_scope='P2P')
    print(f"Product Codes: {codes}")
    
    # Check if Pickup (1050) and FSC Pickup (1060) are present
    has_pickup = 1050 in codes
    has_fsc = 1060 in codes
    
    print(f"Contains Pickup (1050): {has_pickup}")
    print(f"Contains FSC Pickup (1060): {has_fsc}")

    if has_pickup and has_fsc:
        print("SUCCESS: Pickup fees are present in P2P scope.")
        sys.exit(0)
    else:
        print("FAILURE: Pickup fees are MISSING from P2P scope.")
        sys.exit(1)

if __name__ == "__main__":
    verify_p2p_pickup()
