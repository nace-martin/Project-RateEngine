import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rate_engine.settings')
django.setup()

from quotes.models import Quote
import json
from decimal import Decimal

# Helper for JSON serialization of Decimals
class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return str(obj)
        return super(DecimalEncoder, self).default(obj)

# Fetch the specific quote if possible, or just the latest one
quote = Quote.objects.get(id='34fe1c05-51a6-493c-b56f-bc51d27e35f7')

print(f"Quote {quote.id}")
print(f"Computed Totals: {quote.computed_totals}")
print("-" * 50)

charges = quote.computed_charges_json
if isinstance(charges, str):
    charges = json.loads(charges)

lines = charges.get('lines', [])
print(f"Total Lines: {len(lines)}")
print("-" * 50)

print(f"{'Code':<25} | {'Leg':<15} | {'Bucket':<20} | {'Sell PGK'}")
for line in lines:
    print(f"{line.get('service_component_code', ''):<25} | {line.get('leg', ''):<15} | {line.get('bucket', ''):<20} | {line.get('sell_pgk', '0')}")
