# RateEngine v2 Database Migration Summary

This document provides a summary of the database migrations created to fix the issues in RateEngine v2.

## Migration Files

1. **0004_rateengine_v2_db_fixes.py**
   - Installs the `btree_gist` extension
   - Creates lookup tables for `currencies` and `units`
   - Seeds initial data for currencies (PGK, AUD, USD) and units (KG, CBM, WM, EA)
   - Adds `audience_id` fields to `organizations` and `pricing_policy` tables
   - Adds safety flags (`is_incomplete`, `incomplete_reason`) to `quotes` table
   - Adds `side` field to `quote_lines` table
   - Adds GIN indexes for JSONB columns
   - Adds uniqueness constraints and data integrity checks

2. **0005_add_currency_unit_fks.py**
   - Adds foreign key constraints for currency references (NOT VALID initially)
   - Adds foreign key constraints for unit references (NOT VALID initially)

3. **0006_add_audience_fks.py**
   - Adds foreign key constraints for audience references (NOT VALID initially)

4. **0007_add_quotes_safety_flags.py**
   - Adds safety flags to quotes table (`is_incomplete`, `incomplete_reason`)

5. **0008_add_jsonb_indexes_checks.py**
   - Adds GIN indexes for JSONB columns
   - Adds presence checks for required keys in JSONB columns

6. **0009_add_exclusion_constraints.py**
   - Adds exclusion constraints to prevent overlapping ranges:
     - `ratecards`: No overlapping date ranges per (provider_id, audience_id, name)
     - `cartage_ladders`: No overlapping numrange(min_weight_kg, max_weight_kg) per ratecard_id
     - `storage_tiers`: No overlapping int4range(week_from, week_to) per (ratecard_id, group_code)

7. **0010_add_uniqueness_integrity.py**
   - Adds uniqueness constraint for `route_legs` (route_id, sequence)
   - Adds data integrity check for `stations` iata field (3 uppercase characters)

8. **0011_refactor_quote_lines.py**
   - Adds `side` field to `quote_lines` table
   - Backfills `side` field from legacy `is_buy`/`is_sell` fields
   - Updates precision for quote_lines money fields

## Verification Script

The `verify_db_reform_v2.sql` script is provided to verify that all changes have been implemented correctly.

## Implementation Plan

1. Run the migrations in sequence
2. Verify the implementation using the verification script
3. Update application code to use the new columns and constraints
4. Plan follow-up migrations to remove legacy columns after application code is updated