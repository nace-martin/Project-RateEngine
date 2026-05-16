from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

from django.core.management.base import BaseCommand

from pricing_v4.models import ImportCOGS
from pricing_v4.services.import_cogs_scope import ImportCOGSScope, classify_import_cogs_scope
from pricing_v4.services.rate_scope_transition import computed_transition_scope, explicit_scope, scope_mismatch


@dataclass(frozen=True)
class RowSignature:
    product_code: str
    counterparty_type: str
    counterparty_code: str
    currency: str
    amount_signature: tuple[str, ...]
    origin_airport: str
    origin_country: str


@dataclass(frozen=True)
class CoverageSignature:
    product_code: str
    counterparty_type: str
    counterparty_code: str
    currency: str
    amount_signature: tuple[str, ...]


class Command(BaseCommand):
    help = "Dry-run audit of ImportCOGS rows for future scoped normalization."

    def handle(self, *args, **options):
        rows = list(
            ImportCOGS.objects.select_related("product_code", "agent", "carrier")
            .order_by("product_code__code", "origin_airport", "destination_airport", "id")
        )

        duplicate_groups = self._duplicate_non_lane_groups(rows)
        unknown_rows = [row for row in rows if classify_import_cogs_scope(row) == ImportCOGSScope.UNKNOWN]
        mismatch_rows = [row for row in rows if scope_mismatch(row)]
        orphan_groups = self._possible_orphan_groups(rows)
        consolidation_ready_rows = [
            row for row in rows
            if classify_import_cogs_scope(row) not in {ImportCOGSScope.LANE, ImportCOGSScope.UNKNOWN}
            and explicit_scope(row) == computed_transition_scope(row)
            and not _is_already_normalized(row)
        ]

        self.stdout.write("ImportCOGS scope audit (dry run)")
        self.stdout.write("No rows were changed.")
        self.stdout.write("")
        self._write_rows("Scope mismatches:", mismatch_rows)
        self.stdout.write("")
        self._write_duplicate_groups(duplicate_groups)
        self.stdout.write("")
        self._write_unknown_rows(unknown_rows)
        self.stdout.write("")
        self._write_orphan_groups(orphan_groups)
        self.stdout.write("")
        self._write_rows("Rows ready for future consolidation review:", consolidation_ready_rows)
        self.stdout.write("")
        self.stdout.write("Phase 3 direction:")
        self.stdout.write("- Use explicit scope (LANE, ORIGIN, DESTINATION) for all rows.")
        self.stdout.write("- ORIGIN rows must have destination_airport = NULL.")
        self.stdout.write("- DESTINATION rows must have origin_airport = NULL.")
        self.stdout.write("- LANE rows require both origin_airport and destination_airport.")
        self.stdout.write("- Use the consolidation planner to identify and merge duplicate commercial signatures.")
        self.stdout.write("- Preserve deterministic selector ordering and current quote output.")

    def _duplicate_non_lane_groups(self, rows: Iterable[ImportCOGS]):
        groups = defaultdict(list)
        for row in rows:
            scope = classify_import_cogs_scope(row)
            if scope in {ImportCOGSScope.LANE, ImportCOGSScope.UNKNOWN}:
                continue
            groups[_row_signature(row)].append(row)
        return {
            signature: members
            for signature, members in groups.items()
            if len({row.destination_airport for row in members}) > 1
        }

    def _possible_orphan_groups(self, rows: Iterable[ImportCOGS]):
        coverage = defaultdict(lambda: defaultdict(set))
        for row in rows:
            scope = classify_import_cogs_scope(row)
            if scope in {ImportCOGSScope.LANE, ImportCOGSScope.UNKNOWN}:
                continue
            signature = _coverage_signature(row)
            coverage[signature][row.origin_airport].add(row.destination_airport)

        orphan_groups = []
        for signature, by_origin in coverage.items():
            if len(by_origin) < 2:
                continue
            expected_destinations = set().union(*by_origin.values())
            for origin, destinations in by_origin.items():
                missing = expected_destinations - destinations
                if missing:
                    orphan_groups.append((signature, origin, sorted(missing)))
        return orphan_groups

    def _write_duplicate_groups(self, duplicate_groups):
        self.stdout.write("Likely duplicate non-lane rows:")
        if not duplicate_groups:
            self.stdout.write("- none")
            return
        for signature, members in duplicate_groups.items():
            destinations = ", ".join(sorted({str(row.destination_airport) for row in members}))
            ids = ", ".join(str(row.id) for row in members)
            self.stdout.write(
                "- "
                f"{signature.product_code} {signature.counterparty_type}:{signature.counterparty_code} "
                f"{signature.currency} amount={signature.amount_signature} "
                f"origin={signature.origin_airport} origin_country={signature.origin_country} "
                f"destinations={destinations} row_ids={ids} "
                f"computed_scope={computed_transition_scope(members[0])}"
            )

    def _write_unknown_rows(self, unknown_rows):
        self.stdout.write("UNKNOWN scope rows:")
        if not unknown_rows:
            self.stdout.write("- none")
            return
        for row in unknown_rows:
            counterparty_type, counterparty_code, origin_country = _counterparty(row)
            self.stdout.write(
                "- "
                f"#{row.id} {row.product_code.code} {row.origin_airport}->{row.destination_airport} "
                f"explicit_scope={explicit_scope(row)} computed_scope={computed_transition_scope(row)} "
                f"{counterparty_type}:{counterparty_code} origin_country={origin_country} "
                f"currency={row.currency} amount={_amount_signature(row)}"
            )

    def _write_rows(self, title, rows):
        self.stdout.write(title)
        if not rows:
            self.stdout.write("- none")
            return
        for row in rows:
            counterparty_type, counterparty_code, origin_country = _counterparty(row)
            self.stdout.write(
                "- "
                f"#{row.id} {row.product_code.code} {row.origin_airport}->{row.destination_airport} "
                f"explicit_scope={explicit_scope(row)} computed_scope={computed_transition_scope(row)} "
                f"{counterparty_type}:{counterparty_code} origin_country={origin_country} "
                f"currency={row.currency} amount={_amount_signature(row)}"
            )

    def _write_orphan_groups(self, orphan_groups):
        self.stdout.write("Possible orphan/missing companion charges:")
        if not orphan_groups:
            self.stdout.write("- none safely inferable")
            return
        for signature, origin, missing_destinations in orphan_groups:
            self.stdout.write(
                "- "
                f"{signature.product_code} {signature.counterparty_type}:{signature.counterparty_code} "
                f"{signature.currency} amount={signature.amount_signature} origin={origin} "
                f"missing_destinations={', '.join(missing_destinations)}"
            )


