
import os
import sys
import django

sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rate_engine.settings')
django.setup()

from quotes.models import Quote, QuoteLine

def run():
    print("--- Checking Stored Quote Lines ---")
    
    # Get the latest quote
    quote = Quote.objects.order_by('-created_at').first()
    if not quote:
        print("No quotes found")
        return
        
    print(f"Quote: {quote.quote_number} ({quote.id})")
    print(f"Status: {quote.status}")
    
    # Get latest version
    version = quote.versions.order_by('-version_number').first()
    if not version:
        print("No versions found")
        return
        
    print(f"Version: {version.version_number}")
    
    # Get lines
    lines = QuoteLine.objects.filter(quote_version=version)
    print(f"\nLines ({lines.count()}):")
    for line in lines:
        code = line.service_component.code if line.service_component else "N/A"
        print(f"  {code}: cost_pgk={line.cost_pgk}, sell_pgk={line.sell_pgk}")

if __name__ == "__main__":
    run()
