# ImportCOGS Scope Normalization Notes

This documents the Phase 2 persisted-scope transition for `ImportCOGS`. The current quote path remains compatible with existing lane-shaped rows and quote output must not change.

## Current State

`ImportCOGS` stores lane freight and some standard local charges in the same lane-shaped table. That makes valid lane freight duplication look similar to likely invalid local-charge duplication:

- `LANE`: import air freight and lane-dependent freight rates.
- `ORIGIN`: origin documentation, origin AWB, origin agency, origin x-ray/screening, pickup, pickup FSC, and origin CTO charges.
- `DESTINATION`: destination terminal/handling, customs clearance, delivery/cartage, delivery FSC, and destination handling charges.
- `UNKNOWN`: rows that cannot be safely classified from local row/product fields.

## Phase 2 Direction

Phase 2 adds:

- A nullable explicit `scope` field with `LANE`, `ORIGIN`, `DESTINATION`, `LOCAL`, and `UNKNOWN`.
- A backfill that writes only `scope` using `classify_import_cogs_scope`.
- Audit output showing explicit scope, computed scope, mismatches, UNKNOWN rows, duplicate candidates, possible orphan groups, and rows ready for future consolidation review.
- Reversible rollback that clears the new scope values and removes the column.

Phase 2 intentionally does not yet:

- Allow `ORIGIN` rows to store `destination_airport = null`.
- Allow `DESTINATION` rows to store `origin_airport = null`.
- Enforce uniqueness constraints per scope.
- Delete, merge, compress, expire, or otherwise consolidate duplicate rows.

Future normalization should:

- Allow `ORIGIN` rows to store `destination_airport = null` only after selector compatibility is proven.
- Allow `DESTINATION` rows to store `origin_airport = null` only after selector compatibility is proven.
- Keep `LANE` rows requiring both `origin_airport` and `destination_airport`.
- Add uniqueness constraints per scope after production data is proven clean.
- Migrate duplicated origin/destination charges into normalized scoped rows in a separate approved cleanup PR.
- Preserve deterministic selector behavior, including `order_by('-valid_from', '-updated_at', '-id')`.
- Preserve quote totals and quote output during the migration.

## Selector Behavior

Selectors still support existing lane-shaped rows. They do not guess from missing endpoints and do not introduce fallback selection. Scoped rows are preferred only when a caller explicitly provides `metadata["rate_scope"]`; current quote flows do not pass that metadata.

Missing BUY data must continue to return incomplete/missing-rate signals rather than 500s.

## Rollback Plan

Reverse migration `pricing_v4.0028_rate_scope_phase2`. The reverse operation clears the new `scope` values and removes the column. No rate values, currencies, validity dates, ProductCodes, agents, or carriers are modified by the migration, so rollback does not require reconstructing rate data.

## Non-Goals For Phase 2

- No destructive migrations.
- No row deletion.
- No seed data changes.
- No quote-affecting pricing selection changes.
- No quote output changes.
- No runtime dependency on `audit_import_cogs_scope`.
