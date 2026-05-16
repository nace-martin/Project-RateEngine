# Pricing Rate Scope Audit Notes

This now includes the Phase 2 persisted-scope groundwork. It does not change quote math, rate amounts, currencies, validity dates, counterparties, ProductCodes, seed data, or production data.

## Tables Covered

- `ExportCOGS`
- `ExportSellRate`
- `ImportSellRate`
- `DomesticCOGS`
- `DomesticSellRate`
- `LocalCOGSRate`
- `LocalSellRate`

`ImportCOGS` has a separate focused audit command because its buy-side transition has additional origin/destination coverage reporting.

## Scope Signals

- `LANE`: freight or lane-dependent charges that require both route endpoints or zones.
- `ORIGIN`: export/import origin-side local charges.
- `DESTINATION`: export/import destination-side local charges.
- `LOCAL`: domestic local charges without a safe origin/destination side.
- `UNKNOWN`: rows that cannot be safely classified from local row/product fields.

## Audit Focus

The dry-run audit reports:

- Explicit persisted scope.
- Computed transition scope.
- Scope mismatches.
- Non-lane candidates stored in lane-shaped tables.
- Lane candidates stored in local tables.
- Likely duplicate non-lane rows repeated across lane endpoints.
- UNKNOWN rows that need explicit review.
- Rows ready for future consolidation review.

## Migration Behavior

Migration `0028_rate_scope_phase2` adds nullable `scope` fields to all covered rate tables, then backfills only that new column:

- `ImportCOGS` uses the ImportCOGS-specific classifier.
- Export, import sell, domestic, and lane-shaped tables use the general pricing-rate classifier.
- `LocalCOGSRate` and `LocalSellRate` backfill to `LOCAL`.
- The reverse migration clears the new scope values before removing the columns.
- No rows are deleted, merged, expired, or otherwise consolidated.

`UNKNOWN` remains an audit/transition value only. Future normalized records should use `LANE`, `ORIGIN`, `DESTINATION`, or `LOCAL`.

## Selector Behavior

Runtime selectors continue to work with existing lane-shaped rows and preserve current quote output. They do not infer scope from missing endpoints and do not consolidate duplicates.

Selectors only prefer scoped rows when a caller explicitly supplies `metadata["rate_scope"]`; current quote flows do not pass that metadata. Ambiguity handling remains deterministic and still raises selector errors instead of falling back to newest-wins or first-row-wins.

## Rollback Plan

Rollback is schema-only and reversible:

1. Reverse migration `pricing_v4.0028_rate_scope_phase2`.
2. The reverse step clears persisted scope values, then removes the nullable columns.
3. Because Phase 2 does not alter rate values or delete rows, quote output reverts to the previous schema without data reconstruction.

## Phase 2 Direction

Phase 3 cleanup should:

- Review all mismatch and UNKNOWN rows.
- Keep lane rows requiring both route endpoints or zones.
- Keep local rows keyed by direction/location, not full lane.
- Add stricter constraints only after production data is proven clean.
- Normalize duplicated non-lane lane-table rows into local tables or scoped rows after review approval.
- Delete or merge no rows until a separate consolidation PR is approved.
- Preserve deterministic selector behavior and current quote output during migration.
