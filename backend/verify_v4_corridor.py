"""Quick verification script for Export POM-BNE corridor"""
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rate_engine.settings')
django.setup()

from datetime import date
from decimal import Decimal
from pricing_v4.models import ProductCode
from pricing_v4.engine.export_engine import ExportPricingEngine

# Test parameters
origin = 'POM'
destination = 'BNE'
quote_date = date.today()
chargeable_weight = Decimal('150.00')

print("=" * 70)
print("VERIFICATION: Export Air D2A Prepaid POM->BNE")
print("=" * 70)
print(f"\nTest: 150kg shipment POM->BNE")

# Get all Export ProductCodes
export_codes = ProductCode.objects.filter(domain=ProductCode.DOMAIN_EXPORT)
product_code_ids = list(export_codes.values_list('id', flat=True))
print(f"ProductCodes found: {len(product_code_ids)}")

# Initialize engine
engine = ExportPricingEngine(
    quote_date=quote_date,
    origin=origin,
    destination=destination,
    chargeable_weight_kg=chargeable_weight,
)

# Calculate quote
result = engine.calculate_quote(product_code_ids)

print(f"\n{'Code':<15} {'COGS':>10} {'SELL':>10} {'Margin':>10}")
print("-" * 50)

for line in result.lines:
    print(f"{line.product_code:<15} {line.cost_amount:>10.2f} {line.sell_amount:>10.2f} {line.margin_amount:>10.2f}")

print("-" * 50)
print(f"{'TOTALS':<15} {result.total_cost:>10.2f} {result.total_sell:>10.2f} {result.total_margin:>10.2f}")

# Verification summary
print("\n" + "=" * 70)
print("VERIFICATION CHECKLIST")
print("=" * 70)

rates_missing = sum(1 for line in result.lines if line.is_rate_missing)
print(f"[{'PASS' if rates_missing == 0 else 'FAIL'}] Rate Selection: {len(result.lines)} lines, {rates_missing} missing")
print(f"[{'PASS' if result.total_margin > 0 else 'FAIL'}] Margin: {result.total_margin:.2f} PGK")
print(f"[{'PASS' if result.currency == 'PGK' else 'FAIL'}] Currency: {result.currency}")
print(f"[{'PASS' if result.total_gst == 0 else 'WARN'}] GST: {result.total_gst:.2f} (Export should be 0)")

if rates_missing == 0 and result.total_margin > 0 and result.currency == 'PGK':
    print("\n*** CORRIDOR VERIFIED: Export POM->BNE PASSING ***")
else:
    print("\n*** CORRIDOR NEEDS ATTENTION ***")
