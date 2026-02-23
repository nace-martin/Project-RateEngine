import os
import sys
import django

# Setup Django environment
BACKEND_DIR = os.path.join(os.getcwd(), 'dev', 'Project-RateEngine', 'backend')
if not os.path.exists(BACKEND_DIR):
    BACKEND_DIR = os.path.join(os.getcwd(), 'backend')

sys.path.append(BACKEND_DIR)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rate_engine.settings')
django.setup()

from quotes.models import Quote

def inspect_quote():
    try:
        q = Quote.objects.get(quote_number='DRAFT-F756DFA0')
        print(f"Quote: {q.quote_number} | Currency: {q.output_currency} | Status: {q.status}")
        
        # Get latest version
        v = q.versions.order_by('-version_number').first()
        if not v:
            print("No versions found.")
            return

        t = v.totals
        print(f"\n--- TOTALS (DB) ---")
        print(f"Total Sell PGK: {t.total_sell_pgk}")
        print(f"Total Sell FCY: {t.total_sell_fcy} ({t.total_sell_fcy_currency})")
        print(f"Total Sell FCY Inc GST: {t.total_sell_fcy_incl_gst}")
        print(f"Has Missing Rates: {t.has_missing_rates}")
        
        print(f"\n--- LINES ---")
        for l in v.lines.all().select_related('service_component'):
            code = l.service_component.code if l.service_component else "MANUAL"
            print(f"{code:<20} | Sell FCY: {l.sell_fcy:>10.2f} | GST: {l.gst_amount:>6.2f} | Missing: {l.is_rate_missing} | Info: {l.is_informational}")

    except Quote.DoesNotExist:
        print("Quote DRAFT-F756DFA0 not found.")

if __name__ == "__main__":
    inspect_quote()
