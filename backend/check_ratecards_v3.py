import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rate_engine.settings')
django.setup()

from pricing_v3.models import RateCard

count = RateCard.objects.count()
print(f"Total RateCards: {count}")

for rc in RateCard.objects.all():
    print(f"ID: {rc.id}, Name: {rc.name}, Supplier: {rc.supplier}, Valid From: {rc.valid_from}, Valid To: {rc.valid_to}")
