import os
import django
from django.conf import settings
from django.utils import timezone

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rate_engine.settings')
django.setup()

from quotes.models import Quote, SpotPricingEnvelopeDB

def inspect_specific_stale_items():
    print(f"Current Server Time: {timezone.now()}")

    # Check QT-40
    print("\n--- Inspecting QT-40 ---")
    try:
        q = Quote.objects.get(quote_number='QT-40')
        print(f"ID: {q.id}")
        print(f"Status: '{q.status}'") 
        print(f"Created At: {q.created_at}")
        print(f"Is Draft? {q.status == 'DRAFT'}")
    except Quote.DoesNotExist:
        print("QT-40 not found.")

    # Check SQ-1296AD (substring)
    print("\n--- Inspecting SQ-1296AD ---")
    try:
        qs = SpotPricingEnvelopeDB.objects.filter(id__istartswith='1296ad')
        for spe in qs:
            print(f"ID: {spe.id}")
            print(f"Status: '{spe.status}'")
            print(f"Created At: {spe.created_at}")
            print(f"Is Draft? {spe.status == 'draft'}")
    except Exception as e:
        print(f"Error searching SPE: {e}")

    # Check SQ-D86D4E (substring - from Dec 31)
    print("\n--- Inspecting SQ-D86D4E ---")
    try:
        qs = SpotPricingEnvelopeDB.objects.filter(id__istartswith='d86d4e')
        for spe in qs:
            print(f"ID: {spe.id}")
            print(f"Status: '{spe.status}'")
            print(f"Created At: {spe.created_at}")
            print(f"Is Draft? {spe.status == 'draft'}")
    except Exception as e:
        print(f"Error searching SPE: {e}")

if __name__ == "__main__":
    inspect_specific_stale_items()
