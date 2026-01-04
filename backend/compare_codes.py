import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rate_engine.settings')
django.setup()

from services.models import ServiceComponent
from pricing_v4.models import ProductCode

print("Codes in ProductCode (IMPORT) vs ServiceComponent")
print("-" * 70)

pcs = ProductCode.objects.filter(domain='IMPORT').values_list('code', flat=True)
scs = ServiceComponent.objects.values_list('code', flat=True)

missing = []
found = []

for code in pcs:
    if code in scs:
        found.append(code)
    else:
        missing.append(code)

print(f"Found match ({len(found)}):")
for f in found:
    print(f"  - {f}")

print(f"\nMissing match ({len(missing)}):")
for m in missing:
    print(f"  - {m}")
