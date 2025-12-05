import os
import django
from decimal import Decimal

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rate_engine.settings')
django.setup()

from quotes.schemas import V3QuoteTotalSchema

# Test schema serialization
totals_data = {
    'total_cost_pgk': Decimal('915.20'),
    'total_sell_pgk': Decimal('915.20'),
    'total_sell_pgk_incl_gst': Decimal('915.20'),
    'total_sell_fcy': Decimal('915.20'),
    'total_sell_fcy_incl_gst': Decimal('915.20'),
    'total_sell_fcy_currency': 'AUD',
    'has_missing_rates': False,
    'notes': None
}

schema = V3QuoteTotalSchema(**totals_data)
print("model_dump():")
print(schema.model_dump())
print()
print("model_dump(mode='json'):")
print(schema.model_dump(mode='json'))
print()
print("Type of total_sell_fcy in model_dump():", type(schema.model_dump()['total_sell_fcy']))
print("Type of total_sell_fcy in model_dump(mode='json'):", type(schema.model_dump(mode='json')['total_sell_fcy']))
