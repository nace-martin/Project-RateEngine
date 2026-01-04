import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rate_engine.settings')
django.setup()

from services.models import ServiceComponent

# Fix ServiceComponent legs
to_fix = [
    'IMP-AGENCY-ORIGIN',
    'IMP-AWB-ORIGIN',
    'IMP-CTO-ORIGIN',
    'IMP-DOC-ORIGIN',
    'IMP-FSC-PICKUP',
    'IMP-PICKUP',
    'IMP-SCREEN-ORIGIN'
]

updated_count = ServiceComponent.objects.filter(code__in=to_fix).update(leg='ORIGIN')
print(f"Updated {updated_count} ServiceComponents to leg='ORIGIN'")

# Also check for any others that might be wrong
others = ServiceComponent.objects.filter(code__contains='ORIGIN').exclude(leg='ORIGIN')
for sc in others:
    print(f"STILL WRONG: {sc.code} has leg {sc.leg}")

pickup_others = ServiceComponent.objects.filter(code__contains='PICKUP').exclude(leg='ORIGIN')
for sc in pickup_others:
     print(f"STILL WRONG: {sc.code} has leg {sc.leg}")
