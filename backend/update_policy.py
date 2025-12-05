import os
import django
from decimal import Decimal
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "rate_engine.settings")
django.setup()

from core.models import Policy

def update_policy():
    try:
        policy = Policy.objects.latest('effective_from')
        print(f"Current Policy: {policy.name}")
        print(f"  Import CAF: {policy.caf_import_pct}")
        print(f"  Export CAF: {policy.caf_export_pct}")
        print(f"  Margin: {policy.margin_pct}")
        
        # Update to defaults
        policy.caf_import_pct = Decimal("0.05")
        policy.caf_export_pct = Decimal("0.10")
        policy.margin_pct = Decimal("0.15") # Default is 15%
        policy.save()
        
        print("Updated Policy to defaults:")
        print(f"  Import CAF: {policy.caf_import_pct}")
        print(f"  Export CAF: {policy.caf_export_pct}")
        print(f"  Margin: {policy.margin_pct}")
        
    except Policy.DoesNotExist:
        print("No active policy found.")

if __name__ == "__main__":
    update_policy()
