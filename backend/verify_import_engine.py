"""
Verify Import Pricing Engine
=============================
Tests the ImportPricingEngine against PricingPolicy.md rules.
"""
import os
import django
from decimal import Decimal
from datetime import date

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "rate_engine.settings")
django.setup()

from pricing_v4.engine.import_engine import ImportPricingEngine, PaymentTerm, ServiceScope


def verify_import_collect_d2d():
    """
    Test Case: Import Collect D2D (Row 3 in PricingPolicy.md)
    
    Expected:
    - Quote currency: PGK
    - Active legs: Origin + Freight + Destination
    - FX applied to: Origin + Freight (FCY→PGK, TT BUY, CAF↓)
    - Margin applied to: Origin + Freight
    - Destination: Explicit sell rates (no margin)
    """
    print("=" * 90)
    print("TEST: Import Collect D2D (BNE -> POM, 100kg)")
    print("=" * 90)
    
    engine = ImportPricingEngine(
        quote_date=date(2025, 1, 1),
        origin='BNE',
        destination='POM',
        chargeable_weight_kg=Decimal('100.00'),
        payment_term=PaymentTerm.COLLECT,
        service_scope=ServiceScope.D2D,
        tt_buy=Decimal('0.35'),
        caf_rate=Decimal('0.05'),
        margin_rate=Decimal('0.20'),
    )
    
    quote = engine.calculate_quote()
    
    print(f"\nQuote Currency: {quote.quote_currency}")
    print(f"Payment Term: {quote.payment_term}")
    print(f"Service Scope: {quote.service_scope}")
    print(f"TT BUY: {quote.fx_rate_used}")
    print(f"Effective FX Rate (TT BUY × (1-CAF)): {quote.effective_fx_rate}")
    print(f"CAF: {quote.caf_rate}")
    
    print("\n--- ORIGIN CHARGES ---")
    print(f"{'Code':<22} {'Cost':<15} {'Sell':<15} {'FX':<5} {'Margin'}")
    print("-" * 70)
    for line in quote.origin_lines:
        fx = "Yes" if line.fx_applied else "No"
        print(f"{line.product_code:<22} {line.cost_currency} {line.cost_amount:>8} {line.sell_currency} {line.sell_amount:>8} {fx:<5} {line.margin_percent}%")
    
    print("\n--- FREIGHT CHARGES ---")
    for line in quote.freight_lines:
        fx = "Yes" if line.fx_applied else "No"
        print(f"{line.product_code:<22} {line.cost_currency} {line.cost_amount:>8} {line.sell_currency} {line.sell_amount:>8} {fx:<5} {line.margin_percent}%")
    
    print("\n--- DESTINATION CHARGES ---")
    for line in quote.destination_lines:
        fx = "Yes" if line.fx_applied else "No"
        margin = f"{line.margin_percent}%" if line.margin_applied else "(Explicit)"
        print(f"{line.product_code:<22} {line.cost_currency} {line.cost_amount:>8} {line.sell_currency} {line.sell_amount:>8} {fx:<5} {margin}")
    
    print("\n" + "=" * 70)
    print("TOTALS")
    print("=" * 70)
    print(f"Total Sell: {quote.quote_currency} {quote.total_sell}")
    
    # Validation
    print("\n--- VALIDATION ---")
    
    # Check FX formula
    test_aud = Decimal('1140.00')  # Approx origin COGS
    expected_effective_rate = Decimal('0.35') * (Decimal('1') - Decimal('0.05'))
    expected_pgk = test_aud / expected_effective_rate
    print(f"FX Check: AUD {test_aud} ÷ {expected_effective_rate} = PGK {expected_pgk:.2f}")
    
    # Check margin is applied after FX
    expected_with_margin = expected_pgk * Decimal('1.20')
    print(f"With 20% Margin: PGK {expected_with_margin:.2f}")
    
    print("=" * 90)


def verify_import_prepaid_a2d():
    """
    Test Case: Import Prepaid A2D (Row 1 in PricingPolicy.md)
    
    Expected:
    - Quote currency: FCY (AUD)
    - Active legs: Destination only
    - FX applied to: Destination (PGK→FCY, TT SELL, CAF↓)
    """
    print("\n" + "=" * 90)
    print("TEST: Import Prepaid A2D (BNE -> POM, 100kg)")
    print("=" * 90)
    
    engine = ImportPricingEngine(
        quote_date=date(2025, 1, 1),
        origin='BNE',
        destination='POM',
        chargeable_weight_kg=Decimal('100.00'),
        payment_term=PaymentTerm.PREPAID,
        service_scope=ServiceScope.A2D,
        tt_sell=Decimal('0.36'),
        caf_rate=Decimal('0.05'),
    )
    
    quote = engine.calculate_quote()
    
    print(f"\nQuote Currency: {quote.quote_currency}")
    print(f"Payment Term: {quote.payment_term}")
    print(f"Service Scope: {quote.service_scope}")
    
    print("\n--- DESTINATION CHARGES (Converted to AUD) ---")
    print(f"{'Code':<22} {'Cost (PGK)':<15} {'Sell (AUD)':<15} {'FX'}")
    print("-" * 60)
    for line in quote.destination_lines:
        fx = "Yes" if line.fx_applied else "No"
        print(f"{line.product_code:<22} K {line.cost_amount:>8} A$ {line.sell_amount:>8} {fx}")
    
    print(f"\nTotal Sell: {quote.quote_currency} {quote.total_sell}")
    print("=" * 90)


if __name__ == "__main__":
    import sys
    with open('engine_verification_output.txt', 'w', encoding='utf-8') as f:
        sys.stdout = f
        verify_import_collect_d2d()
        verify_import_prepaid_a2d()
        sys.stdout = sys.__stdout__
    print("Output written to engine_verification_output.txt")
