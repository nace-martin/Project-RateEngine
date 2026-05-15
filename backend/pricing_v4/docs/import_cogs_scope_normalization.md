# ImportCOGS Scope Normalization Notes

This is a Phase 2 preparation note only. The current `ImportCOGS` selector remains lane-based and still requires `origin_airport` plus `destination_airport`.

## Current State

`ImportCOGS` stores lane freight and some standard local charges in the same lane-shaped table. That makes valid lane freight duplication look similar to likely invalid local-charge duplication:

- `LANE`: import air freight and lane-dependent freight rates.
- `ORIGIN`: origin documentation, origin AWB, origin agency, origin x-ray/screening, pickup, pickup FSC, and origin CTO charges.
- `DESTINATION`: destination terminal/handling, customs clearance, delivery/cartage, delivery FSC, and destination handling charges.
- `UNKNOWN`: rows that cannot be safely classified from local row/product fields.

## Phase 2 Direction

Future normalization should:

- Add an explicit `scope` field with `LANE`, `ORIGIN`, `DESTINATION`, and `UNKNOWN`.
- Allow `ORIGIN` rows to store `destination_airport = null`.
- Allow `DESTINATION` rows to store `origin_airport = null`.
- Keep `LANE` rows requiring both `origin_airport` and `destination_airport`.
- Add uniqueness constraints per scope.
- Migrate duplicated origin/destination charges into normalized scoped rows.
- Preserve deterministic selector behavior, including `order_by('-valid_from', '-updated_at', '-id')`.
- Preserve quote totals and quote output during the migration.

## Non-Goals For Phase 1

- No destructive migrations.
- No row deletion.
- No seed data changes.
- No pricing selection changes.
- No quote output changes.
- No runtime dependency on `audit_import_cogs_scope`.
