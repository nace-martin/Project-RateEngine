from decimal import Decimal
import os
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rate_engine.settings')
django.setup()

from pricing_v4.engine.domestic_engine import DomesticPricingEngine

def verify_domestic_pom_lae():
    print("=" * 60)
    print("VERIFYING DOMESTIC: POM -> LAE (100kg)")
    print("=" * 60)
    
    # Init engine
    engine = DomesticPricingEngine(
        cogs_origin='POM',
        destination='LAE',
        weight_kg=100
    )
    
    quote = engine.calculate_quote()
    
    print(f"\nBreakdown (COST):")
    for charge in quote.cogs_breakdown:
        print(f"  - {charge.description}: K{charge.amount:,.2f}")
    print(f"  TOTAL COST: K{quote.total_cost:,.2f}")
    
    print(f"\nBreakdown (SELL):")
    for charge in quote.sell_breakdown:
        print(f"  - {charge.description}: K{charge.amount:,.2f}")
    
    # Calculate GST (10%)
    gst = quote.total_sell * Decimal('0.10')
    total_inc_gst = quote.total_sell + gst
    
    print(f"  SUBTOTAL: K{quote.total_sell:,.2f}")
    print(f"  GST (10%): K{gst:,.2f}")
    print(f"  TOTAL SELL (inc GST): K{total_inc_gst:,.2f}")
    
    # Verification Assertions
    # 1. Freight (POM->LAE)
    #    Cost: K6.10/kg * 100kg = K610.00 (Unchanged)
    #    Sell: K7.10/kg * 100kg = K710.00 (Updated)
    # 2. Surcharges (Global)
    #    Doc Fee: Cost K35 (Doc) + K35 (Term) = K70; Sell K70 (AWB)
    #    Security: Cost K5.00 (Flat) = K5.00; Sell K0.20/kg * 100 = K20
    #    FSC: Cost K0.30/kg * 100 = K30; Sell K0.35/kg * 100 = K35
    
    expected_cost = Decimal('610.00') + Decimal('35.00') + Decimal('35.00') + Decimal('5.00') + Decimal('30.00')
    expected_sell = Decimal('710.00') + Decimal('70.00') + Decimal('20.00') + Decimal('35.00')
    
    print("\nVerification:")
    print(f"  Expected Cost: K{expected_cost:,.2f} vs Actual: K{quote.total_cost:,.2f} [{'✅' if quote.total_cost == expected_cost else '❌'}]")
    print(f"  Expected Sell: K{expected_sell:,.2f} vs Actual: K{quote.total_sell:,.2f} [{'✅' if quote.total_sell == expected_sell else '❌'}]")

def verify_cartage_restrictions():
    print("\n" + "=" * 60)
    print("VERIFYING CARTAGE RESTRICTIONS")
    print("=" * 60)
    
    test_cases = [
        ('POM', 'LAE', 'D2D', True),  # Valid: Both POM and LAE allow door
        ('POM', 'GKA', 'A2A', True),  # Valid: Airport to Airport always ok
        ('POM', 'GKA', 'D2A', True),  # Valid: POM allows Pickup, GKA Airport
        ('POM', 'GKA', 'A2D', False), # Invalid: GKA does not allow Delivery
        ('GKA', 'POM', 'D2A', False), # Invalid: GKA does not allow Pickup
        ('GKA', 'POM', 'D2D', False), # Invalid: GKA does not allow Pickup
    ]
    
    for origin, dest, scope, should_pass in test_cases:
        try:
            DomesticPricingEngine(origin, dest, 100, service_scope=scope)
            result = "PASSED"
            success = should_pass
        except ValueError as e:
            result = f"FAILED ({str(e)})"
            success = not should_pass
            
        status = "✅" if success else "❌"
        print(f"  {origin}->{dest} [{scope}]: {result} {status}")

if __name__ == '__main__':
    verify_domestic_pom_lae()
    verify_cartage_restrictions()
