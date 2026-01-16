import os
import django
from django.conf import settings

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rate_engine.settings')
django.setup()

from quotes.models import Quote, SpotPricingEnvelopeDB

def inspect_stale_data():
    print("--- Inspecting QT-31 ---")
    try:
        q = Quote.objects.get(quote_number='QT-31')
        print(f"ID: {q.id}")
        print(f"Status: '{q.status}' (Type: {type(q.status)})")
        print(f"Created At: {q.created_at}")
    except Quote.DoesNotExist:
        print("QT-31 not found.")

    print("\n--- Inspecting SQ-7C3A4A ---")
    # SQ-7C3A4A is a substring of the UUID. 
    # The frontend code: `const shortId = d.id.substring(0, 6).toUpperCase();`
    # So we need to find an ID starting with '7c3a4a' (case insensitive)
    try:
        qs = SpotPricingEnvelopeDB.objects.filter(id__istartswith='7c3a4a')
        for spe in qs:
            print(f"ID: {spe.id}")
            print(f"Status: '{spe.status}' (Type: {type(spe.status)})")
            print(f"Created At: {spe.created_at}")
    except Exception as e:
        print(f"Error searching SPE: {e}")

if __name__ == "__main__":
    inspect_stale_data()