def _is_already_normalized(row: ImportCOGS) -> bool:
    scope = classify_import_cogs_scope(row)
    if scope == ImportCOGSScope.ORIGIN:
        return row.destination_airport is None or row.destination_airport == ""
    if scope == ImportCOGSScope.DESTINATION:
        return row.origin_airport is None or row.origin_airport == ""
    return True


def _row_signature(row: ImportCOGS) -> RowSignature:
    counterparty_type, counterparty_code, origin_country = _counterparty(row)
    return RowSignature(
        product_code=row.product_code.code,
        counterparty_type=counterparty_type,
        counterparty_code=counterparty_code,
        currency=row.currency,
        amount_signature=_amount_signature(row),
        origin_airport=row.origin_airport,
        origin_country=origin_country,
    )


def _coverage_signature(row: ImportCOGS) -> CoverageSignature:
    counterparty_type, counterparty_code, _origin_country = _counterparty(row)
    return CoverageSignature(
        product_code=row.product_code.code,
        counterparty_type=counterparty_type,
        counterparty_code=counterparty_code,
        currency=row.currency,
        amount_signature=_amount_signature(row),
    )


def _counterparty(row: ImportCOGS) -> tuple[str, str, str]:
    if row.agent_id:
        return ("agent", row.agent.code, row.agent.country_code or "")
    if row.carrier_id:
        return ("carrier", row.carrier.code, "")
    return ("none", "", "")


def _amount_signature(row: ImportCOGS) -> tuple[str, ...]:
    return (
        _decimal_value(row.rate_per_kg),
        _decimal_value(row.rate_per_shipment),
        _decimal_value(row.min_charge),
        _decimal_value(row.max_charge),
        _decimal_value(row.percent_rate),
        str(row.weight_breaks or ""),
    )


def _decimal_value(value: Decimal | None) -> str:
    if value is None:
        return ""
    return str(value.normalize())
