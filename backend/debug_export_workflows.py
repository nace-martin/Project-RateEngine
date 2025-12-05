
import os
import django
import sys
from decimal import Decimal

# Setup Django environment
sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rate_engine.settings')
django.setup()

from pricing_v2.pricing_service_v3 import PricingServiceV3
from pricing_v2.dataclasses_v3 import QuoteInput, ShipmentDetails, Piece, LocationRef
from core.models import Location, Policy
from services.models import ServiceRule

def debug_export_workflows():
    print("Debugging Export Workflows...")
    
    # Ensure Policy exists
    from django.utils import timezone
    Policy.objects.create(name="Debug Policy", margin_pct=Decimal("0.10"), caf_export_pct=Decimal("0.10"), effective_from=timezone.now())

    # Ensure FxSnapshot exists
    from core.models import FxSnapshot
    import json
    from django.utils import timezone
    
    rates = {
        "AUD": {"tt_buy": 0.40, "tt_sell": 0.35}, # Sell Rate 0.35
        "USD": {"tt_buy": 0.30, "tt_sell": 0.25}
    }
    FxSnapshot.objects.create(
        source="DEBUG",
        as_of_timestamp=timezone.now(),
        rates=json.dumps(rates),
        caf_percent=Decimal("0.10") # Not used directly by PricingServiceV3 for CAF, but good to have
    )

    # Ensure Currencies and Countries exist
    from core.models import Country, Currency
    aud, _ = Currency.objects.get_or_create(code="AUD", defaults={"name": "Australian Dollar"})
    pgk, _ = Currency.objects.get_or_create(code="PGK", defaults={"name": "Papua New Guinea Kina"})
    
    au, _ = Country.objects.get_or_create(code="AU", defaults={"name": "Australia", "currency": aud})
    if not au.currency:
        au.currency = aud
        au.save()
        print("Updated AU currency to AUD")

    pg, _ = Country.objects.get_or_create(code="PG", defaults={"name": "Papua New Guinea", "currency": pgk})
    if not pg.currency:
        pg.currency = pgk
        pg.save()
        print("Updated PG currency to PGK")

    # Ensure Locations have Countries
    bne = Location.objects.get(code="BNE")
    if not bne.country:
        bne.country = au
        bne.save()
        print("Updated BNE country to AU")
        
    pom = Location.objects.get(code="POM")
    if not pom.country:
        pom.country = pg
        pom.save()
        print("Updated POM country to PG")

    # 1. Test Prepaid D2D Export (DAP)
    print("\n--- Test 1: Prepaid D2D Export (DAP) ---")
    test_workflow(
        mode='AIR',
        shipment_type='EXPORT',
        incoterm='DAP',
        payment_term='PREPAID',
        service_scope='D2D',
        origin_code='POM',
        dest_code='BNE',
        expected_currency='PGK'
    )

    # 2. Test Collect D2A Export (EXW)
    print("\n--- Test 2: Collect D2A Export (EXW) ---")
    test_workflow(
        mode='AIR',
        shipment_type='EXPORT',
        incoterm='EXW',
        payment_term='COLLECT',
        service_scope='D2A',
        origin_code='POM',
        dest_code='BNE',
        expected_currency='AUD' # BNE currency
    )

def test_workflow(mode, shipment_type, incoterm, payment_term, service_scope, origin_code, dest_code, expected_currency):
    try:
        origin = Location.objects.get(code=origin_code)
        dest = Location.objects.get(code=dest_code)
        
        origin_currency = origin.country.currency.code if origin.country and origin.country.currency else 'PGK'
        dest_currency = dest.country.currency.code if dest.country and dest.country.currency else 'PGK'
        
        origin_ref = LocationRef(id=str(origin.id), code=origin.code, name=origin.name, country_code=origin.country.code, currency_code=origin_currency)
        dest_ref = LocationRef(id=str(dest.id), code=dest.code, name=dest.name, country_code=dest.country.code, currency_code=dest_currency)
        
        shipment = ShipmentDetails(
            mode=mode,
            shipment_type=shipment_type,
            incoterm=incoterm,
            payment_term=payment_term,
            service_scope=service_scope,
            origin_location=origin_ref,
            destination_location=dest_ref,
            pieces=[Piece(length_cm=100, width_cm=100, height_cm=100, gross_weight_kg=100, pieces=1)], # 100kg, 1 CBM (167kg vol)
            is_dangerous_goods=False
        )
        
        quote_input = QuoteInput(
            shipment=shipment,
            customer_id="123", # Dummy
            contact_id="456",
            output_currency=None # Let logic decide
        )
        
        service = PricingServiceV3(quote_input)
        service._resolve_service_rule() # Manually trigger for debug print (it's called in calculate_charges anyway)
        print(f"Resolved Service Rule: {service.service_rule}")
        print(f"Origin Currency: {origin_ref.currency_code}")
        print(f"Dest Currency: {dest_ref.currency_code}")

        charges = service.calculate_charges()
        
        print(f"Output Currency: {charges.totals.total_sell_fcy_currency}")
        print(f"Total Sell (PGK): {charges.totals.total_sell_pgk}")
        print(f"Total Sell (FCY): {charges.totals.total_sell_fcy}")
        
        # Verify Currency
        if charges.totals.total_sell_fcy_currency == expected_currency:
             print(f"[OK] Currency matches expected: {expected_currency}")
        else:
             print(f"[FAIL] Currency mismatch! Expected {expected_currency}, got {charges.totals.total_sell_fcy_currency}")

        # Verify Calculation Logic (Spot Check)
        # PGK Cost -> Sell PGK (Margin) -> Sell FCY (FX + Buffer)
        # Example: PICKUP_SELL (250.00 PGK)
        # Margin 10% (Policy default in script) -> 275.00 PGK
        # FX Rate (PGK->AUD) = 0.35 (assumed)
        # Buffer 10% (Export CAF) -> Rate 0.385
        # Sell FCY = 275.00 * 0.385 = 105.875 AUD
        
        # We need to know the actual rates used to verify precisely.
        # For now, we print the components and check if FCY > PGK * 0.35 (indicating buffer applied)
        
        print("Components:")
        for line in charges.lines:
            print(f" - {line.service_component_code}: {line.sell_pgk} PGK / {line.sell_fcy} {line.sell_fcy_currency} ({line.cost_source})")
            if line.service_component_code == 'PICKUP_SELL' and expected_currency == 'AUD':
                # Check if buffer applied
                # Base Rate (PGK->AUD) is usually around 0.35-0.40. 
                # If Sell FCY / Sell PGK > 0.35, it's likely working.
                implied_rate = line.sell_fcy / line.sell_pgk if line.sell_pgk else 0
                print(f"   -> Implied FX Rate (incl Buffer): {implied_rate}")
            
    except Exception as e:
        print(f"[ERROR] Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    debug_export_workflows()
