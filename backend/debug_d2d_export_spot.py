
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
from services.models import ServiceRule, ServiceComponent

def debug_d2d_export_spot():
    # Redirect stdout to file (artifact path)
    output_path = r'C:\Users\commercial.manager\.gemini\antigravity\brain\b0b97559-78cf-43cd-b15a-4d434ece4944\debug_d2d_export_output.txt'
    with open(output_path, 'w') as f:
        sys.stdout = f
        
        print("Debugging D2D Export Spot (POM -> BNE)...")

        # 1. Setup Data
        try:
            origin = Location.objects.get(code="POM")
            dest = Location.objects.get(code="BNE")
        except Location.DoesNotExist:
            print("Error: Locations not found.")
            return

        # D2D Export
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
            service_scope="D2D", # D2D
            is_dangerous_goods=False,
            pieces=[Piece(pieces=1, length_cm=Decimal("10"), width_cm=Decimal("10"), height_cm=Decimal("10"), gross_weight_kg=Decimal("10.0"))]
        )

        # Spot Rates: Agent Charges = 100 AUD
        spot_rates = {
            'DST_CHARGES': {
                'amount': '100.00',
                'currency': 'AUD'
            }
        }

        quote_input = QuoteInput(
            customer_id=uuid.uuid4(),
            contact_id=uuid.uuid4(),
            shipment=shipment,
            output_currency="PGK",
            spot_rates=spot_rates
        )

        # 2. Check Service Rule (We might need to create one if it doesn't exist for D2D)
        # Assuming D2D rule exists or we might need to mock it/create it.
        # Let's check if D2D rule exists first.
        rule = ServiceRule.objects.filter(
            mode=shipment.mode,
            direction=shipment.shipment_type,
            incoterm=shipment.incoterm,
            payment_term=shipment.payment_term,
            service_scope=shipment.service_scope,
            is_active=True
        ).first()
        
        if not rule:
            print("WARNING: No D2D Rule found. Creating temporary rule for testing...")
            # Create a temporary rule or just proceed and hope the engine handles it?
            # The engine needs a rule to know components.
            # If no rule, it won't find DST_CHARGES unless injected.
            # PricingServiceV3 injects DST_CHARGES if in spot_rates.
            pass

        # 3. Run Calculation
        print("\nRunning Pricing Service...")
        service = PricingServiceV3(quote_input)
        charges = service.calculate_charges()

        print("\nResults:")
        dst_line = None
        for line in charges.lines:
            print(f" - {line.service_component_code}: Cost={line.cost_pgk} ({line.cost_fcy} {line.cost_fcy_currency}), Sell={line.sell_pgk}")
            if line.service_component_code == 'DST_CHARGES':
                dst_line = line
        
        if dst_line:
            print(f"\nVerifying DST_CHARGES Margin:")
            print(f"Cost PGK: {dst_line.cost_pgk}")
            print(f"Sell PGK: {dst_line.sell_pgk}")
            
            # Expected: Cost = 100 AUD * FX Buy (with 5% buffer)
            # Sell = Cost * 1.20 (20% margin)
            
            # Let's calculate implied margin
            if dst_line.cost_pgk > 0:
                margin = (dst_line.sell_pgk - dst_line.cost_pgk) / dst_line.cost_pgk
                print(f"Implied Margin: {margin:.4f} (Expected ~0.2000)")
        else:
            print("\nERROR: DST_CHARGES line not found!")

if __name__ == '__main__':
    debug_d2d_export_spot()
