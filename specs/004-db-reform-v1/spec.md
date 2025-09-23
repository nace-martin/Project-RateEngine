# Feature Specification: DB Reform v1

**Feature Branch**: `004-db-reform-v1`  
**Created**: Tuesday 23 September 2025  
**Status**: Draft  
**Input**: User description: "— “DB Reform v1” Intent Lock down core enums (currencies/units/audience), prevent overlapping ratecards & ladders, add quote fail-safe flags, standardize money precision, and speed up JSON filters—without breaking current data. Files to add/modify 1) backend/pricing_v2/migrations/0101_currencies_units_and_fks.py from django.db import migrations DDL = r""" CREATE TABLE IF NOT EXISTS currencies( code CHAR(3) PRIMARY KEY, name TEXT, is_active BOOLEAN NOT NULL DEFAULT TRUE ); CREATE TABLE IF NOT EXISTS units( code TEXT PRIMARY KEY, label TEXT ); -- Wire obvious FK columns (keep types as-is; we just add contracts now) ALTER TABLE quotes ADD CONSTRAINT fk_quotes_currency FOREIGN KEY (currency) REFERENCES currencies(code); ALTER TABLE quote_lines ADD CONSTRAINT fk_quote_lines_currency FOREIGN KEY (currency) REFERENCES currencies(code); ALTER TABLE quote_lines ADD CONSTRAINT fk_quote_lines_unit FOREIGN KEY (unit) REFERENCES units(code); -- Optional seeds (safe re-runs) INSERT INTO currencies(code,name) VALUES ('PGK','Papua New Guinean Kina'), ('AUD','Australian Dollar'), ('USD','US Dollar') ON CONFLICT (code) DO NOTHING; INSERT INTO units(code,label) VALUES ('KG','Kilogram'),('CBM','Cubic Meter'),('WM','Weight/M3'),('EA','Each') ON CONFLICT (code) DO NOTHING; """ class Migration(migrations.Migration): dependencies = [] operations = [migrations.RunSQL(DDL)] 2) backend/pricing_v2/migrations/0102_audience_fk_backfill.py from django.db import migrations FORWARD = r""" -- Add FK columns ALTER TABLE organizations ADD COLUMN IF NOT EXISTS audience_id BIGINT; ALTER TABLE pricing_policy ADD COLUMN IF NOT EXISTS audience_id BIGINT; -- Backfill from text code via audiences.code UPDATE organizations o SET audience_id = a.id FROM audiences a WHERE o.audience_id IS NULL AND o.audience = a.code; UPDATE pricing_policy p SET audience_id = a.id FROM audiences a WHERE p.audience_id IS NULL AND p.audience = a.code; -- Enforce FKs and (optionally) drop old text columns later ALTER TABLE organizations ADD CONSTRAINT fk_orgs_audience FOREIGN KEY (audience_id) REFERENCES audiences(id); ALTER TABLE pricing_policy ADD CONSTRAINT fk_policy_audience FOREIGN KEY (audience_id) REFERENCES audiences(id); -- Keep originals for rollback; app code should start reading *_id """ BACKWARD = r""" ALTER TABLE organizations DROP CONSTRAINT IF EXISTS fk_orgs_audience; ALTER TABLE pricing_policy DROP CONSTRAINT IF EXISTS fk_policy_audience; """ class Migration(migrations.Migration): dependencies = [("pricing_v2","0101_currencies_units_and_fks")] operations = [migrations.RunSQL(FORWARD, BACKWARD)] 3) backend/pricing_v2/migrations/0103_ratecards_exclusion_constraints.py from django.db import migrations DDL = r""" CREATE EXTENSION IF NOT EXISTS btree_gist; -- Block overlapping effective windows for same (provider,audience,name) DO $ BEGIN IF NOT EXISTS ( SELECT 1 FROM pg_constraint WHERE conname='ratecards_no_overlap' ) THEN ALTER TABLE ratecards ADD CONSTRAINT ratecards_no_overlap EXCLUDE USING gist ( provider_id WITH =, audience_id WITH =, name WITH =, daterange(effective_date, COALESCE(expiry_date,'9999-12-31')) WITH && ); END IF; END $; """ class Migration(migrations.Migration): dependencies = [("pricing_v2","0102_audience_fk_backfill")] operations = [migrations.RunSQL(DDL)] 4) backend/pricing_v2/migrations/0104_cartage_storage_no_overlap.py from django.db import migrations DDL = r""" CREATE EXTENSION IF NOT EXISTS btree_gist; -- Weight-band overlap shield per ratecard DO $ BEGIN IF NOT EXISTS ( SELECT 1 FROM pg_constraint WHERE conname='cartage_ladders_no_overlap' ) THEN ALTER TABLE cartage_ladders ADD CONSTRAINT cartage_ladders_no_overlap EXCLUDE USING gist ( ratecard_id WITH =, numrange(min_weight_kg, max_weight_kg, '[]') WITH && ); END IF; END $; -- Storage tiers no-overlap per ratecard/group_code DO $ BEGIN IF NOT EXISTS ( SELECT 1 FROM pg_constraint WHERE conname='storage_tiers_no_overlap' ) THEN ALTER TABLE storage_tiers ADD CONSTRAINT storage_tiers_no_overlap EXCLUDE USING gist ( ratecard_id WITH =, group_code WITH =, int4range(week_from, week_to, '[]') WITH && ); END IF; END $; """ class Migration(migrations.Migration): dependencies = [("pricing_v2","0103_ratecards_exclusion_constraints")] operations = [migrations.RunSQL(DDL)] 5) backend/pricing_v2/migrations/0105_quote_lines_side_precision.py from django.db import migrations SQL = r""" ALTER TABLE quote_lines ADD COLUMN IF NOT EXISTS side TEXT CHECK (side IN ('BUY','SELL')) DEFAULT 'SELL'; -- Make money precision consistent ALTER TABLE quote_lines ALTER COLUMN unit_price TYPE NUMERIC(18,4), ALTER COLUMN extended_price TYPE NUMERIC(18,2); -- (Optional) migrate legacy is_buy/is_sell into side if present UPDATE quote_lines SET side='BUY' WHERE is_buy = TRUE AND is_sell = FALSE; UPDATE quote_lines SET side='SELL' WHERE is_sell = TRUE AND is_buy = FALSE; """ class Migration(migrations.Migration): dependencies = [("pricing_v2","0104_cartage_storage_no_overlap")] operations = [migrations.RunSQL(SQL)] 6) backend/pricing_v2/migrations/0106_quotes_incomplete_flags.py from django.db import migrations SQL = r""" ALTER TABLE quotes ADD COLUMN IF NOT EXISTS is_incomplete BOOLEAN NOT NULL DEFAULT FALSE, ADD COLUMN IF NOT EXISTS incomplete_reason TEXT; """ class Migration(migrations.Migration): dependencies = [("pricing_v2","0105_quote_lines_side_precision")] operations = [migrations.RunSQL(SQL)] 7) backend/pricing_v2/migrations/0107_jsonb_indexes_checks.py from django.db import migrations SQL = r""" -- Speed up JSON filters CREATE INDEX IF NOT EXISTS quotes_req_snapshot_gin ON quotes USING gin (request_snapshot jsonb_path_ops); CREATE INDEX IF NOT EXISTS ratecard_fees_applies_if_gin ON ratecard_fees USING gin (applies_if jsonb_path_ops); CREATE INDEX IF NOT EXISTS service_items_conditions_gin ON service_items USING gin (conditions_json jsonb_path_ops); -- Minimal JSON presence checks ALTER TABLE ratecard_fees ADD CONSTRAINT chk_applies_if_has_kind CHECK (applies_if ? 'kind') NOT VALID; ALTER TABLE service_items ADD CONSTRAINT chk_conditions_has_kind CHECK (conditions_json ? 'kind') NOT VALID; """ class Migration(migrations.Migration): dependencies = [("pricing_v2","0106_quotes_incomplete_flags")] operations = [migrations.RunSQL(SQL)] 8) backend/pricing_v2/migrations/0108_route_legs_unique_seq.py from django.db import migrations SQL = r""" -- One position per route ALTER TABLE route_legs ADD CONSTRAINT route_legs_route_id_sequence_uniq UNIQUE (route_id, sequence); """ class Migration(migrations.Migration): dependencies = [("pricing_v2","0107_jsonb_indexes_checks")] operations = [migrations.RunSQL(SQL)] 9) backend/pricing_v2/migrations/0109_currency_fk_other_tables.py from django.db import migrations SQL = r""" -- Tighten fee/service currencies to lookup ALTER TABLE ratecard_fees ADD CONSTRAINT fk_ratecard_fees_currency FOREIGN KEY (currency) REFERENCES currencies(code); ALTER TABLE service_items ADD CONSTRAINT fk_service_items_currency FOREIGN KEY (currency) REFERENCES currencies(code); """ class Migration(migrations.Migration): dependencies = [("pricing_v2","0108_route_legs_unique_seq")] operations = [migrations.RunSQL(SQL)] 10) backend/pricing_v2/migrations/0110_stations_iata_check.py from django.db import migrations SQL = r""" -- Enforce 3-letter uppercase IATA in stations (stored as text in current schema) ALTER TABLE stations ADD CONSTRAINT chk_stations_iata_len CHECK (length(iata)=3) NOT VALID; -- Optional: normalize to uppercase UPDATE stations SET iata = upper(iata); """ class Migration(migrations.Migration): dependencies = [("pricing_v2","0109_currency_fk_other_tables")] operations = [migrations.RunSQL(SQL)]"

## Execution Flow (main)
```
1. Parse user description from Input
   → If empty: ERROR "No feature description provided"
2. Extract key concepts from description
   → Identify: actors, actions, data, constraints
3. For each unclear aspect:
   → Mark with [NEEDS CLARIFICATION: specific question]
4. Fill User Scenarios & Testing section
   → If no clear user flow: ERROR "Cannot determine user scenarios"
5. Generate Functional Requirements
   → Each requirement must be testable
   → Mark ambiguous requirements
6. Identify Key Entities (if data involved)
7. Run Review Checklist
   → If any [NEEDS CLARIFICATION]: WARN "Spec has uncertainties"
   → If implementation details found: ERROR "Remove tech details"
8. Return: SUCCESS (spec ready for planning)
```

---

## ⚡ Quick Guidelines
- ✅ Focus on WHAT users need and WHY
- ❌ Avoid HOW to implement (no tech stack, APIs, code structure)
- 👥 Written for business stakeholders, not developers

### Section Requirements
- **Mandatory sections**: Must be completed for every feature
- **Optional sections**: Include only when relevant to the feature
- When a section doesn't apply, remove it entirely (don't leave as "N/A")

### For AI Generation
When creating this spec from a user prompt:
1. **Mark all ambiguities**: Use [NEEDS CLARIFICATION: specific question] for any assumption you'd need to make
2. **Don't guess**: If the prompt doesn't specify something (e.g., "login system" without auth method), mark it
3. **Think like a tester**: Every vague requirement should fail the "testable and unambiguous" checklist item
4. **Common underspecified areas**:
   - User types and permissions
   - Data retention/deletion policies  
   - Performance targets and scale
   - Error handling behaviors
   - Integration requirements
   - Security/compliance needs

---

## User Scenarios & Testing *(mandatory)*

### Primary User Story
As a system administrator, I want to ensure data integrity and consistency across the pricing and quoting modules, so that I can prevent invalid data entries, improve performance, and provide accurate quotes to customers.

### Acceptance Scenarios
1. **Given** a new ratecard is created with an effective date that overlaps with an existing ratecard for the same provider, audience, and name, **When** the system attempts to save the new ratecard, **Then** the system MUST prevent the creation and raise an integrity error.
2. **Given** a new quote is created without specifying `is_incomplete` and `incomplete_reason`, **When** the system saves the quote, **Then** the `is_incomplete` flag MUST default to `FALSE` and `incomplete_reason` MUST be `NULL`.
3. **Given** a new quote is created with `is_incomplete` set to `TRUE` and `incomplete_reason` provided, **When** the system saves the quote, **Then** the `is_incomplete` flag MUST be `TRUE` and `incomplete_reason` MUST match the provided value.
4. **Given** a cartage ladder is defined with a weight band that overlaps with an existing cartage ladder for the same ratecard, **When** the system attempts to save the new cartage ladder, **Then** the system MUST prevent the creation and raise an integrity error.
5. **Given** a storage tier is defined with a week range that overlaps with an existing storage tier for the same ratecard and group code, **When** the system attempts to save the new storage tier, **Then** the system MUST prevent the creation and raise an integrity error.
6. **Given** a quote line is created, **When** the system saves the quote line, **Then** the `unit_price` column MUST have a precision of 4 decimal places and `extended_price` MUST have a precision of 2 decimal places.
7. **Given** a station is created with an IATA code, **When** the system saves the station, **Then** the IATA code MUST be converted to uppercase and its length MUST be exactly 3 characters.

### Edge Cases
- What happens when a user attempts to create a ratecard with an `expiry_date` that is earlier than its `effective_date`? [NEEDS CLARIFICATION: Should this be prevented by the system or handled by business logic?]
- How does the system handle existing data that violates the new constraints (e.g., overlapping ratecards) during migration? [NEEDS CLARIFICATION: The migrations are designed to be idempotent, but what is the expected behavior for existing invalid data?]
- What is the impact on performance for JSON filters after adding GIN indexes? [NEEDS CLARIFICATION: Are there specific performance targets for JSON queries?]

## Requirements *(mandatory)*

### Functional Requirements
- **FR-001**: The system MUST enforce unique currency codes and unit codes.
- **FR-002**: The system MUST establish foreign key relationships for currencies and units in `quotes` and `quote_lines` tables.
- **FR-003**: The system MUST add an `audience_id` column to `organizations` and `pricing_policy` tables.
- **FR-004**: The system MUST backfill `audience_id` in `organizations` and `pricing_policy` tables based on existing `audience` text codes.
- **FR-005**: The system MUST enforce foreign key relationships for `audience_id` in `organizations` and `pricing_policy` tables, referencing the `audiences` table.
- **FR-006**: The system MUST prevent overlapping effective date windows for ratecards with the same provider, audience, and name.
- **FR-007**: The system MUST prevent overlapping weight bands for cartage ladders within the same ratecard.
- **FR-008**: The system MUST prevent overlapping week ranges for storage tiers within the same ratecard and group code.
- **FR-009**: The system MUST add a `side` column to `quote_lines` with a default value of 'SELL' and a check constraint for 'BUY' or 'SELL'.
- **FR-010**: The system MUST ensure `unit_price` in `quote_lines` has a numeric precision of (18,4) and `extended_price` has a numeric precision of (18,2).
- **FR-011**: The system MUST migrate existing `is_buy`/`is_sell` flags in `quote_lines` to the new `side` column.
- **FR-012**: The system MUST add `is_incomplete` (BOOLEAN, default FALSE) and `incomplete_reason` (TEXT) columns to the `quotes` table.
- **FR-013**: The system MUST create GIN indexes on `quotes.request_snapshot`, `ratecard_fees.applies_if`, and `service_items.conditions_json` for faster JSON filtering.
- **FR-014**: The system MUST add check constraints to `ratecard_fees.applies_if` and `service_items.conditions_json` to ensure the presence of a 'kind' key.
- **FR-015**: The system MUST enforce a unique constraint on `route_id` and `sequence` in the `route_legs` table.
- **FR-016**: The system MUST establish foreign key relationships for currency in `ratecard_fees` and `service_items` tables.
- **FR-017**: The system MUST enforce that `iata` codes in the `stations` table are 3 characters long and uppercase.

### Key Entities *(include if feature involves data)*
- **Currencies**: Represents different monetary units with a unique code, name, and active status.
- **Units**: Represents different units of measurement with a unique code and label.
- **Audiences**: Represents target groups for pricing policies and organizations.
- **Ratecards**: Defines pricing rules, including provider, audience, name, effective dates, and currency.
- **Cartage Ladders**: Defines weight-based pricing tiers within a ratecard.
- **Storage Tiers**: Defines week-based storage pricing tiers within a ratecard and group code.
- **Quotes**: Represents a pricing quotation, including status, request snapshot, totals, currency, and organization.
- **Quote Lines**: Represents individual line items within a quote, including unit price, extended price, side (BUY/SELL), currency, and unit.
- **Organizations**: Represents entities associated with quotes and pricing policies, now with an explicit `audience_id`.
- **Pricing Policy**: Defines pricing rules, now with an explicit `audience_id`.
- **Ratecard Fees**: Represents fees associated with ratecards, including currency and conditions.
- **Service Items**: Represents service offerings, including currency and conditions.
- **Route Legs**: Represents segments of a route, with a sequence within a route.
- **Stations**: Represents locations with an IATA code.

---

## Review & Acceptance Checklist
*GATE: Automated checks run during main() execution*

### Content Quality
- [ ] No implementation details (languages, frameworks, APIs)
- [ ] Focused on user value and business needs
- [ ] Written for non-technical stakeholders
- [ ] All mandatory sections completed

### Requirement Completeness
- [ ] No [NEEDS CLARIFICATION] markers remain
- [ ] Requirements are testable and unambiguous  
- [ ] Success criteria are measurable
- [ ] Scope is clearly bounded
- [ ] Dependencies and assumptions identified

---

## Execution Status
*Updated by main() during processing*

- [ ] User description parsed
- [ ] Key concepts extracted
- [ ] Ambiguities marked
- [ ] User scenarios defined
- [ ] Requirements generated
- [ ] Entities identified
- [ ] Review checklist passed

---
