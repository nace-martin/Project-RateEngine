import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rate_engine.settings')
django.setup()

from pricing_v4.models import ImportCOGS, ExportCOGS, Surcharge, DomesticCOGS
from django.db.models import Count

print("Summary of Rates in DB")
print("=" * 70)

print("\nImportCOGS Lanes:")
import_lanes = ImportCOGS.objects.values('origin_airport', 'destination_airport').annotate(count=Count('id'))
for lane in import_lanes:
    print(f"  {lane['origin_airport']} -> {lane['destination_airport']}: {lane['count']} rates")

print("\nExportCOGS Lanes:")
export_lanes = ExportCOGS.objects.values('origin_airport', 'destination_airport').annotate(count=Count('id'))
for lane in export_lanes:
    print(f"  {lane['origin_airport']} -> {lane['destination_airport']}: {lane['count']} rates")

print("\nSurcharges by Service Type:")
surcharge_types = Surcharge.objects.values('service_type').annotate(count=Count('id'))
for st in surcharge_types:
    print(f"  {st['service_type']}: {st['count']} surcharges")

print("\nDomesticCOGS Lanes:")
dom_lanes = DomesticCOGS.objects.values('origin_zone', 'destination_zone').annotate(count=Count('id'))
for lane in dom_lanes:
    print(f"  {lane['origin_zone']} -> {lane['destination_zone']}: {lane['count']} rates")
