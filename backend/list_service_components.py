import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rate_engine.settings')
django.setup()

from services.models import ServiceComponent

print("Existing ServiceComponents:")
print("-" * 50)
for sc in ServiceComponent.objects.all():
    print(f"{sc.code}: {sc.description}")
