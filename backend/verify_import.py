"""
Verify Import Seeded Rates: BNE/SYD -> POM
==========================================
This script queries the seeded ImportCOGS and ImportSellRate tables
and calculates a sample quote for verification.
"""
import os
import django
from decimal import Decimal, ROUND_HALF_UP
from datetime import date

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "rate_engine.settings")
django.setup()

from pricing_v4.models import ImportCOGS, ImportSellRate, ProductCode


def calculate_charge(rate, weight_kg):
    """Calculate charge amount from a rate record."""
    amount = Decimal('0')
    
    # Percentage-based charge
    if hasattr(rate, 'percent_rate') and rate.percent_rate:
        return None, rate.percent_rate  # Return percent for later calculation
    
    # Weight breaks
    if rate.weight_breaks:
        wb = sorted(rate.weight_breaks, key=lambda x: Decimal(str(x['min_kg'])), reverse=True)
        for tier in wb:
            if weight_kg >= Decimal(str(tier['min_kg'])):
                amount = weight_kg * Decimal(str(tier['rate']))
                break
    elif rate.rate_per_kg:
        amount = weight_kg * rate.rate_per_kg
    
    # Add flat rate if present
    if rate.rate_per_shipment:
        if amount == 0:
            amount = rate.rate_per_shipment
        elif hasattr(rate, 'is_additive') and rate.is_additive:
            amount += rate.rate_per_shipment
    
    # Apply min/max
    if rate.min_charge and amount < rate.min_charge:
        amount = rate.min_charge
    if rate.max_charge and amount > rate.max_charge:
        amount = rate.max_charge
    
    return amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP), None


def verify_import_rates():
    origin = 'BNE'
    destination = 'POM'
    weight_kg = Decimal('100.00')
    quote_date = date(2025, 1, 1)
    
    print("=" * 90)
    print(f"IMPORT VERIFICATION: {origin} -> {destination} ({weight_kg}kg)")
    print("=" * 90)
    
    # Fetch all Import ProductCodes
    import_pcs = ProductCode.objects.filter(domain='IMPORT').order_by('id')
    
    results = []
    
    for pc in import_pcs:
        # Get COGS
        cogs = ImportCOGS.objects.filter(
            product_code=pc,
            origin_airport=origin,
            destination_airport=destination,
            valid_from__lte=quote_date,
            valid_until__gte=quote_date
        ).first()
        
        # Get Sell Rate
        sell = ImportSellRate.objects.filter(
            product_code=pc,
            origin_airport=origin,
            destination_airport=destination,
            valid_from__lte=quote_date,
            valid_until__gte=quote_date
        ).first()
        
        cost_amt = Decimal('0')
        cost_curr = '-'
        cost_pct = None
        sell_amt = Decimal('0')
        sell_curr = '-'
        sell_pct = None
        
        if cogs:
            cost_amt, cost_pct = calculate_charge(cogs, weight_kg)
            cost_curr = cogs.currency
            if cost_amt is None:
                cost_amt = Decimal('0')
        
        if sell:
            sell_amt, sell_pct = calculate_charge(sell, weight_kg)
            sell_curr = sell.currency
            if sell_amt is None:
                sell_amt = Decimal('0')
        
        # Skip if neither exists
        if not cogs and not sell:
            continue
        
        results.append({
            'code': pc.code,
            'desc': pc.description[:30],
            'cost_amt': cost_amt,
            'cost_curr': cost_curr,
            'cost_pct': cost_pct,
            'sell_amt': sell_amt,
            'sell_curr': sell_curr,
            'sell_pct': sell_pct,
            'has_cogs': cogs is not None,
            'has_sell': sell is not None,
        })
    
    # Print Origin Charges (AUD)
    print("\n--- ORIGIN CHARGES (EFM-AU) ---")
    print(f"{'Code':<22} {'Description':<32} {'Cost':<15} {'Sell':<15} {'Margin'}")
    print("-" * 90)
    
    origin_cost = Decimal('0')
    origin_sell = Decimal('0')
    
    for r in results:
        if r['cost_curr'] == 'AUD':
            cost_str = f"{r['cost_curr']} {r['cost_amt']:>8}" if r['cost_amt'] else '-'
            sell_str = '-'  # Origin charges don't have explicit Sell in tables
            if r['cost_pct']:
                cost_str = f"{r['cost_pct']}%"
            print(f"{r['code']:<22} {r['desc']:<32} {cost_str:<15} {sell_str:<15} (Cost-Plus)")
            origin_cost += r['cost_amt'] or Decimal('0')
    
    print(f"\nOrigin COGS Total: AUD {origin_cost}")
    
    # Print Destination Charges (PGK)
    print("\n--- DESTINATION CHARGES (EFM-PG) ---")
    print(f"{'Code':<22} {'Description':<32} {'Cost':<15} {'Sell':<15} {'Margin'}")
    print("-" * 90)
    
    dest_cost = Decimal('0')
    dest_sell = Decimal('0')
    
    for r in results:
        if r['cost_curr'] == 'PGK' or r['sell_curr'] == 'PGK':
            cost_str = f"K{r['cost_amt']:>8}" if r['cost_amt'] else '-'
            sell_str = f"K{r['sell_amt']:>8}" if r['sell_amt'] else '-'
            
            if r['cost_pct']:
                cost_str = f"{r['cost_pct']}%"
            if r['sell_pct']:
                sell_str = f"{r['sell_pct']}%"
            
            margin = '-'
            if r['cost_amt'] and r['sell_amt'] and r['cost_amt'] > 0:
                margin_pct = ((r['sell_amt'] - r['cost_amt']) / r['cost_amt'] * 100).quantize(Decimal('0.1'))
                margin = f"{margin_pct}%"
            elif r['cost_amt'] == 0 and r['sell_amt']:
                margin = "100%"
            
            print(f"{r['code']:<22} {r['desc']:<32} {cost_str:<15} {sell_str:<15} {margin}")
            dest_cost += r['cost_amt'] or Decimal('0')
            dest_sell += r['sell_amt'] or Decimal('0')
    
    print(f"\nDestination COGS Total: K{dest_cost}")
    print(f"Destination Sell Total: K{dest_sell}")
    dest_margin = ((dest_sell - dest_cost) / dest_sell * 100).quantize(Decimal('0.1')) if dest_sell > 0 else 0
    print(f"Destination Margin: {dest_margin}% (Sell - Cost / Sell)")
    
    # Summary
    print("\n" + "=" * 90)
    print("SUMMARY")
    print("=" * 90)
    print(f"Origin COGS (AUD):      A$ {origin_cost}")
    print(f"Destination COGS (PGK): K  {dest_cost}")
    print(f"Destination Sell (PGK): K  {dest_sell}")
    print(f"\nNOTE: Origin Sell rates are NOT seeded (Cost-Plus logic to be applied at runtime)")
    print("=" * 90)


if __name__ == "__main__":
    import sys
    with open('import_verification_output.txt', 'w', encoding='utf-8') as f:
        sys.stdout = f
        verify_import_rates()
        sys.stdout = sys.__stdout__
    print("Output written to import_verification_output.txt")
