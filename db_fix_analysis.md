# RateEngine v2 DB Fix Analysis

## 1. Unconstrained Strings for Currencies, Units, and Audiences

### Currencies
- `quotes.currency` (VARCHAR(3)) - unconstrained string
- `quote_lines.currency` (VARCHAR(3)) - unconstrained string
- `ratecard_fees.currency` (TEXT) - unconstrained string
- `service_items.currency` (TEXT) - unconstrained string
- `ratecards.currency` (TEXT) - unconstrained string

### Units
- `quote_lines.unit` (VARCHAR(16)) - unconstrained string

### Audiences
- `organizations.audience` (TEXT) - unconstrained string
- `pricing_policy.audience` (TEXT) - unconstrained string

## 2. JSON Columns Needing GIN Indexes and Checks

- `quotes.request_snapshot` (JSONField) - needs GIN index
- `ratecard_fees.applies_if` (JSONField) - needs GIN index and presence check
- `service_items.conditions_json` (JSONField) - needs GIN index and presence check

## 3. Overlapping Constraints Needed

- `ratecards` - no overlapping date ranges per (provider_id, audience_id, name)
- `cartage_ladders` - no overlapping numrange(min_weight_kg, max_weight_kg) per ratecard_id
- `storage_tiers` - no overlapping int4range(week_from, week_to) per (ratecard_id, group_code)

## 4. Missing Uniqueness/Integrity Constraints

- `route_legs` - missing UNIQUE (route_id, sequence)
- `stations` - iata field should be exactly 3 uppercase characters

## 5. BUY/SELL Modeling Issues

- `quote_lines` uses two booleans (is_buy, is_sell) which can conflict
- Should be one side field with values 'BUY' or 'SELL'

## 6. Money & Currency Inconsistencies

- Mixed precision in quote_lines:
  - `unit_price` - DECIMAL(12,4) should be DECIMAL(18,4)
  - `extended_price` - DECIMAL(12,2) should be DECIMAL(18,2)

## 7. Safety Flags Needed

- `quotes.is_incomplete` - BOOLEAN NOT NULL DEFAULT FALSE
- `quotes.incomplete_reason` - TEXT

## 8. Required Changes Summary

### Lookup Tables
- Create `currencies` table with code (PK), name, is_active
- Create `units` table with code (PK), label
- Seed currencies: ['PGK','AUD','USD']
- Seed units: ['KG','CBM','WM','EA']

### Foreign Key Constraints
- Add FKs from currency columns to `currencies.code`
- Add FKs from unit columns to `units.code`
- Add `audience_id` to `organizations` and `pricing_policy` tables
- Add FKs to `audiences.id`

### JSON Improvements
- Add GIN indexes on JSONB columns
- Add presence checks for required keys

### Exclusion Constraints
- Add exclusion constraints to prevent overlapping ranges

### Data Integrity
- Add uniqueness constraints where missing
- Add checks for data validation (iata format)

### Quote Lines Refactoring
- Add `side` field (TEXT CHECK IN ('BUY','SELL') DEFAULT 'SELL')
- Convert money precision
- Backfill from legacy is_buy/is_sell fields