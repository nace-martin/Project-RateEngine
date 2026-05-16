# Pricing Rate Scope Audit Notes

This is a follow-up visibility pass to the ImportCOGS-specific audit. It does not change schema, selectors, quote math, seed data, or production data.

## Tables Covered

- `ExportCOGS`
- `ExportSellRate`
- `ImportSellRate`
- `DomesticCOGS`
- `DomesticSellRate`
- `LocalCOGSRate`
- `LocalSellRate`

`ImportCOGS` is intentionally excluded so the ImportCOGS audit PR stays small and reviewable.

## Scope Signals

- `LANE`: freight or lane-dependent charges that require both route endpoints or zones.
- `ORIGIN`: export/import origin-side local charges.
- `DESTINATION`: export/import destination-side local charges.
- `LOCAL`: domestic local charges without a safe origin/destination side.
- `UNKNOWN`: rows that cannot be safely classified from local row/product fields.

## Audit Focus

The dry-run audit reports:

- Non-lane candidates stored in lane-shaped tables.
- Lane candidates stored in local tables.
- Likely duplicate non-lane rows repeated across lane endpoints.
- UNKNOWN rows that need explicit review.

## Phase 2 Direction

Future normalization should:

- Add explicit scope only after table-specific data review.
- Keep lane rows requiring both route endpoints or zones.
- Keep local rows keyed by direction/location, not full lane.
- Normalize duplicated non-lane lane-table rows into local tables or scoped rows.
- Preserve deterministic selector behavior and current quote output during migration.
