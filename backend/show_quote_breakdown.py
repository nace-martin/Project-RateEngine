"""Detailed quote breakdown showing exact calculations"""
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rate_engine.settings')
django.setup()

from datetime import date
from decimal import Decimal
from pricing_v4.models import ProductCode, ExportCOGS, ExportSellRate
from pricing_v4.engine.export_engine import ExportPricingEngine

# Test parameters
origin = 'POM'
destination = 'BNE'
quote_date = date.today()
weight = Decimal('150.00')

print("=" * 80)
print("DETAILED QUOTE BREAKDOWN: Export Air D2A Prepaid POM->BNE")
print("=" * 80)
print(f"\nShipment Details:")
print(f"  Origin: {origin}")
print(f"  Destination: {destination}")
print(f"  Chargeable Weight: {weight} kg")
print(f"  Quote Date: {quote_date}")

# Get all Export ProductCodes
export_codes = ProductCode.objects.filter(domain=ProductCode.DOMAIN_EXPORT).order_by('id')
product_code_ids = list(export_codes.values_list('id', flat=True))

# Initialize engine
engine = ExportPricingEngine(
    quote_date=quote_date,
    origin=origin,
    destination=destination,
    chargeable_weight_kg=weight,
)

# Calculate quote
result = engine.calculate_quote(product_code_ids)

print("\n" + "=" * 80)
print("LINE-BY-LINE CALCULATIONS")
print("=" * 80)

total_cost = Decimal('0')
total_sell = Decimal('0')
total_margin = Decimal('0')

for line in result.lines:
    print(f"\n--- {line.product_code}: {line.description} ---")
    
    # Get the underlying rate data
    cogs = ExportCOGS.objects.filter(
        product_code_id=line.product_code_id,
        origin_airport=origin,
        destination_airport=destination,
    ).first()
    
    sell = ExportSellRate.objects.filter(
        product_code_id=line.product_code_id,
        origin_airport=origin,
        destination_airport=destination,
    ).first()
    
    # COGS calculation
    print(f"\n  COGS Calculation:")
    if cogs:
        if cogs.weight_breaks:
            print(f"    Weight Breaks: {cogs.weight_breaks}")
            # Find applicable rate
            sorted_breaks = sorted(cogs.weight_breaks, key=lambda x: x['min_kg'], reverse=True)
            for tier in sorted_breaks:
                if weight >= Decimal(str(tier['min_kg'])):
                    rate = Decimal(str(tier['rate']))
                    calc = weight * rate
                    print(f"    >> Using tier min_kg={tier['min_kg']}: {weight} kg x K{rate} = K{calc:.2f}")
                    if cogs.min_charge and calc < cogs.min_charge:
                        print(f"    >> Apply min charge: K{cogs.min_charge}")
                    break
        elif cogs.is_additive and cogs.rate_per_kg and cogs.rate_per_shipment:
            kg_amount = weight * cogs.rate_per_kg
            flat = cogs.rate_per_shipment
            total = kg_amount + flat
            print(f"    ADDITIVE: {weight} kg x K{cogs.rate_per_kg}/kg + K{flat} flat")
            print(f"    >> K{kg_amount:.2f} + K{flat:.2f} = K{total:.2f}")
        elif cogs.rate_per_kg:
            calc = weight * cogs.rate_per_kg
            print(f"    Per-kg: {weight} kg x K{cogs.rate_per_kg} = K{calc:.2f}")
            if cogs.min_charge and calc < cogs.min_charge:
                print(f"    >> Apply min charge: K{cogs.min_charge}")
        elif cogs.rate_per_shipment:
            print(f"    Flat fee: K{cogs.rate_per_shipment}")
        print(f"    COGS Result: K{line.cost_amount:.2f}")
    else:
        print(f"    (No COGS - sell-only charge)")
        print(f"    COGS Result: K0.00")
    
    # SELL calculation
    print(f"\n  SELL Calculation:")
    if sell:
        if sell.percent_rate:
            # Get base product code
            pc = ProductCode.objects.get(id=line.product_code_id)
            base_pc = pc.percent_of_product_code
            if base_pc:
                # Find the base sell amount
                base_line = next((l for l in result.lines if l.product_code_id == base_pc.id), None)
                if base_line:
                    print(f"    Percentage: {sell.percent_rate}% of {base_pc.code} (K{base_line.sell_amount:.2f})")
                    calc = base_line.sell_amount * (sell.percent_rate / 100)
                    print(f"    >> K{base_line.sell_amount:.2f} x {sell.percent_rate}% = K{calc:.2f}")
        elif sell.weight_breaks:
            print(f"    Weight Breaks: {sell.weight_breaks}")
            sorted_breaks = sorted(sell.weight_breaks, key=lambda x: x['min_kg'], reverse=True)
            for tier in sorted_breaks:
                if weight >= Decimal(str(tier['min_kg'])):
                    rate = Decimal(str(tier['rate']))
                    calc = weight * rate
                    print(f"    >> Using tier min_kg={tier['min_kg']}: {weight} kg x K{rate} = K{calc:.2f}")
                    if sell.min_charge and calc < sell.min_charge:
                        print(f"    >> Apply min charge: K{sell.min_charge}")
                    break
        elif getattr(sell, 'is_additive', False) and sell.rate_per_kg and sell.rate_per_shipment:
            kg_amount = weight * sell.rate_per_kg
            flat = sell.rate_per_shipment
            total = kg_amount + flat
            print(f"    ADDITIVE: {weight} kg x K{sell.rate_per_kg}/kg + K{flat} flat")
            print(f"    >> K{kg_amount:.2f} + K{flat:.2f} = K{total:.2f}")
        elif sell.rate_per_kg:
            calc = weight * sell.rate_per_kg
            print(f"    Per-kg: {weight} kg x K{sell.rate_per_kg} = K{calc:.2f}")
            if sell.min_charge and calc < sell.min_charge:
                print(f"    >> Apply min charge: K{sell.min_charge}")
            if sell.max_charge and calc > sell.max_charge:
                print(f"    >> Apply max charge: K{sell.max_charge}")
        elif sell.rate_per_shipment:
            print(f"    Flat fee: K{sell.rate_per_shipment}")
        print(f"    SELL Result: K{line.sell_amount:.2f}")
    else:
        print(f"    (No sell rate found)")
    
    # Margin
    print(f"\n  MARGIN: K{line.sell_amount:.2f} - K{line.cost_amount:.2f} = K{line.margin_amount:.2f}")
    
    total_cost += line.cost_amount
    total_sell += line.sell_amount
    total_margin += line.margin_amount

print("\n" + "=" * 80)
print("SUMMARY")
print("=" * 80)
print(f"\n{'Product Code':<20} {'COGS':>12} {'SELL':>12} {'MARGIN':>12}")
print("-" * 56)
for line in result.lines:
    print(f"{line.product_code:<20} K{line.cost_amount:>10.2f} K{line.sell_amount:>10.2f} K{line.margin_amount:>10.2f}")
print("-" * 56)
print(f"{'TOTALS':<20} K{total_cost:>10.2f} K{total_sell:>10.2f} K{total_margin:>10.2f}")
print("=" * 56)
