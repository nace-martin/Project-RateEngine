# RateEngine v2 Database Fix Plan

## Overview

This document outlines the comprehensive plan for fixing the database issues in RateEngine v2. The changes address several critical problems including unconstrained strings, missing foreign key constraints, overlapping data ranges, and inconsistent data modeling.

## Issues Addressed

1. **Unconstrained Strings**: Business-critical strings like currencies, units, and audiences were stored as plain text, leading to typos, drift, and broken joins.
2. **Pricing Ambiguity**: Ratecards allowed overlapping effective windows; ladders/tiers could overlap, causing ambiguous pricing.
3. **JSON Performance**: JSON columns lacked proper indexes and validation, leading to silent drift and slow queries.
4. **BUY/SELL Modeling**: The use of two boolean fields (is_buy, is_sell) could lead to conflicts.
5. **Money Precision**: Inconsistent precision in monetary fields.
6. **Missing Integrity**: Missing uniqueness constraints and data validation checks.
7. **Delete/Child Semantics**: Unclear foreign key delete policies.

## Target State

### Lookup Tables
- `currencies(code PK, name, is_active default true)`
- `units(code PK, label)`
- Seed at least: currencies ['PGK','AUD','USD']; units ['KG','CBM','WM','EA']

### Foreign Key Constraints
- All business-critical strings now reference lookup tables:
  - `quotes.currency` → `currencies(code)`
  - `quote_lines.currency` → `currencies(code)`
  - `quote_lines.unit` → `units(code)`
  - `ratecard_fees.currency` → `currencies(code)`
  - `service_items.currency` → `currencies(code)`
  - `organizations.audience_id` → `audiences(id)`
  - `pricing_policy.audience_id` → `audiences(id)`

### Safety Flags
- `quotes.is_incomplete BOOLEAN NOT NULL DEFAULT FALSE`
- `quotes.incomplete_reason TEXT`

### Quote Lines Refactoring
- `quote_lines.side TEXT CHECK (side IN ('BUY','SELL')) DEFAULT 'SELL'`
- Converted money precision:
  - `quote_lines.unit_price NUMERIC(18,4)`
  - `quote_lines.extended_price NUMERIC(18,2)`

### JSON Improvements
- GIN indexes on:
  - `quotes.request_snapshot jsonb_path_ops`
  - `ratecard_fees.applies_if jsonb_path_ops`
  - `service_items.conditions_json jsonb_path_ops`
- Presence checks:
  - `ratecard_fees.applies_if ? 'kind'`
  - `service_items.conditions_json ? 'kind'`

### Data Integrity
- `route_legs UNIQUE (route_id, sequence)`
- `stations CHECK (length(iata)=3) AND iata = upper(iata)`

### Exclusion Constraints
- `ratecards`: No overlapping date ranges per (provider_id, audience_id, name)
- `cartage_ladders`: No overlapping numrange(min_weight_kg, max_weight_kg) per ratecard_id
- `storage_tiers`: No overlapping int4range(week_from, week_to) per (ratecard_id, group_code)

## Implementation Approach

### Migration Sequence
1. Install `btree_gist` extension for exclusion constraints
2. Create lookup tables (`currencies`, `units`) and seed data
3. Add new columns (`audience_id`, `is_incomplete`, `incomplete_reason`, `side`)
4. Add foreign key constraints as NOT VALID to avoid blocking writes
5. Add JSONB indexes and checks
6. Add exclusion constraints for overlapping ranges
7. Add uniqueness and data integrity constraints
8. Backfill data where necessary
9. Validate foreign key constraints in a separate migration after data verification

### Error Handling Rules
- If an FK add fails: Ensure seeds exist; add FK as NOT VALID; then VALIDATE
- If exclusion constraint creation fails: Run overlap audits; report violating row ids; do not force-create constraint
- If JSON GIN index creation blocks writes: Schedule off-peak or split into a CONCURRENTLY follow-up migration
- If legacy columns still referenced by app code: Keep legacy columns; create a follow-up migration to drop them only after code switches to *_id

## Verification

A verification script (`verify_db_reform_v2.sql`) is provided to check that all changes have been implemented correctly:

1. Extensions present: `btree_gist`
2. Tables exist: `currencies`, `units`
3. Columns exist: `quotes.is_incomplete`, `quotes.incomplete_reason`, `quote_lines.side`
4. Precision: `quote_lines.unit_price` (18,4), `extended_price` (18,2)
5. FKs exist and are VALIDATED for all currency/unit paths
6. Exclusion constraints present on `ratecards`, `cartage_ladders`, `storage_tiers`
7. GIN indexes exist on the three JSONB columns
8. `route_legs` unique present; `stations` iata check present + bad rows count == 0
9. Overlap audit returns 0 pairs

## Minimal Acceptance Tests (DB-level)

1. Inserting a second `ratecards` row with overlapping window for same (provider_id, audience_id, name) → IntegrityError
2. Inserting `cartage_ladders` rows with overlapping numrange for same ratecard_id → IntegrityError
3. Inserting `storage_tiers` rows with overlapping int4range for same (ratecard_id, group_code) → IntegrityError
4. Inserting a quote with no explicit incomplete fields → is_incomplete=FALSE, incomplete_reason=NULL
5. Setting is_incomplete=TRUE and a reason → round-trips values
6. Inserting quote_lines with side not in ('BUY','SELL') → IntegrityError
7. Inserting station with iata='cx' or length != 3 → CHECK violation

## Non-goals

1. Do not drop legacy text columns until the app reads only *_id (follow-up)
2. Do not change ON DELETE policies without explicit instruction
3. Do not convert JSON payloads to tables (only add checks/indexes)

## Migration Files Created

1. `0004_rateengine_v2_db_fixes.py` - Initial setup and lookup tables
2. `0005_add_currency_unit_fks.py` - Currency and unit foreign key constraints
3. `0006_add_audience_fks.py` - Audience foreign key constraints
4. `0007_add_quotes_safety_flags.py` - Safety flags for quotes
5. `0008_add_jsonb_indexes_checks.py` - JSONB indexes and checks
6. `0009_add_exclusion_constraints.py` - Exclusion constraints for overlapping ranges
7. `0010_add_uniqueness_integrity.py` - Uniqueness and data integrity constraints
8. `0011_refactor_quote_lines.py` - Quote lines refactoring

## Next Steps

1. Run the migrations in sequence
2. Verify the implementation using the verification script
3. Update application code to use the new columns and constraints
4. Plan follow-up migrations to remove legacy columns after application code is updated