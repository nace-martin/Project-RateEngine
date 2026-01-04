import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rate_engine.settings')
django.setup()

from pricing_v4.models import ImportCOGS, ProductCode
from datetime import date

today = date.today()
origin = 'BNE'
dest = 'POM'

print(f"Today: {today}")
print(f"Checking ImportCOGS for {origin} -> {dest}")
print("-" * 50)

cogs = ImportCOGS.objects.filter(
    origin_airport=origin,
    destination_airport=dest
).select_related('product_code')

for c in cogs:
    status = "ACTIVE" if c.valid_from <= today <= c.valid_until else "EXPIRED"
    print(f"{c.product_code.code} ({c.product_code.category}): {status} (Valid: {c.valid_from} to {c.valid_until})")
