from decimal import Decimal
from datetime import date
import uuid
from core.dataclasses import QuoteInput, ShipmentDetails, LocationRef, Piece
from pricing_v4.adapter import PricingServiceV4Adapter

# Setup basic shipment details matching the quote
shipment = ShipmentDetails(
    mode='AIR',
    shipment_type='IMPORT',
    service_scope='D2D',
    origin_location=LocationRef(id=uuid.uuid4(), code='BNE', country_code='AU', name='Brisbane'),
    destination_location=LocationRef(id=uuid.uuid4(), code='POM', country_code='PG', name='Port Moresby'),
    commodity_code='GCR',
    incoterm='EXW',
    payment_term='COLLECT',
    is_dangerous_goods=False,
    pieces=[Piece(pieces=1, length_cm=Decimal('100'), width_cm=Decimal('100'), height_cm=Decimal('100'), gross_weight_kg=Decimal('100.0'))]
)

qi = QuoteInput(
    customer_id=uuid.uuid4(),
    contact_id=uuid.uuid4(),
    quote_date=date.today(),
    output_currency='PGK',
    shipment=shipment
)

ad = PricingServiceV4Adapter(qi)
res = ad.calculate_charges()

print(f"has_missing: {res.totals.has_missing_rates}")
print(f"notes: {res.totals.notes}")
origin_lines = [l for l in res.lines if l.bucket == 'origin_charges']
print(f"Origin Lines Count: {len(origin_lines)}")
for l in origin_lines:
    print(f" - {l.service_component_code}: is_rate_missing={l.is_rate_missing}, sell={l.sell_pgk}")
