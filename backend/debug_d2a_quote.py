
import os
import django
import sys
import uuid
from decimal import Decimal

# Setup Django environment
sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rate_engine.settings')
django.setup()

from pricing_v2.pricing_service_v3 import PricingServiceV3
from pricing_v2.dataclasses_v3 import QuoteInput, ShipmentDetails, Piece, LocationRef
from core.models import Location
from services.models import ServiceRule

def debug_d2a_quote():
    # Redirect stdout to file (artifact path)
    output_path = r'C:\Users\commercial.manager\.gemini\antigravity\brain\b0b97559-78cf-43cd-b15a-4d434ece4944\debug_d2a_output.txt'
    with open(output_path, 'w') as f:
        sys.stdout = f
        
        print("Debugging D2A Export Quote (POM -> BNE)...")

        # 1. Setup Data
        try:
            origin = Location.objects.get(code="POM")
            dest = Location.objects.get(code="BNE")
        except Location.DoesNotExist:
            print("Error: Locations not found.")
            return

        # Match the screenshot: AIR, EXW, PREPAID, D2A
        shipment = ShipmentDetails(
            origin_location=LocationRef(
                id=origin.id, 
                code=origin.code, 
                name=origin.name, 
                country_code=origin.country.code if origin.country else None, 
                currency_code=origin.country.currency.code if origin.country and origin.country.currency else None
            ),
            destination_location=LocationRef(
                id=dest.id, 
                code=dest.code, 
                name=dest.name, 
                country_code=dest.country.code if dest.country else None, 
                currency_code=dest.country.currency.code if dest.country and dest.country.currency else None
            ),
            mode="AIR",
            shipment_type="EXPORT",
            incoterm="EXW", 
            payment_term="PREPAID",
            service_scope="D2A",
            is_dangerous_goods=False,
            pieces=[Piece(pieces=1, length_cm=Decimal("10"), width_cm=Decimal("10"), height_cm=Decimal("10"), gross_weight_kg=Decimal("10.0"))]
        )

        quote_input = QuoteInput(
            customer_id=uuid.uuid4(),
            contact_id=uuid.uuid4(),
            shipment=shipment,
            output_currency="PGK"
        )

        # 2. Check Service Rule
        print(f"\nChecking Service Rule for: {shipment.mode} {shipment.shipment_type} {shipment.incoterm} {shipment.payment_term} {shipment.service_scope}")
        rule = ServiceRule.objects.filter(
            mode=shipment.mode,
            direction=shipment.shipment_type,
            incoterm=shipment.incoterm,
            payment_term=shipment.payment_term,
            service_scope=shipment.service_scope,
            is_active=True
        ).first()
        
        if rule:
            print(f"Found Service Rule: {rule}")
            print("Components:")
            for rc in rule.rule_components.all():
                print(f" - {rc.service_component.code} ({rc.service_component.description})")
        else:
            print("ERROR: No matching Service Rule found!")
            # Try finding *any* rule for D2A Export to see what's available
            alternatives = ServiceRule.objects.filter(
                mode="AIR", 
                direction="EXPORT", 
                service_scope="D2A"
            )
            print("\nAvailable D2A Export Rules:")
            for r in alternatives:
                print(f" - Incoterm: {r.incoterm}, Payment: {r.payment_term}")

        # 3. Run Calculation
        print("\nRunning Pricing Service...")
        service = PricingServiceV3(quote_input)
        charges = service.calculate_charges()

        print("\nResults:")
        for line in charges.lines:
            print(f" - {line.service_component_code}: Cost={line.cost_pgk}, Sell={line.sell_pgk}, Missing={line.is_rate_missing}")
        
        print(f"\nTotal Sell: {charges.totals.total_sell_pgk}")
        print(f"Has Missing Rates: {charges.totals.has_missing_rates}")

if __name__ == '__main__':
    debug_d2a_quote()
