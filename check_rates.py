
import os
import sys
import django
from datetime import date

sys.path.append(os.path.join(os.getcwd(), 'backend'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rate_engine.settings')
django.setup()

from pricing_v4.models import ProductCode, ExportSellRate, ExportCOGS

def check_rates():
    codes = [1050, 1060]
    origin = 'POM'
    today = date.today()
    
    print(f"Checking rates for {codes} (Origin: {origin})")
    
    for code_id in codes:
        try:
            pc = ProductCode.objects.get(id=code_id)
            print(f"\nProduct: {pc.code} ({pc.id})")
            
            sell = ExportSellRate.objects.filter(
                product_code=pc,
                origin_airport=origin,
                valid_until__gte=today
            )
            print(f"  Sell Rates Found: {sell.count()}")
            for r in sell:
                 print(f"    -> Dest: {r.destination_airport}, Rate: {r.rate_per_kg or r.rate_per_shipment or r.percent_rate}")
                 
            cogs = ExportCOGS.objects.filter(
                product_code=pc,
                origin_airport=origin,
                valid_until__gte=today
            )
            print(f"  COGS Found: {cogs.count()}")
            
        except ProductCode.DoesNotExist:
            print(f"Product Code {code_id} does not exist!")

if __name__ == "__main__":
    check_rates()
