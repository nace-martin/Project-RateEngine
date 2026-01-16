import os
import django
from django.conf import settings

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rate_engine.settings')
django.setup()

from quotes.models import Quote, SpotPricingEnvelopeDB

def inspect_all():
    print(f"Total Quotes: {Quote.objects.count()}")
    print("--- First 5 Quotes ---")
    for q in Quote.objects.all().order_by('-created_at')[:5]:
        print(f"Num: {q.quote_number}, Status: {q.status}, Created: {q.created_at}")

    print(f"\nTotal SPEs: {SpotPricingEnvelopeDB.objects.count()}")
    print("--- First 5 SPEs ---")
    for spe in SpotPricingEnvelopeDB.objects.all().order_by('-created_at')[:5]:
        print(f"ID: {spe.id}, Status: {spe.status}, Created: {spe.created_at}")

if __name__ == "__main__":
    inspect_all()
