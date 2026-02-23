import os
import sys
import django
import json
from decimal import Decimal

# Setup Django environment
BACKEND_DIR = os.path.join(os.getcwd(), 'dev', 'Project-RateEngine', 'backend')
if not os.path.exists(BACKEND_DIR):
    BACKEND_DIR = os.path.join(os.getcwd(), 'backend')

sys.path.append(BACKEND_DIR)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rate_engine.settings')
django.setup()

from quotes.models import Quote
from quotes.serializers import V3QuoteTotalSerializer

def decimal_default(obj):
    if isinstance(obj, Decimal):
        return str(obj)
    raise TypeError

def audit_quote_full(quote_number):
    try:
        q = Quote.objects.get(quote_number=quote_number)
        v = q.versions.order_by('-version_number').first()
        t = v.totals
        
        print("--- FULL TOTALS AUDIT: " + quote_number + " ---")
        
        # Check Serializer Output
        total_ser = V3QuoteTotalSerializer(t).data
        # Manually convert Decimal values to string for printing
        clean_data = {k: (str(v) if isinstance(v, Decimal) else v) for k, v in total_ser.items()}
        print(json.dumps(clean_data, indent=2))

    except Exception as e:
        print("Error: " + str(e))

if __name__ == "__main__":
    audit_quote_full('DRAFT-92503B92')
