import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rate_engine.settings')
django.setup()

from pricing_v4.models import ImportSellRate
from datetime import date

today = date.today()
origin = 'BNE'
dest = 'POM'

print(f"ImportSellRate for {origin} -> {dest}")
print("-" * 50)

rates = ImportSellRate.objects.filter(
    origin_airport=origin,
    destination_airport=dest
).select_related('product_code')

for r in rates:
    print(f"{r.product_code.code} | Category: {r.product_code.category}")
