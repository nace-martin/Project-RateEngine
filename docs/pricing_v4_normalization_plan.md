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

---

## Phase 3B: Proposed Migration Approach

### Strategy: "Normalize and Deduplicate"
The goal of Phase 3B is to transition the identified rows to the normalized schema where `destination_airport` is `NULL` for `ORIGIN` scope and `origin_airport` is `NULL` for `DESTINATION` scope.

1. **Step 1: Create Target Rows**
   - For each group (or single row) identified in Phase 3A, create one new "Normalized" row.
   - The normalized row will have the redundant location field set to `NULL`.
   - The normalized row will inherit all other fields (product, amounts, currency, validity, etc.).

2. **Step 2: Update References**
   - If any other tables refer to these `ImportCOGS` IDs, they must be updated to point to the new normalized ID.
   - (Currently, no tables are known to refer to specific `ImportCOGS` row IDs by foreign key in a way that prevents deletion).

3. **Step 3: Delete Redundant Rows**
   - Once the normalized row is created, delete the original redundant rows.

4. **Step 4: Enforce Constraints**
   - Add database-level constraints to prevent future redundant data:
     - If `scope == 'ORIGIN'`, `destination_airport` MUST be `NULL`.
     - If `scope == 'DESTINATION'`, `origin_airport` MUST be `NULL`.
     - If `scope == 'LANE'`, both MUST be NOT `NULL`.

### Rollback Plan
- **Migration Rollback**: Standard Django migration `unapply` will remove the constraints but cannot automatically restore deleted rows.
- **Data Recovery**: A JSON backup of the rows being deleted should be taken before the migration.
- **Verification**: The `ImportPricingEngine` regression suite must pass before and after the migration.

### Risks
- **Selector Logic**: The `select_import_cogs_rate` selector must be updated to handle `NULL` values in the location fields. This was partially addressed in Phase 2 but needs full validation.
- **Ambiguity**: If multiple rates match an origin (e.g. one specific to a destination and one global), the selector must have clear tie-breaking rules (Specific > Global).
