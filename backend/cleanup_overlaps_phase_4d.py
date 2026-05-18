import os
import django
from collections import defaultdict
from datetime import date

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rate_engine.settings')
django.setup()

from pricing_v4.models import DomesticSellRate

def cleanup_domestic_sell_overlaps():
    identity_fields = ['product_code_id', 'origin_zone', 'destination_zone', 'currency']
    all_rows = list(DomesticSellRate.objects.all().order_by('id'))
    groups = defaultdict(list)
    
    for row in all_rows:
        key = tuple(getattr(row, f) for f in identity_fields)
        groups[key].append(row)
        
    deleted_ids = []
    for key, members in groups.items():
        if len(members) < 2:
            continue
            
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                m1 = members[i]
                m2 = members[j]
                
                # Check for overlap
                if m1.valid_from <= m2.valid_until and m2.valid_from <= m1.valid_until:
                    # Check if they are identical commercially
                    fields_to_compare = ['rate_per_kg', 'rate_per_shipment', 'min_charge', 'max_charge', 'percent_rate', 'weight_breaks', 'is_additive']
                    identical = True
                    for field in fields_to_compare:
                        if getattr(m1, field) != getattr(m2, field):
                            identical = False
                            break
                    
                    if identical:
                        # If identical, delete the one with a shorter range or later ID
                        # In our case, ID #51 is a sub-range of ID #1 (2026 subset of 2025-2026)
                        if m1.valid_from <= m2.valid_from and m1.valid_until >= m2.valid_until:
                            # m1 fully shadows m2
                            if m2.id not in deleted_ids:
                                deleted_ids.append(m2.id)
                        elif m2.valid_from <= m1.valid_from and m2.valid_until >= m1.valid_until:
                            # m2 fully shadows m1
                            if m1.id not in deleted_ids:
                                deleted_ids.append(m1.id)
    
    if deleted_ids:
        print(f"Deleting {len(deleted_ids)} redundant DomesticSellRate rows: {deleted_ids}")
        DomesticSellRate.objects.filter(id__in=deleted_ids).delete()
    else:
        print("No redundant DomesticSellRate rows found to delete.")

if __name__ == "__main__":
    cleanup_domestic_sell_overlaps()
