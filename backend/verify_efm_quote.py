import os
import django
from decimal import Decimal
from django.utils import timezone

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "rate_engine.settings")
django.setup()

from core.models import Location, Country, Policy, FxSnapshot
from pricing_v3.models import RateCard, ComponentMargin
from services.models import ServiceComponent, ServiceRule
from quotes.models import Quote
from parties.models import Company
from pricing_v3.resolvers import QuoteContextBuilder, BuyChargeResolver
from pricing_v3.charge_engine import ChargeEngine

def verify_quote():
    print("--- Verifying EFM Quote on Seeded DB ---")
    
    # 1. Fetch Master Data
    try:
        bne = Location.objects.get(code="BNE")
        pom = Location.objects.get(code="POM")
        customer = Company.objects.filter(company_type="CUSTOMER").first() or Company.objects.create(name="Test Customer", company_type="CUSTOMER")
        print("Master Data Found (Locations, Customer)")
    except Exception as e:
        print(f"Master Data Missing: {e}")
        return

    # 2. Check Policy/FX
    policy = Policy.objects.filter(is_active=True).first()
    if not policy:
        print("No active policy found, creating default.")
        policy = Policy.objects.create(name="Default Policy", effective_from=timezone.now())
    
    fx = FxSnapshot.objects.latest('as_of_timestamp')
    print(f"FX Snapshot Found (Source: {fx.source})")

    # 3. Create Quote
    quote = Quote.objects.create(
        quote_number="Q-VERIFY-SEED",
        customer=customer,
        mode="AIR",
        shipment_type="IMPORT",
        incoterm="EXW",
        payment_term="COLLECT",
        service_scope="D2D",
        origin_location=bne,
        destination_location=pom,
        status="DRAFT",
        fx_snapshot=fx,
        output_currency="PGK"
    )
    print(f"Quote Created: {quote.quote_number}")

    # 4. Build Context
    context = QuoteContextBuilder.build(quote.id)
    # Mock Weight (since we don't have shipment/pieces linked yet in this simple script)
    context.chargeable_weight = Decimal("100.00") 
    print(f"Chargeable Weight: {context.chargeable_weight} kg")

    # 5. Resolve Service Rule
    rule = ServiceRule.objects.filter(
        mode=context.quote.mode,
        direction=context.quote.shipment_type,
        incoterm=context.quote.incoterm,
        payment_term=context.quote.payment_term,
        service_scope=context.quote.service_scope,
        is_active=True
    ).first()
    
    if not rule:
        print("Service Rule NOT Found!")
        return
    print(f"Service Rule Found: {rule.description}")
    
    components = list(rule.service_components.all())
    print(f"Components: {[c.code for c in components]}")

    # 6. Resolve Buy Charges
    resolver = BuyChargeResolver(context)
    buy_charges = resolver.resolve_all(components)
    
    print("\n--- Buy Charges ---")
    found_codes = []
    for charge in buy_charges:
        amount = charge.flat_amount or charge.rate_per_unit
        # If rate_per_unit, calculate total for display
        if charge.rate_per_unit:
             total = charge.rate_per_unit * context.chargeable_weight
             if charge.min_charge:
                 total = max(total, charge.min_charge)
             display_amount = f"{total} (Rate: {charge.rate_per_unit}, Min: {charge.min_charge})"
        else:
            display_amount = amount
            
        print(f"{charge.component_code}: {display_amount} {charge.currency} ({charge.source})")
        found_codes.append(charge.component_code)

    # Verify expected charges
    expected = ["PICKUP", "FRT_AIR", "CLEARANCE", "CARTAGE"]
    missing = [c for c in expected if c not in found_codes]
    if missing:
        print(f"Missing Charges: {missing}")
    else:
        print("All Expected Charges Found")

    # 7. Run Charge Engine
    engine = ChargeEngine(context)
    result = engine.calculate_sell_charges(buy_charges)
    
    print("\n--- Sell Lines ---")
    for line in result.sell_lines:
        print(f"{line.component_code or line.line_type}: Cost {line.cost_pgk} PGK -> Sell {line.sell_pgk} PGK")

    print(f"\nTotal Sell: {result.total_sell_pgk} {result.sell_currency}")
    
    # Cleanup
    quote.delete()
    print("\nVerification Complete (Quote deleted)")

if __name__ == "__main__":
    verify_quote()
