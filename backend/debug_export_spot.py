import os
import django
import sys
from decimal import Decimal

# Setup Django environment
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rate_engine.settings')
django.setup()

from pricing_v2.pricing_service_v3 import PricingServiceV3
from pricing_v2.dataclasses_v3 import QuoteInput, ShipmentDetails, Piece, LocationRef
from core.models import Location, FxSnapshot, Policy
from services.models import ServiceComponent, ServiceRule, ServiceRuleComponent
import uuid

def run_debug():
    print("DEBUG: Starting Export Spot Workflow Verification...")

    # 1. Setup Data
    # Ensure Policy exists with correct CAF
    policy = Policy.objects.filter(is_active=True).latest('effective_from')
    print(f"DEBUG: Using Policy {policy.name} (Export CAF: {policy.caf_export_pct}, Import CAF: {policy.caf_import_pct})")

    # Ensure FxSnapshot
    fx = FxSnapshot.objects.latest('as_of_timestamp')
    print(f"DEBUG: Using FxSnapshot {fx.id}")

    # Locations
    pom = Location.objects.get(code='POM')
    bne = Location.objects.get(code='BNE')
    
    pom_ref = LocationRef(id=pom.id, code=pom.code, name=pom.name, country_code='PG', currency_code='PGK')
    bne_ref = LocationRef(id=bne.id, code=bne.code, name=bne.name, country_code='AU', currency_code='AUD')

    # Pieces
    pieces = [Piece(pieces=1, length_cm=Decimal("100"), width_cm=Decimal("100"), height_cm=Decimal("100"), gross_weight_kg=Decimal("200"))]

    # Ensure DST_CHARGES exists
    ServiceComponent.objects.get_or_create(
        code='DST_CHARGES',
        defaults={
            'description': 'Destination Charges',
            'category': 'DESTINATION',
            'cost_type': 'RATE_OFFER',
            'is_active': True
        }
    )

    # --- TEST 1: Prepaid D2D Export Spot ---
    print("\n--- TEST 1: Prepaid D2D Export Spot ---")
    # Scenario:
    # - A2A Spot Rate: 500 PGK (FRT_AIR_EXP)
    # - Dest Charges: 100 USD (DST_CHARGES)
    # Expected:
    # - FRT_AIR_EXP: 500 PGK Cost -> Sell (Margin)
    # - DST_CHARGES: 100 USD -> PGK (Buy Rate + 5% Buffer) -> Sell (Margin)
    
    spot_rates_d2d = {
        'FRT_AIR_EXP': {'amount': '500.00', 'currency': 'PGK'},
        'DST_CHARGES': {'amount': '100.00', 'currency': 'USD'}
    }

    shipment_d2d = ShipmentDetails(
        mode='AIR',
        shipment_type='EXPORT',
        incoterm='DAP',
        payment_term='PREPAID',
        is_dangerous_goods=False,
        pieces=pieces,
        service_scope='D2D',
        origin_location=pom_ref,
        destination_location=bne_ref
    )

    input_d2d = QuoteInput(
        customer_id=uuid.uuid4(),
        contact_id=uuid.uuid4(),
        output_currency='PGK',
        shipment=shipment_d2d,
        spot_rates=spot_rates_d2d
    )

    service_d2d = PricingServiceV3(input_d2d)
    charges_d2d = service_d2d.calculate_charges()

    print("D2D Charges:")
    frt_found = False
    dst_found = False
    
    for line in charges_d2d.lines:
        if line.service_component_code == 'FRT_AIR_EXP':
            frt_found = True
            print(f" - FRT_AIR_EXP: Cost {line.cost_pgk} PGK (Source: {line.cost_source})")
            if line.cost_pgk != Decimal("500.00"):
                print("   [FAIL] Expected 500.00 PGK")
            else:
                print("   [PASS] Cost matches Spot Rate")

        if line.service_component_code == 'DST_CHARGES':
            dst_found = True
            print(f" - DST_CHARGES: Cost {line.cost_pgk} PGK (FCY: {line.cost_fcy} {line.cost_fcy_currency})")
            print(f"   Exchange Rate Used: {line.exchange_rate}")
            
            # Verify FX Logic (Buy Rate + 5% Buffer)
            # 1 USD = X PGK.
            # Rate = _get_exchange_rate('USD', 'PGK', apply_caf=True, force_import=True)
            # Standard Buy Rate (USD->PGK) = 1 / tt_buy
            # Buffered Rate = (1 / tt_buy) * (1 / (1 - 0.05)) ?? No, logic is:
            # rate = tt_buy * (1 - 0.05)
            # result = 1 / rate
            
            # Let's check manual calc
            # Assuming USD Buy is ~0.28 (example)
            # Buffered Rate = 0.28 * 0.95 = 0.266
            # Cost PGK = 100 / 0.266 = ~375.94
            
            # We can't know exact rate without checking DB, but we can check if it differs from standard export logic
            # Export CAF is 10%. If it used 10%, rate would be 0.28 * 0.90 = 0.252. Cost = 396.82.
            # So checking the rate used helps.
            
    if not frt_found:
        print(" [FAIL] FRT_AIR_EXP not found!")
    if not dst_found:
        print(" [FAIL] DST_CHARGES not found (Injection failed)!")


    # --- TEST 2: Collect D2A Export Spot ---
    print("\n--- TEST 2: Collect D2A Export Spot ---")
    # Scenario:
    # - A2A Spot Rate: 600 PGK (FRT_AIR_EXP)
    # - Output Currency: AUD
    # Expected:
    # - FRT_AIR_EXP: 600 PGK Cost
    # - Total Sell converted to AUD using Sell Rate + 10% Buffer
    
    spot_rates_d2a = {
        'FRT_AIR_EXP': {'amount': '600.00', 'currency': 'PGK'}
    }

    shipment_d2a = ShipmentDetails(
        mode='AIR',
        shipment_type='EXPORT',
        incoterm='EXW',
        payment_term='COLLECT',
        is_dangerous_goods=False,
        pieces=pieces,
        service_scope='D2A',
        origin_location=pom_ref,
        destination_location=bne_ref
    )

    input_d2a = QuoteInput(
        customer_id=uuid.uuid4(),
        contact_id=uuid.uuid4(),
        output_currency='AUD', # Override to AUD
        shipment=shipment_d2a,
        spot_rates=spot_rates_d2a
    )

    service_d2a = PricingServiceV3(input_d2a)
    charges_d2a = service_d2a.calculate_charges()
    
    print(f"D2A Output Currency: {charges_d2a.totals.total_sell_fcy_currency}")
    print(f"Total Sell PGK: {charges_d2a.totals.total_sell_pgk}")
    print(f"Total Sell FCY: {charges_d2a.totals.total_sell_fcy}")
    
    # Verify Implied FX Rate
    if charges_d2a.totals.total_sell_pgk > 0:
        implied_rate = charges_d2a.totals.total_sell_fcy / charges_d2a.totals.total_sell_pgk
        print(f"Implied FX Rate (FCY/PGK): {implied_rate}")
        
        # Expected: Sell Rate (AUD) * 1.10
        # If AUD Sell is 0.35, expected is 0.385.
        
    for line in charges_d2a.lines:
        if line.service_component_code == 'FRT_AIR_EXP':
            print(f" - FRT_AIR_EXP: Cost {line.cost_pgk} PGK")
            if line.cost_pgk != Decimal("600.00"):
                print("   [FAIL] Expected 600.00 PGK")
            else:
                print("   [PASS] Cost matches Spot Rate")

    # --- TEST 3: All-In Spot Rate (Prepaid D2D) ---
    print("\n--- TEST 3: All-In Spot Rate (Prepaid D2D) ---")
    # Scenario: User enters 3761.60 PGK as All-In Spot Rate.
    # Expectation: FRT_AIR_EXP = 3761.60, Surcharges (Fuel, Security) suppressed.
    
    spot_rates_all_in = {
        'FRT_AIR_EXP': {
            'amount': '3761.60',
            'currency': 'PGK',
            'is_all_in': True
        }
    }
    
    quote_input_all_in = QuoteInput(
        customer_id=uuid.uuid4(),
        contact_id=uuid.uuid4(),
        output_currency='PGK',
        shipment=shipment_d2d, # Reuse D2D shipment
        spot_rates=spot_rates_all_in
    )
    
    service_all_in = PricingServiceV3(quote_input_all_in)
    charges_all_in = service_all_in.calculate_charges()
    
    frt_line = next((l for l in charges_all_in.lines if l.service_component_code == 'FRT_AIR_EXP'), None)
    fuel_line = next((l for l in charges_all_in.lines if l.service_component_code == 'FRT_AIR_FUEL'), None)
    sec_line = next((l for l in charges_all_in.lines if l.service_component_code == 'SECURITY_SELL'), None)
    
    if frt_line:
        print(f"FRT_AIR_EXP Cost: {frt_line.cost_pgk} PGK (Expected: 3761.60)")
    else:
        print("FRT_AIR_EXP not found!")
        
    if fuel_line:
        print(f"FRT_AIR_FUEL Found: {fuel_line.cost_pgk} PGK (Expected: None/Suppressed)")
    else:
        print("FRT_AIR_FUEL Suppressed (Correct)")
        
    if sec_line:
        print(f"SECURITY_SELL Found: {sec_line.cost_pgk} PGK (Expected: None/Suppressed)")
    else:
        print("SECURITY_SELL Suppressed (Correct)")

if __name__ == "__main__":
    run_debug()
