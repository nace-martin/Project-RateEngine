import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rate_engine.settings')
django.setup()

from pricing_v4.models import ImportCOGS, ExportCOGS, DomesticCOGS, Surcharge, ImportSellRate, ExportSellRate, DomesticSellRate
from datetime import date

new_expiry = date(2026, 12, 31)
today = date.today()

print(f"Updating all expired rates to be valid until {new_expiry}...")

# Update COGS
updated = ImportCOGS.objects.filter(valid_until__lt=today).update(valid_until=new_expiry)
print(f"Updated {updated} ImportCOGS")

updated = ExportCOGS.objects.filter(valid_until__lt=today).update(valid_until=new_expiry)
print(f"Updated {updated} ExportCOGS")

updated = DomesticCOGS.objects.filter(valid_until__lt=today).update(valid_until=new_expiry)
print(f"Updated {updated} DomesticCOGS")

# Update SELL
updated = ImportSellRate.objects.filter(valid_until__lt=today).update(valid_until=new_expiry)
print(f"Updated {updated} ImportSellRate")

updated = ExportSellRate.objects.filter(valid_until__lt=today).update(valid_until=new_expiry)
print(f"Updated {updated} ExportSellRate")

updated = DomesticSellRate.objects.filter(valid_until__lt=today).update(valid_until=new_expiry)
print(f"Updated {updated} DomesticSellRate")

# Update Surcharges
updated = Surcharge.objects.filter(valid_until__lt=today).update(valid_until=new_expiry)
print(f"Updated {updated} Surcharges")

print("Done! All rates are now valid for 2026.")
