from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, fields
from decimal import Decimal
from datetime import date

from django.core.management.base import BaseCommand
from django.db import transaction

from pricing_v4.models import ImportCOGS
from pricing_v4.services.import_cogs_scope import ImportCOGSScope, classify_import_cogs_scope


@dataclass(frozen=True)
class ImportCOGSPlanSignature:
    product_code: str
    scope: str
    counterparty_type: str
    counterparty_code: str
    currency: str
    rate_per_kg: Decimal | None
    rate_per_shipment: Decimal | None
    min_charge: Decimal | None
    max_charge: Decimal | None
    percent_rate: Decimal | None
    weight_breaks_json: str
    is_additive: bool
    valid_from: date
    valid_until: date
    
    # Location fields depend on scope
    origin_airport: str | None
    destination_airport: str | None

    @classmethod
    def from_row(cls, row: ImportCOGS) -> ImportCOGSPlanSignature:
        scope = classify_import_cogs_scope(row)
        counterparty_type, counterparty_code = _counterparty(row)
        
        return cls(
            product_code=row.product_code.code,
            scope=str(scope),
            counterparty_type=counterparty_type,
            counterparty_code=counterparty_code,
            currency=row.currency,
            rate_per_kg=_normalize_decimal(row.rate_per_kg),
            rate_per_shipment=_normalize_decimal(row.rate_per_shipment),
            min_charge=_normalize_decimal(row.min_charge),
            max_charge=_normalize_decimal(row.max_charge),
            percent_rate=_normalize_decimal(row.percent_rate),
            weight_breaks_json=json.dumps(row.weight_breaks, sort_keys=True) if row.weight_breaks else "null",
            is_additive=row.is_additive,
            valid_from=row.valid_from,
            valid_until=row.valid_until,
            # For ORIGIN scope, we group by origin_airport, destination_airport is allowed to differ
            origin_airport=row.origin_airport if scope == ImportCOGSScope.ORIGIN else None,
            # For DESTINATION scope, we group by destination_airport, origin_airport is allowed to differ
            destination_airport=row.destination_airport if scope == ImportCOGSScope.DESTINATION else None,
        )


def _normalize_decimal(val: Decimal | None) -> Decimal | None:
    if val is None:
        return None
    return val.normalize()


def _counterparty(row: ImportCOGS) -> tuple[str, str]:
    if row.agent_id:
        return ("agent", row.agent.code)
    if row.carrier_id:
        return ("carrier", row.carrier.code)
    return ("none", "")


class Command(BaseCommand):
    help = "Produce a dry-run consolidation plan for ImportCOGS non-lane rates."

    def handle(self, *args, **options):
        # Use a transaction that we will roll back just in case, 
        # though we don't plan to mutate anything.
        with transaction.atomic():
            rows = list(
                ImportCOGS.objects.select_related("product_code", "agent", "carrier")
                .order_by("product_code__code", "origin_airport", "destination_airport", "id")
            )
            
            self.stdout.write("ImportCOGS Consolidation Planner (Dry Run)")
            self.stdout.write("=" * 40)
            
            groups = defaultdict(list)
            for row in rows:
                scope = classify_import_cogs_scope(row)
                if scope not in {ImportCOGSScope.ORIGIN, ImportCOGSScope.DESTINATION}:
                    continue
                
                sig = ImportCOGSPlanSignature.from_row(row)
                groups[sig].append(row)
            
            consolidated_count = 0
            candidate_count = 0
            
            for sig, members in groups.items():
                # Skip if already normalized (no redundant locations in ANY member)
                if all(_is_normalized(m) for m in members):
                    continue

                candidate_count += 1
                if len(members) > 1:
                    consolidated_count += 1
                    self._report_group(sig, members)
                else:
                    self._report_single(sig, members[0])
            
            self.stdout.write("=" * 40)
            self.stdout.write(f"Summary: {candidate_count} consolidation candidates found.")
            self.stdout.write(f"Groups with actual duplicates: {consolidated_count}")
            self.stdout.write("No rows were mutated. Dry run complete.")
            
            # Safety rollback
            transaction.set_rollback(True)

    def _report_group(self, sig: ImportCOGSPlanSignature, members: list[ImportCOGS]):
        self.stdout.write(f"\n[GROUP] {sig.product_code} ({sig.scope})")
        self.stdout.write(f"  Target: {sig.origin_airport or '*' } -> {sig.destination_airport or '*'}")
        self.stdout.write(f"  Members ({len(members)}):")
        for m in members:
            self.stdout.write(f"    - #{m.id} {m.origin_airport}->{m.destination_airport}")
        
        self.stdout.write("  Fields identical:")
        sig_dict = sig.__dict__
        for field in fields(sig):
            if field.name in {"origin_airport", "destination_airport"}:
                continue
            self.stdout.write(f"    - {field.name}: {sig_dict[field.name]}")
        
        self.stdout.write("  Fields differing:")
        if sig.scope == str(ImportCOGSScope.ORIGIN):
            dests = ", ".join(sorted({m.destination_airport for m in members}))
            self.stdout.write(f"    - destination_airport: {dests}")
        else:
            origins = ", ".join(sorted({m.origin_airport for m in members}))
            self.stdout.write(f"    - origin_airport: {origins}")
        
        self.stdout.write("  Safe to consolidate: YES (Exact match on all required fields)")
        self.stdout.write(f"  Action: Replace {len(members)} rows with 1 normalized row.")

    def _report_single(self, sig: ImportCOGSPlanSignature, row: ImportCOGS):
        self.stdout.write(f"\n[SINGLE] {sig.product_code} ({sig.scope})")
        self.stdout.write(f"  Current: {row.origin_airport}->{row.destination_airport} (ID #{row.id})")
        self.stdout.write(f"  Target: {sig.origin_airport or '*' } -> {sig.destination_airport or '*'}")
        self.stdout.write("  Safe to normalize: YES")
        self.stdout.write("  Action: Update 1 row to be normalized (clear redundant location).")


def _is_normalized(row: ImportCOGS) -> bool:
    scope = classify_import_cogs_scope(row)
    if scope == ImportCOGSScope.ORIGIN:
        return row.destination_airport is None or row.destination_airport == ""
    if scope == ImportCOGSScope.DESTINATION:
        return row.origin_airport is None or row.origin_airport == ""
    return True
