"""Test 100kg Export Prepaid POM->SYD"""
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
weight = Decimal('100.00')

print("=" * 70)
print(f"TEST QUOTE: Export {origin}->{destination} ({weight} kg)")
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

# Breakdown specific checks
print("\nVerifications:")

# Freight (100kg tier)
frt_line = next(l for l in result.lines if l.product_code == 'EXP-FRT-AIR')
print(f"Freight (+100kg):")
print(f"  COGS: K{frt_line.cost_amount} (Expected: 100 * 7.50 = 750.00)")
print(f"  SELL: K{frt_line.sell_amount} (Expected: 100 * 9.40 = 940.00)")

# Screening
scr_line = next(l for l in result.lines if l.product_code == 'EXP-SCREEN')
print(f"Screening (100kg * 0.17/0.20 + Flat 35/45):")
print(f"  COGS: K{scr_line.cost_amount} (Expected: 17 + 35 = 52.00)")
print(f"  SELL: K{scr_line.sell_amount} (Expected: 20 + 45 = 65.00)")

# Buildup
bld_line = next(l for l in result.lines if l.product_code == 'EXP-BUILDUP')
print(f"Buildup (100kg * 0.15/0.20, Min 30/50):")
print(f"  COGS: K{bld_line.cost_amount} (Expected: 15 < 30 -> 30.00)")
print(f"  SELL: K{bld_line.sell_amount} (Expected: 20 < 50 -> 50.00)")
