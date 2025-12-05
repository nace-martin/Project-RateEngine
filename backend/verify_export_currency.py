import os
import django
from decimal import Decimal

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "rate_engine.settings")
django.setup()

from pricing_v2.pricing_service_v3 import PricingServiceV3
from pricing_v2.dataclasses_v3 import QuoteInput, ShipmentDetails, Piece, LocationRef
from core.models import Location
from services.models import ServiceRule

def verify_export_currency():
    print("Verifying Export Currency Logic...")
    
    # 1. Setup Data
    pom = Location.objects.get(code='POM')
    bne = Location.objects.get(code='BNE')
    
    # 2. Create Quote Input (Export D2D Prepaid)
    shipment = ShipmentDetails(
        mode='AIR',
        shipment_type='EXPORT',
        incoterm='DAP', # D2D
        payment_term='PREPAID',
        is_dangerous_goods=False,
        pieces=[Piece(pieces=1, length_cm=Decimal('50'), width_cm=Decimal('50'), height_cm=Decimal('50'), gross_weight_kg=Decimal('100'))],
        service_scope='D2D',
        direction='EXPORT',
        origin_location=LocationRef(id=pom.id, code=pom.code, name=pom.name, country_code='PG', currency_code='PGK'),
        destination_location=LocationRef(id=bne.id, code=bne.code, name=bne.name, country_code='AU', currency_code='AUD'),
    )
    
    quote_input = QuoteInput(
        customer_id=uuid.uuid4(), # Fake ID
        contact_id=uuid.uuid4(),
        output_currency=None, # Let it derive
        shipment=shipment
    )
    
    # 3. Run Service
    service = PricingServiceV3(quote_input)
    charges = service.calculate_charges()
    
    print(f"Output Currency: {service.output_currency_code}")
    print(f"Service Rule Used: {service.service_rule.output_currency_type if service.service_rule else 'None'}")
    
    if service.output_currency_code == 'PGK':
        print("SUCCESS: Output currency is PGK.")
    else:
        print(f"FAILURE: Output currency is {service.output_currency_code}, expected PGK.")

import uuid
if __name__ == "__main__":
    verify_export_currency()
