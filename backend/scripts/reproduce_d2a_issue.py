
import os
import sys
import django
from decimal import Decimal
import uuid

# Setup Django
sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rate_engine.settings')
django.setup()

from pricing_v2.pricing_service_v3 import PricingServiceV3
from pricing_v2.dataclasses_v3 import QuoteInput, ShipmentDetails, Piece, LocationRef
from core.models import Airport, Country

def run():
    print("--- Reproducing Export Prepaid D2A Issue ---")
    
    # POM -> BNE
    # 100kg
    
    # POM -> BNE
    # 100kg
    
    origin = LocationRef(id=uuid.uuid4(), code='POM', name='Port Moresby', country_code='PG', currency_code='PGK')
    destination = LocationRef(id=uuid.uuid4(), code='BNE', name='Brisbane', country_code='AU', currency_code='AUD')
    
    shipment = ShipmentDetails(
        mode='AIR',
        shipment_type='EXPORT',
        incoterm='FCA',
        payment_term='PREPAID',
        service_scope='D2A', 
        is_dangerous_goods=False,
        direction='EXPORT',
        origin_location=origin,
        destination_location=destination,
        pieces=[Piece(pieces=1, weight_kg=Decimal("100.00"), gross_weight_kg=Decimal("100.00"), length_cm=Decimal("100"), width_cm=Decimal("100"), height_cm=Decimal("100"))]
    )
    
    quote_input = QuoteInput(
        customer_id=uuid.uuid4(), # Mock
        contact_id=uuid.uuid4(), # Mock
        output_currency='PGK',
        shipment=shipment,
        overrides=[],
        spot_rates={}
    )
    
    service = PricingServiceV3(quote_input)
    charges = service.calculate_charges()
    
    print(f"Total Cost: {charges.totals.total_cost_pgk}")
    print(f"Total Sell: {charges.totals.total_sell_pgk}")
    
    if not charges.lines:
        print("❌ No charge lines returned!")
    else:
        for line in charges.lines:
            print(f"- {line.service_component_code}: Cost={line.cost_pgk} Sell={line.sell_pgk} ({line.cost_source})")

if __name__ == "__main__":
    run()
