import os
import django
from collections import defaultdict
from datetime import date

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rate_engine.settings')
django.setup()

from pricing_v4.models import (
    LocalSellRate, LocalCOGSRate,
    ExportSellRate, ExportCOGS,
    ImportSellRate, ImportCOGS,
    DomesticSellRate, DomesticCOGS
)

def audit_overlaps():
    targets = [
        (LocalSellRate, ['product_code_id', 'location', 'direction', 'payment_term', 'currency']),
        (LocalCOGSRate, ['product_code_id', 'location', 'direction', 'currency', 'agent_id', 'carrier_id']),
        (ExportSellRate, ['product_code_id', 'origin_airport', 'destination_airport', 'currency']),
        (ExportCOGS, ['product_code_id', 'origin_airport', 'destination_airport', 'currency', 'agent_id', 'carrier_id']),
        (ImportSellRate, ['product_code_id', 'origin_airport', 'destination_airport', 'currency']),
        (ImportCOGS, ['product_code_id', 'origin_airport', 'destination_airport', 'currency', 'agent_id', 'carrier_id']),
        (DomesticSellRate, ['product_code_id', 'origin_zone', 'destination_zone', 'currency']),
        (DomesticCOGS, ['product_code_id', 'origin_zone', 'destination_zone', 'currency', 'agent_id', 'carrier_id']),
    ]

    print("=" * 80)
    print("Phase 4D: Freight and COGS Overlap Audit")
    print("=" * 80)

    total_conflicts = 0

    for model, identity_fields in targets:
        print(f"\nAuditing {model.__name__}...")
        all_rows = list(model.objects.all().order_by('id'))
        groups = defaultdict(list)
        
        for row in all_rows:
            key = tuple(getattr(row, f) for f in identity_fields)
            groups[key].append(row)
            
        model_conflicts = 0
        for key, members in groups.items():
            if len(members) < 2:
                continue
                
            for i in range(len(members)):
                for j in range(i + 1, len(members)):
                    m1 = members[i]
                    m2 = members[j]
                    
                    if m1.valid_from <= m2.valid_until and m2.valid_from <= m1.valid_until:
                        # Conflict found
                        print(f"  [!] CONFLICT: {model.__name__} identity {key}")
                        print(f"      ID #{m1.id} ({m1.valid_from} to {m1.valid_until})")
                        print(f"      ID #{m2.id} ({m2.valid_from} to {m2.valid_until})")
                        model_conflicts += 1
                        total_conflicts += 1
        
        if model_conflicts == 0:
            print(f"  OK: No overlaps found in {model.__name__}.")
        else:
            print(f"  SUMMARY: {model_conflicts} overlaps found in {model.__name__}.")

    print("\n" + "=" * 80)
    print(f"TOTAL CONFLICTS FOUND: {total_conflicts}")
    print("=" * 80)

if __name__ == "__main__":
    audit_overlaps()
