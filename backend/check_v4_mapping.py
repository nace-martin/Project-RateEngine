import os
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rate_engine.settings')
django.setup()

from pricing_v4.models import ProductCode
from services.models import ServiceComponent

def check_mapping():
    print("=" * 60)
    print("Checking ProductCode -> ServiceComponent Mapping")
    print("=" * 60)
    
    product_codes = ProductCode.objects.all()
    missing_count = 0
    found_count = 0
    
    for pc in product_codes:
        if ServiceComponent.objects.filter(code=pc.code).exists():
            found_count += 1
        else:
            missing_count += 1
            if missing_count <= 10:
                print(f"Missing ServiceComponent for: {pc.code}")
    
    print("-" * 60)
    print(f"Total ProductCodes: {product_codes.count()}")
    print(f"Mapped: {found_count}")
    print(f"Missing: {missing_count}")
    
    if missing_count > 0:
        print("\nACTION REQUIRED: Need to sync ServiceComponents.")

if __name__ == '__main__':
    check_mapping()
