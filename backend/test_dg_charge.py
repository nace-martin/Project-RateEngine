"""Test DG conditional charge logic"""
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rate_engine.settings')
django.setup()

from datetime import date
from decimal import Decimal
from pricing_v4.engine.export_engine import ExportPricingEngine

# Test parameters
origin = 'POM'
destination = 'BNE'
quote_date = date.today()
weight = Decimal('150.00')

print("=" * 70)
print("DG CONDITIONAL CHARGE TEST")
print("=" * 70)

# Initialize engine
engine = ExportPricingEngine(
    quote_date=quote_date,
    origin=origin,
    destination=destination,
    chargeable_weight_kg=weight,
)

# Test 1: Standard shipment (no DG)
print("\n--- TEST 1: Standard Shipment (is_dg=False) ---")
standard_codes = ExportPricingEngine.get_product_codes(is_dg=False)
print(f"ProductCodes included: {len(standard_codes)}")
result1 = engine.calculate_quote(standard_codes)
print(f"Total SELL: K{result1.total_sell:.2f}")
print(f"Total MARGIN: K{result1.total_margin:.2f}")
has_dg = any(line.product_code == 'EXP-DG' for line in result1.lines)
print(f"DG Charge included: {'YES' if has_dg else 'NO'}")

# Test 2: DG shipment
print("\n--- TEST 2: Dangerous Goods Shipment (is_dg=True) ---")
dg_codes = ExportPricingEngine.get_product_codes(is_dg=True)
print(f"ProductCodes included: {len(dg_codes)}")
result2 = engine.calculate_quote(dg_codes)
print(f"Total SELL: K{result2.total_sell:.2f}")
print(f"Total MARGIN: K{result2.total_margin:.2f}")
has_dg = any(line.product_code == 'EXP-DG' for line in result2.lines)
print(f"DG Charge included: {'YES' if has_dg else 'NO'}")

# Show difference
diff_sell = result2.total_sell - result1.total_sell
diff_margin = result2.total_margin - result1.total_margin
print(f"\n--- DIFFERENCE (DG vs Standard) ---")
print(f"SELL difference: +K{diff_sell:.2f}")
print(f"MARGIN difference: +K{diff_margin:.2f}")
print("=" * 70)
