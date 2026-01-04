import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rate_engine.settings')
django.setup()

from pricing_v4.adapter import PricingServiceV4Adapter
from pricing_v2.dataclasses_v3 import QuoteInput, ShipmentDetails, Piece, LocationRef
from decimal import Decimal
from parties.models import Company, Contact
from core.models import Location
import uuid

customer = Company.objects.first()
contact = customer.contacts.first() if customer else None

origin_loc = Location.objects.get(code='BNE')
dest_loc = Location.objects.get(code='POM')

# Setup input
origin = LocationRef(id=origin_loc.id, code='BNE', name='Brisbane', country_code='AU', currency_code='AUD')
destination = LocationRef(id=dest_loc.id, code='POM', name='Port Moresby', country_code='PG', currency_code='PGK')

shipment = ShipmentDetails(
    mode='AIR',
    shipment_type='IMPORT',
    incoterm='EXW',
    payment_term='COLLECT',
    is_dangerous_goods=False,
    pieces=[Piece(pieces=1, length_cm=Decimal('50'), width_cm=Decimal('50'), height_cm=Decimal('50'), gross_weight_kg=Decimal('100'))],
    service_scope='D2D',
    direction='IMPORT',
    origin_location=origin,
    destination_location=destination
)

quote_input = QuoteInput(
    customer_id=customer.id,
    contact_id=contact.id if contact else customer.id,
    output_currency='PGK',
    shipment=shipment
)

adapter = PricingServiceV4Adapter(quote_input)
result = adapter.calculate_charges()

print(f"{'Code':<25} | {'Leg':<15} | {'Bucket':<20} | {'Sell PGK'}")
print("-" * 75)
for line in result.lines:
    print(f"{line.service_component_code:<25} | {line.leg:<15} | {line.bucket:<20} | {line.sell_pgk}")
