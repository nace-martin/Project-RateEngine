"""Query current database rates for comparison"""
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rate_engine.settings')
django.setup()

from decimal import Decimal
from pricing_v4.models import ExportCOGS, ExportSellRate, ProductCode

print("=" * 70)
print("DATABASE RATES: Export POM->BNE")
print("=" * 70)

# Query all Export COGS for POM->BNE
print("\n--- COGS RATES ---")
cogs = ExportCOGS.objects.filter(
    origin_airport='POM',
    destination_airport='BNE',
).select_related('product_code')

for rate in cogs:
    print(f"\n{rate.product_code.code}:")
    if rate.weight_breaks:
        print(f"  Weight Breaks: {rate.weight_breaks}")
    if rate.rate_per_kg:
        print(f"  Rate/kg: K{rate.rate_per_kg}")
    if rate.rate_per_shipment:
        print(f"  Rate/shipment: K{rate.rate_per_shipment}")
    if rate.min_charge:
        print(f"  Min charge: K{rate.min_charge}")
    if rate.is_additive:
        print(f"  Is Additive: {rate.is_additive}")

# Query all Export SELL for POM->BNE
print("\n--- SELL RATES ---")
sells = ExportSellRate.objects.filter(
    origin_airport='POM',
    destination_airport='BNE',
).select_related('product_code')

for rate in sells:
    print(f"\n{rate.product_code.code}:")
    if rate.weight_breaks:
        print(f"  Weight Breaks: {rate.weight_breaks}")
    if rate.rate_per_kg:
        print(f"  Rate/kg: K{rate.rate_per_kg}")
    if rate.rate_per_shipment:
        print(f"  Rate/shipment: K{rate.rate_per_shipment}")
    if rate.min_charge:
        print(f"  Min charge: K{rate.min_charge}")
    if rate.percent_rate:
        print(f"  Percent Rate: {rate.percent_rate}%")
    if rate.is_additive:
        print(f"  Is Additive: {rate.is_additive}")

print("\n" + "=" * 70)
