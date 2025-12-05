import os
import django
import uuid
import sys
import traceback
from decimal import Decimal

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "rate_engine.settings")
django.setup()

from services.models import ServiceRule
from pricing_v2.pricing_service_v3 import PricingServiceV3
from pricing_v2.dataclasses_v3 import QuoteInput, ShipmentDetails, Piece, LocationRef
from core.models import Location

def debug_missing_charges():
    output_path = r'C:\Users\commercial.manager\.gemini\antigravity\brain\b0b97559-78cf-43cd-b15a-4d434ece4944\debug_output_v3.txt'
    with open(output_path, 'w') as f:
        def log(msg):
            print(msg)
            f.write(str(msg) + '\n')
            f.flush()
            
        log("Debugging Missing Charges - Round 2...")
        
        # 1. Check Service Rule
        log("\n--- Checking Service Rule ---")
        rule = ServiceRule.objects.filter(
            mode='AIR',
            direction='EXPORT',
            service_scope='D2D',
            payment_term='PREPAID',
            incoterm='EXW'
        ).first()
        
        if not rule:
            log("CRITICAL: Service Rule NOT FOUND for AIR/EXPORT/D2D/PREPAID/EXW")
        else:
            log(f"Found Rule: {rule.id}")
            log(f" - Active: {rule.is_active}")
            log(f" - Output Currency: {rule.output_currency_type}")
            
            # Check Components
            components = rule.rule_components.all().select_related('service_component')
            log(f" - Component Count: {components.count()}")
            for rc in components:
                comp = rc.service_component
                log(f"   - {comp.code} ({comp.description}) [Owner: {rc.leg_owner}]")
                log(f"     - Cost Source: {comp.cost_source}")
                log(f"     - Base Cost: {comp.base_pgk_cost}")

        # 2. Run Pricing Service
        log("\n--- Running Pricing Service ---")
        try:
            pom = Location.objects.get(code='POM')
            bne = Location.objects.get(code='BNE')
            
            shipment = ShipmentDetails(
                mode='AIR',
                shipment_type='EXPORT',
                incoterm='EXW',
                payment_term='PREPAID',
                is_dangerous_goods=False,
                pieces=[Piece(pieces=1, length_cm=Decimal('50'), width_cm=Decimal('50'), height_cm=Decimal('50'), gross_weight_kg=Decimal('100'))],
                service_scope='D2D',
                direction='EXPORT',
                origin_location=LocationRef(id=pom.id, code=pom.code, name=pom.name, country_code='PG', currency_code='PGK'),
                destination_location=LocationRef(id=bne.id, code=bne.code, name=bne.name, country_code='AU', currency_code='AUD'),
            )
            
            quote_input = QuoteInput(
                customer_id=uuid.uuid4(),
                contact_id=uuid.uuid4(),
                output_currency=None,
                shipment=shipment
            )
            
            service = PricingServiceV3(quote_input)
            
            # Hook into internal methods to debug
            service._resolve_service_rule()
            log(f"Service resolved rule: {service.service_rule}")
            
            comps = service._get_service_components()
            log(f"Service found {len(comps)} components.")
            
            charges = service.calculate_charges()
            
            log(f"Calculated {len(charges.lines)} charge lines.")
            for line in charges.lines:
                log(f" - {line.service_component_code}: Sell {line.sell_pgk} PGK (Cost: {line.cost_pgk})")
                if line.is_rate_missing:
                    log(f"   *** RATE MISSING ***")
                    
        except Exception as e:
            log(f"Error running pricing service: {e}")
            log(traceback.format_exc())

if __name__ == "__main__":
    debug_missing_charges()
