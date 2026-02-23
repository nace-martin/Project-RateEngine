import os
import sys
import django
from datetime import date

# Setup Django environment
BACKEND_DIR = os.path.join(os.getcwd(), 'dev', 'Project-RateEngine', 'backend')
if not os.path.exists(BACKEND_DIR):
    BACKEND_DIR = os.path.join(os.getcwd(), 'backend')

sys.path.append(BACKEND_DIR)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rate_engine.settings')
django.setup()

from pricing_v4.models import ProductCode, Surcharge

def check_service_types():
    codes = [1010, 1011, 1031, 1050]
    print("\n--- SERVICE TYPE CHECK ---")
    for cid in codes:
        s = Surcharge.objects.filter(product_code_id=cid).first()
        print(f"ID {cid}: type={s.service_type if s else None}")

if __name__ == "__main__":
    check_service_types()
