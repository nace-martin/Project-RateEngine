import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rate_engine.settings')
django.setup()

from services.models import ServiceComponent

sc = ServiceComponent.objects.get(code='IMP-PICKUP')
print(f"IMP-PICKUP leg: {sc.leg}")

sc2 = ServiceComponent.objects.get(code='IMP-DOC-ORIGIN')
print(f"IMP-DOC-ORIGIN leg: {sc2.leg}")
