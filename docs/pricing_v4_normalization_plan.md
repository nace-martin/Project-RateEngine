# Pricing V4 Normalization Plan: ImportCOGS

## Phase 3A: Consolidation Planning (Origin-Scoped Rates)

### Findings
The initial audit of `ImportCOGS` identified 14 rows (IDs #100-#113) classified as `ORIGIN` scope. These rows represent origin-side charges (e.g., Documentation, Pickup, Screening) for shipments from BNE and SYD to POM.

- **Current State**: These charges are stored with explicit `origin_airport` and `destination_airport` (POM), even though they are independent of the destination.
- **Normalization Opportunity**: These rows can be "normalized" by clearing the `destination_airport` field, making them valid for ANY destination from that origin.
- **Consolidation**: No actual "duplicates" (multiple rows for the same origin/product with identical rates) were found in the current dev database. However, the planner is now equipped to detect and group such rows if they appear.

### Consolidation Groups
The `plan_import_cogs_consolidation` command identifies the following candidates:

1. **SINGLE** candidates (Normalization only): 14 rows found.
   - Example: `#100 IMP-AGENCY-ORIGIN BNE->POM` -> Target: `BNE -> *`
   - All 14 rows are safe to normalize as they currently exist for only one destination (POM) per origin.

2. **GROUP** candidates (Actual Consolidation): 0 groups found.
   - If a row for `BNE->POM` and `BNE->SIN` existed with identical rates, they would be grouped.

## Phase 3B: Execution (Origin-Scoped Normalization) - COMPLETED

### Actions Taken
1. **Schema Update**: `ImportCOGS` location fields (`origin_airport`, `destination_airport`) made nullable (Migration `0029`).
2. **Data Normalization**: 14 `ORIGIN` scoped rows for BNE and SYD normalized by clearing their redundant `destination_airport` (Migration `0030`).
3. **Selector Compatibility**: `RateSelector` logic updated to handle `NULL` locations. It now matches `ORIGIN` rows by `origin_airport` and allows `destination_airport` to be `NULL`.
4. **Engine Integration**: `ImportPricingEngine` now explicitly passes `rate_scope` metadata to the selector, ensuring deterministic resolution of origin/destination/lane rates.

### Verification Results
- **Planner Output**: `Summary: 0 consolidation candidates found` (All previous candidates are now normalized).
- **Audit Output**: `Rows ready for future consolidation review: none`.
- **Regression Suite**: 35 tests passed, including `ImportPricingEngine` and `QuotePublicDetailAPI`.
- **Quote Stability**: Proved that normalized rows resolve correctly for existing lanes (BNE->POM, SYD->POM) without changing totals.

---

## Phase 4: Proposed Migration Approach (Strict Constraints)

