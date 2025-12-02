import os
import django
import sys

# Add project root to path
sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rate_engine.settings')
django.setup()

from quotes.models import Quote
from pricing_v2.pricing_service_v3 import PricingServiceV3
from pricing_v2.dataclasses_v3 import QuoteInput, ShipmentDetails, Piece, LocationRef
import uuid

# Get the quote
q = Quote.objects.get(id='5316c541-0d8c-4334-bf63-b6e8dbe8bc30')

# Reconstruct input (simplified)
pieces = [Piece(pieces=10, length_cm=50, width_cm=50, height_cm=50, gross_weight_kg=100)]
origin = LocationRef(id=q.origin_location.id, code=q.origin_location.code, name=q.origin_location.name, country_code='AU', currency_code='AUD')
dest = LocationRef(id=q.destination_location.id, code=q.destination_location.code, name=q.destination_location.name, country_code='PGK', currency_code='PGK')

shipment = ShipmentDetails(
    mode='AIR',
    shipment_type='IMPORT',
    incoterm='EXW',
    payment_term='COLLECT',
    is_dangerous_goods=False,
    pieces=pieces,
    service_scope='D2D',
    direction='IMPORT',
    origin_location=origin,
    destination_location=dest
)

inp = QuoteInput(
    customer_id=q.customer.id,
    contact_id=uuid.uuid4(), # fake
    output_currency='PGK',
    shipment=shipment
)

service = PricingServiceV3(inp)
charges = service.calculate_charges()

print(f"\n--- Policy Check ---")
policy = service.get_policy()
print(f"Policy: {policy.name}")
print(f"Margin: {policy.margin_pct}")
print(f"CAF Import: {policy.caf_import_pct}")
print(f"CAF Export: {policy.caf_export_pct}")

print(f"\n{'Component':<15} {'Leg':<10} {'Cost Src':<20} {'Cost PGK':<10} {'Sell PGK':<10} {'Margin'}")
print("-" * 80)

for line in charges.lines:
    margin = ((line.sell_pgk - line.cost_pgk) / line.cost_pgk * 100) if line.cost_pgk > 0 else 0
    print(f"{line.service_component_code:<15} {line.leg:<10} {line.cost_source[:20]:<20} {line.cost_pgk:<10.2f} {line.sell_pgk:<10.2f} {margin:.1f}%")
