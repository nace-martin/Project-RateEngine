"""Calculate quote WITHOUT DG to match user's general cargo test"""
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rate_engine.settings')
django.setup()

from datetime import date
from decimal import Decimal
from pricing_v4.engine.export_engine import ExportPricingEngine

# Test parameters - matching user's test
origin = 'POM'
destination = 'BNE'
quote_date = date.today()
weight = Decimal('150.00')

print("=" * 70)
print("GENERAL CARGO (No DG) - 150kg POM->BNE")
print("=" * 70)

# Get product codes WITHOUT DG
product_codes = ExportPricingEngine.get_product_codes(is_dg=False)
print(f"ProductCodes included: {product_codes}")

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

print(f"\nYour figures:  COGS = K1,328.00   SELL = K2,182.50")
print(f"My figures:    COGS = K{result.total_cost:.2f}   SELL = K{result.total_sell:.2f}")
print(f"Difference:    COGS = K{Decimal('1328.00') - result.total_cost:.2f}   SELL = K{Decimal('2182.50') - result.total_sell:.2f}")
