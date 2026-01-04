import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rate_engine.settings')
django.setup()

from pricing_v4.adapter import PricingServiceV4Adapter
from pricing_v2.dataclasses_v3 import QuoteInput, ShipmentDetails, LocationRef, Piece
from decimal import Decimal
from datetime import date
import uuid

# Mock a QuoteInput for BNE-POM Import D2D Collect
origin_ref = LocationRef(id=uuid.uuid4(), code='BNE', name='Brisbane', country_code='AU', currency_code='AUD')
dest_ref = LocationRef(id=uuid.uuid4(), code='POM', name='Port Moresby', country_code='PG', currency_code='PGK')

shipment = ShipmentDetails(
    mode='AIR',
    shipment_type='IMPORT',
    incoterm='DDU',
    payment_term='COLLECT',
    is_dangerous_goods=False,
    pieces=[Piece(pieces=1, length_cm=Decimal('50'), width_cm=Decimal('50'), height_cm=Decimal('50'), gross_weight_kg=Decimal('100'))],
    service_scope='D2D',
    direction='IMPORT',
    origin_location=origin_ref,
    destination_location=dest_ref
)

quote_input = QuoteInput(
    customer_id=uuid.uuid4(),
    contact_id=uuid.uuid4(),
    output_currency='PGK',
    quote_date=date.today(),
    shipment=shipment
)

adapter = PricingServiceV4Adapter(quote_input)
lines = adapter._calculate_standard_lines()

with open('adapter_results.txt', 'w') as f:
    f.write(f"{'Code':<25} | {'Bucket':<25} | {'Description'}\n")
    f.write("-" * 80 + "\n")
    for line in lines:
        f.write(f"{line.service_component_code:<25} | {line.bucket:<25} | {line.service_component_desc}\n")
