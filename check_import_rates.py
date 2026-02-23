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

from pricing_v4.models import ImportCOGS, ImportSellRate

def check_rates():
    c_count = ImportCOGS.objects.filter(origin_airport='BNE', destination_airport='POM').count()
    s_count = ImportSellRate.objects.filter(origin_airport='BNE', destination_airport='POM').count()
    print(f"Import COGS (BNE->POM): {c_count}")
    print(f"Import Sell (BNE->POM): {s_count}")

if __name__ == "__main__":
    check_rates()
