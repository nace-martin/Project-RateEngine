from __future__ import annotations

import os
from collections import defaultdict
from django.core.management.base import BaseCommand
from django.db.models import QuerySet

from pricing_v4.models import (
    LocalSellRate, LocalCOGSRate,
    ExportSellRate, ExportCOGS,
    ImportSellRate, ImportCOGS,
    DomesticSellRate, DomesticCOGS,
    Surcharge
)

class Command(BaseCommand):
    help = 'Audit all V4 pricing tables for commercial identity overlaps'

    def handle(self, *args, **options):
        targets = [
            (LocalSellRate, ['product_code_id', 'location', 'direction', 'payment_term', 'currency']),
            (LocalCOGSRate, ['product_code_id', 'location', 'direction', 'currency', 'agent_id', 'carrier_id']),
            (ExportSellRate, ['product_code_id', 'origin_airport', 'destination_airport', 'currency']),
            (ExportCOGS, ['product_code_id', 'origin_airport', 'destination_airport', 'currency', 'agent_id', 'carrier_id']),
            (ImportSellRate, ['product_code_id', 'origin_airport', 'destination_airport', 'currency']),
            (ImportCOGS, ['product_code_id', 'origin_airport', 'destination_airport', 'currency', 'agent_id', 'carrier_id']),
            (DomesticSellRate, ['product_code_id', 'origin_zone', 'destination_zone', 'currency']),
            (DomesticCOGS, ['product_code_id', 'origin_zone', 'destination_zone', 'currency', 'agent_id', 'carrier_id']),
            (Surcharge, ['product_code_id', 'service_type', 'rate_side', 'currency', 'origin_filter', 'destination_filter']),
        ]

        self.stdout.write(self.style.MIGRATE_HEADING("Phase 4D: Pricing Overlap Audit"))

        total_conflicts = 0

        for model, identity_fields in targets:
            self.stdout.write(f"\nAuditing {model.__name__}...")
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
                            self.stdout.write(self.style.WARNING(f"  [!] CONFLICT: {model.__name__} identity {key}"))
                            self.stdout.write(f"      ID #{m1.id} ({m1.valid_from} to {m1.valid_until})")
                            self.stdout.write(f"      ID #{m2.id} ({m2.valid_from} to {m2.valid_until})")
                            model_conflicts += 1
                            total_conflicts += 1
            
            if model_conflicts == 0:
                self.stdout.write(self.style.SUCCESS(f"  OK: No overlaps found in {model.__name__}."))
            else:
                self.stdout.write(self.style.ERROR(f"  SUMMARY: {model_conflicts} overlaps found in {model.__name__}."))

        self.stdout.write("\n" + "=" * 80)
        if total_conflicts == 0:
            self.stdout.write(self.style.SUCCESS(f"TOTAL CONFLICTS FOUND: {total_conflicts}"))
        else:
            self.stdout.write(self.style.ERROR(f"TOTAL CONFLICTS FOUND: {total_conflicts}"))
        self.stdout.write("=" * 80)
