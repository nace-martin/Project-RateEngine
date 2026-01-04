import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rate_engine.settings')
django.setup()

from pricing_v4.models import ImportCOGS, Surcharge, ProductCode
from datetime import date

today = date.today()
origin = 'BNE'
dest = 'POM'

print(f"Current Date: {today}")
print(f"Checking rates for Import {origin} -> {dest}")
print("=" * 70)

# 1. Check ImportCOGS
print("\n--- All ImportCOGS for BNE -> POM ---")
cogs = ImportCOGS.objects.filter(
    origin_airport=origin,
    destination_airport=dest
).select_related('product_code')

if not cogs.exists():
    print("No ImportCOGS found for this lane.")
else:
    for rate in cogs:
        print(f"[{rate.product_code.category}] {rate.product_code.code}: {rate.product_code.description}")
        print(f"  Valid: {rate.valid_from} to {rate.valid_until}")
        is_active = (rate.valid_from <= today <= rate.valid_until) if rate.valid_from and rate.valid_until else "N/A"
        print(f"  Active Today: {is_active}")

# 2. Check Surcharges (Import Origin) at BNE
print("\n--- All IMPORT_ORIGIN surcharges ---")
surcharges = Surcharge.objects.filter(
    service_type='IMPORT_ORIGIN'
).select_related('product_code')

if not surcharges.exists():
    print(f"No IMPORT_ORIGIN surcharges found.")
else:
    for s in surcharges:
        print(f"[{s.product_code.category}] {s.product_code.code}: {s.product_code.description}")
        print(f"  Origin Filter: {s.origin_filter}")
        print(f"  Valid: {s.valid_from} to {s.valid_until}")
        is_active = (s.valid_from <= today <= s.valid_until) if s.valid_from and s.valid_until else "N/A"
        print(f"  Active Today: {is_active}")

# 3. Check Surcharges (IMPORT_DEST) at POM
print("\n--- All IMPORT_DEST surcharges ---")
dest_surcharges = Surcharge.objects.filter(
    service_type='IMPORT_DEST'
).select_related('product_code')

if not dest_surcharges.exists():
    print(f"No IMPORT_DEST surcharges found.")
else:
    for s in dest_surcharges:
        print(f"[{s.product_code.category}] {s.product_code.code}: {s.product_code.description}")
        print(f"  Dest Filter: {s.destination_filter}")
        print(f"  Valid: {s.valid_from} to {s.valid_until}")
        is_active = (s.valid_from <= today <= s.valid_until) if s.valid_from and s.valid_until else "N/A"
        print(f"  Active Today: {is_active}")
