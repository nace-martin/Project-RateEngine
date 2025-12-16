"""Verify POM->SYD Corridor"""
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rate_engine.settings')
django.setup()

from datetime import date
from decimal import Decimal
from pricing_v4.engine.export_engine import ExportPricingEngine

# Test parameters
origin = 'POM'
destination = 'SYD'
quote_date = date.today()
weight = Decimal('150.00')

print("=" * 70)
print("VERIFICATION: Export POM->SYD (150kg)")
print("=" * 70)

# Get product codes (No DG)
product_codes = ExportPricingEngine.get_product_codes(is_dg=False)

# Calculate
engine = ExportPricingEngine(
    quote_date=quote_date,
    origin=origin,
    destination=destination,
    chargeable_weight_kg=weight,
)

result = engine.calculate_quote(product_codes)

print(f"\n{'Code':<20} {'COGS':>12} {'SELL':>12}")
print("-" * 45)
for line in result.lines:
    print(f"{line.product_code:<20} K{line.cost_amount:>10.2f} K{line.sell_amount:>10.2f}")
print("-" * 45)
print(f"{'TOTALS':<20} K{result.total_cost:>10.2f} K{result.total_sell:>10.2f}")
print("=" * 45)

# Expected values (calculated manually from rate card)
# COGS: 
#   Freight: 150kg * K7.50 (+100kg tier) = K1125.00
#   DOC, AWB, TERM: K35 * 3 = K105.00
#   BUILDUP: 150 * 0.15 = 22.50 (min 30.00) => K30.00
#   SCREEN: 150*0.17 + 35 = 25.5 + 35 = K60.50
#   TOTAL COGS = 1125 + 105 + 30 + 60.50 = K1320.50

# SELL:
#   Freight: 150kg * K9.40 (+100kg tier) = K1410.00
#   DOC, AWB, TERM: K50 * 3 = K150.00
#   BUILDUP: 150 * 0.20 = 30.00 (min 50.00) => K50.00
#   SCREEN: 150*0.20 + 45 = 30 + 45 = K75.00
#   CLEAR: K300.00
#   AGENCY: K250.00
#   PICKUP: 150 * 1.50 = K225.00 (min 95) => K225.00
#   FSC: 10% of 225 = K22.50
#   TOTAL SELL = 1410 + 150 + 50 + 75 + 300 + 250 + 225 + 22.50 = K2482.50

expected_cogs = Decimal('1320.50')
expected_sell = Decimal('2482.50')

print(f"\nExpected COGS: K{expected_cogs}")
print(f"Calculated COGS: K{result.total_cost}")
if result.total_cost == expected_cogs:
    print("COGS CHECK: PASS ✅")
else:
    print(f"COGS CHECK: FAIL ❌ (Diff: K{result.total_cost - expected_cogs})")

print(f"\nExpected SELL: K{expected_sell}")
print(f"Calculated SELL: K{result.total_sell}")
if result.total_sell == expected_sell:
    print("SELL CHECK: PASS ✅")
else:
    print(f"SELL CHECK: FAIL ❌ (Diff: K{result.total_sell - expected_sell})")
