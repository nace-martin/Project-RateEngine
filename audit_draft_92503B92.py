import os
import sys
import django
from decimal import Decimal

# Setup Django environment
BACKEND_DIR = os.path.join(os.getcwd(), 'dev', 'Project-RateEngine', 'backend')
if not os.path.exists(BACKEND_DIR):
    BACKEND_DIR = os.path.join(os.getcwd(), 'backend')

sys.path.append(BACKEND_DIR)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rate_engine.settings')
django.setup()

from quotes.models import Quote
from quotes.serializers import V3QuoteTotalSerializer, V3QuoteLineSerializer

def audit_quote(quote_number):
    try:
        q = Quote.objects.get(quote_number=quote_number)
        v = q.versions.order_by('-version_number').first()
        t = v.totals
        
        print(f"--- DATABASE AUDIT: {quote_number} ---")
        print("Currency: " + str(q.output_currency))
        print("Total Sell FCY: " + str(t.total_sell_fcy))
        print("Total Sell FCY Incl GST: " + str(t.total_sell_fcy_incl_gst))
        
        # Check Serializer Output (What the frontend actually sees)
        total_ser = V3QuoteTotalSerializer(t).data
        print("\n--- SERIALIZER TOTALS ---")
        print("currency: " + str(total_ser.get('currency')))
        print("total_sell_ex_gst: " + str(total_ser.get('total_sell_ex_gst')))
        print("gst_amount: " + str(total_ser.get('gst_amount')))
        print("total_quote_amount: " + str(total_ser.get('total_quote_amount')))
        
        print("\n--- SERIALIZER LINES ---")
        lines = v.lines.all()
        for l in lines:
            l_ser = V3QuoteLineSerializer(l).data
            print(f"{l_ser.get('component', 'MANUAL'):<20} | Sell: {str(l_ser.get('sell_fcy')):>8} | GST: {str(l_ser.get('gst_amount')):>8} | Total: {str(l_ser.get('sell_fcy_incl_gst')):>8}")

    except Exception as e:
        print("Error: " + str(e))
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    audit_quote('DRAFT-92503B92')
