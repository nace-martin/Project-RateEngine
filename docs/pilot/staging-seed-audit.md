# Phase 13.1A Staging Seed Audit

## 1. Executive summary

This phase is audit-only. No database records were created, updated, deleted, truncated, or overwritten.

The current local database is mostly ready for an Air Freight pilot from a hierarchy and location perspective, but not ready to seed staging blindly. The canonical RBAC hierarchy exists under the single active `Express Freight Management` organization, and active memberships currently have branch, department, and operating-entity scope. Legacy organization rows for `EFM PNG`, `EFM Australia`, `EFM Fiji`, and `EFM Solomon Islands` still exist as inactive records and must not be treated as canonical organizations.

The biggest seed gaps are ProductCode governance and staging-safe verification. Export ProductCodes are embedded inside corridor seed commands, import and domestic have dedicated ProductCode seed commands, and ChargeAlias seeding has a dry-run path. There is no single Air Freight pilot seed audit/apply command that checks required ProductCodes, aliases, locations, currencies, roles, memberships, and sample data readiness without mutating records.

## 2. Current known reference-data sources

- Core geography models: `Currency`, `Country`, `City`, `Airport`, `Port`, and `Location` in `backend/core/models.py`.
- RBAC hierarchy models: `Organization`, `OperatingEntity`, `Branch`, and `Department` in `backend/parties/models.py`.
- Role and membership models: `Role`, `Permission`, `RolePermission`, and `UserMembership` in `backend/accounts/models.py`.
- Pricing master data: `ProductCode`, `ChargeAlias`, `CanonicalChargeType`, `Carrier`, and `Agent` in `backend/pricing_v4/models.py`.
- Customer/supplier data: `Company`, `Contact`, and `CustomerCommercialProfile` in `backend/parties/models.py`.
- Reference-data templates: `docs/templates/reference-data-hub/`.
- Seed/import guidance: `docs/reference-data-seeding.md`, `docs/pre-production-runbook.md`, and `docs/pilot/air-freight-pilot-verification.md`.

Fallow baseline evidence was run before audit work:

- `npx fallow --format json`: completed with existing findings; summary included 104 dead-code issues plus health/duplicate findings.
- `npx fallow dead-code --format json`: completed with findings; 104 issues.
- `npx fallow dupes --format json`: completed with findings; 21 clone groups.
- `npx fallow health --format json`: completed with existing frontend complexity findings, including SPOT workspace components.

These findings are baseline evidence only. No cleanup was performed in this phase.

## 3. Existing seed commands / fixtures found

Hierarchy and RBAC:

- `python backend/manage.py seed_operating_entities`
  - Idempotently creates/updates canonical operating entities under `Express Freight Management`.
  - Current command uses codes `PNG`, `AUS`, `FJI`, and `SLB`, while the pilot shorthand asks for `EFM PNG`, `EFM AU`, `EFM FJ`, and `EFM SI`.
- `python backend/manage.py seed_final_rbac_hierarchy --dry-run`
  - Seeds canonical branches and departments under `Express Freight Management`.
  - Has dry-run support.
  - Uses branch codes `POM`, `LAE`, `BNE`, `SUV`, and `HIR`; the pilot checklist names branches as `POM`, `Lae`, `Brisbane`, `Suva`, and `Honiara`.
- `python backend/manage.py seed_rbac_foundation --json`
  - Seeds branches, departments, permissions, roles, role permissions, and memberships.
  - Does not expose a dry-run flag.
  - The older foundation constants include `FIJ`, `SOL`, `LAND`, `FINANCE`, and `ADMIN`, so it is not the canonical final hierarchy source.

Geography:

- `python backend/manage.py import_reference_data ... --dry-run`
  - Imports currencies, countries, cities, airports, and optional locations from CSV.
  - Has dry-run support.
- `python backend/manage.py normalize_locations --dry-run`
  - Repairs specific legacy city/airport location issues.
  - This command can update quotes and delete duplicate locations when not in dry-run mode; staging use must be explicitly reviewed before apply.
- Migration `backend/core/migrations/0004_backfill_locations.py`
  - Creates `Location` rows from existing `Airport` and `Port` rows during migration.

Pricing and ProductCodes:

- `python backend/manage.py seed_import_product_codes`
  - Idempotently uses `update_or_create` for import ProductCodes.
  - No dry-run flag.
- `python backend/manage.py seed_domestic_product_codes`
  - Idempotently uses `update_or_create` for domestic ProductCodes.
  - No dry-run flag.
  - Some embedded values use legacy units/categories such as `PER_KG`, `FLAT`, `SECURITY`, `SPECIAL`, and `TAX`, while the current model choices are `SHIPMENT`, `KG`, `PERCENT` and current categories such as `SCREENING` and `SURCHARGE`.
- Export ProductCodes are seeded inside corridor commands such as `seed_export_pom_bne`, rather than a standalone ProductCode-only command.
- `python backend/manage.py seed_charge_aliases --dry-run`
  - Safely seeds baseline `ChargeAlias` records from embedded Pack A aliases.
  - Has dry-run support and reports missing ProductCodes/conflicts.
- ProductCode data migrations:
  - `backend/pricing_v4/migrations/0024_import_origin_permit_and_customs_codes.py`
  - `backend/pricing_v4/migrations/0027_explicit_origin_customs_and_export_permit_codes.py`
  - `backend/pricing_v4/migrations/0032_seed_canonical_charge_types.py`

Customer/supplier seed tooling:

- `python backend/manage.py validate_customer_seed --customers customers.csv --contacts contacts.csv`
- `python backend/manage.py import_customers --file customers.csv --dry-run`
- `python backend/manage.py import_contacts --file contacts.csv --dry-run`
- `python backend/manage.py import_customer_discounts --file discounts.csv --dry-run`

Development-only or unsafe-for-staging commands:

- `bootstrap_dev`, `create_test_users`, `seed_test_users`, `seed_v3_compute_data`, `reset_quotes`, `clear_domestic_cogs`, `unseed_import_data`, and non-dry-run cleanup/apply commands must not be used for staging pilot seeding.

## 4. Required Air Freight pilot reference data

Hierarchy:

- One active organization: `Express Freight Management`.
- Active operating entities under that organization:
  - `EFM PNG`
  - `EFM Australia`
  - `EFM Fiji`
  - `EFM Solomon Islands`
- Active branches under the canonical organization:
  - `POM` / Port Moresby
  - `LAE` / Lae
  - `BNE` / Brisbane
  - `SUV` / Suva
  - `HIR` / Honiara
- Active departments under the canonical organization:
  - `AIR` / Air Freight
  - `SEA` / Sea Freight
  - `CUS` / Customs
  - `TRN` / Transport

Roles and memberships:

- System roles required: `admin`, `manager`, `sales`, and `finance`.
- Optional role gap: no read-only role currently exists in the inspected data/model seed definitions.
- Active pilot users must have active memberships with organization, operating entity, branch, department, role, and `is_primary=True`.

Air Freight ProductCodes:

- Export/import/domestic air freight.
- Fuel surcharge.
- Security/screening surcharge.
- AWB/docs.
- Import/export/origin/destination handling.
- Customs-related pass-through where applicable.
- Storage/warehouse if pilot scenarios include storage.
- Miscellaneous recoveries should be either mapped to an existing ProductCode or captured as a controlled manual-review gap, not auto-created without review.

Locations and currencies:

- Required currencies: `PGK`, `USD`, `AUD`, `SGD`, `EUR`.
- Required airports/locations: `POM`, `LAE`, `BNE`, `SYD`, `SIN`, `HKG`, `NRT`, `LAX`, `AKL`, plus any confirmed pilot origin/destination stations.
- `Location` rows must be active and airport-backed where possible.

Customers/suppliers:

- Do not seed real customers/suppliers in this phase.
- Staging should use a separate anonymized pilot data pack unless the business approves named staging records and confirms no sensitive customer data is included in repo docs.

## 5. Missing data checklist

Observed from the read-only local database audit:

- `LAX` exists as an active `Location`, but no matching `Airport` row was found in the inspected airport list.
- `EFM AU`, `EFM FJ`, and `EFM SI` are not current `OperatingEntity.code` values. Current codes are `AUS`, `FJI`, and `SLB`.
- No read-only role was found.
- Storage/warehouse ProductCode coverage was not found in the inspected ProductCode subset.
- Domestic ProductCode seed definitions contain legacy units/categories that do not match current model choices and should not be copied into a new staging seed path.
- Export ProductCodes are not isolated in a ProductCode-only seed command; they are coupled to corridor rate seeding.
- No single read-only command currently produces an Air Freight pilot readiness JSON for hierarchy, ProductCodes, aliases, locations, currencies, customer/supplier anonymization, and memberships.

Items already present in the read-only local database snapshot:

- Active `Express Freight Management` organization.
- Inactive legacy organization rows for `EFM PNG`, `EFM Australia`, `EFM Fiji`, and `EFM Solomon Islands`.
- Active canonical operating entities under `Express Freight Management`.
- Active canonical branches `POM`, `LAE`, `BNE`, `SUV`, and `HIR` under `Express Freight Management`.
- Active canonical departments `AIR`, `SEA`, `CUS`, and `TRN` under `Express Freight Management`.
- System roles `admin`, `manager`, `sales`, and `finance`.
- Active memberships: 12.
- Active memberships missing branch: 0.
- Active memberships missing department: 0.
- Active memberships missing operating entity: 0.
- Required currencies `PGK`, `USD`, `AUD`, `SGD`, and `EUR`.
- Active airport `Location` rows for `POM`, `LAE`, `BNE`, `SYD`, `SIN`, `HKG`, `NRT`, `LAX`, and `AKL`.

## 6. Duplicate/conflict risks

- Legacy organization rows for `EFM PNG`, `EFM Australia`, `EFM Fiji`, and `EFM Solomon Islands` still exist. They are inactive, but staging seed logic must never reactivate them or attach new pilot data to them.
- Existing branch and department rows exist under inactive legacy organizations and `EFM Express Air Cargo`. Seed logic must scope lookups to `Express Freight Management`, not just `code`.
- Branch code mismatch risk:
  - User-facing pilot names include `Suva` and `Honiara`.
  - Existing canonical codes are `SUV` and `HIR`.
  - A new seed must not create `Suva` or `Honiara` as codes by mistake.
- Operating entity code mismatch risk:
  - Pilot shorthand says `EFM AU`, `EFM FJ`, and `EFM SI`.
  - Existing model rows use `AUS`, `FJI`, and `SLB`.
  - Resolve this as display-name/shorthand documentation, not duplicate rows.
- ProductCode risk:
  - ProductCode has no `is_active` field. Do not invent one.
  - ProductCode IDs are manually assigned and domain-scoped: export `1xxx`, import `2xxx`, domestic `3xxx`.
  - ProductCode `code` is unique. Any new seed must detect code conflicts and ID conflicts separately.
- ChargeAlias risk:
  - Active aliases can conflict by normalized text, match type, mode scope, and direction scope.
  - Use `seed_charge_aliases --dry-run` and conflict reporting before applying any alias pack.
- Location risk:
  - Current `Location.code` is 3 characters and IATA-shaped. City aliases and non-airport locations require careful review.
  - `normalize_locations` can update quote FKs and delete duplicate location rows in apply mode; staging use should stay dry-run unless separately approved.
- Customer/supplier risk:
  - Real customer names, contacts, emails, and commercial terms are sensitive. Do not commit them into docs or fixtures.

## 7. Recommended safe idempotent seeding strategy

Phase 13.1B should add a dedicated management command, not migrations, for pilot reference-data readiness and additive seeding.

Recommended command shape:

```bash
python backend/manage.py air_freight_pilot_seed --dry-run --format json
python backend/manage.py air_freight_pilot_seed --apply --format json
```

Recommended behavior:

- Default to `--dry-run`; require an explicit write flag for apply.
- Read the current model fields only. Do not add invented fields such as `ProductCode.is_active`.
- Use `get_or_create` for missing immutable identity rows where defaults are safe.
- Use guarded `update_or_create` only for records owned by the seed pack and only for fields that are intended to be managed by the seed pack.
- Detect ID/code conflicts before writing ProductCodes.
- Validate ProductCode domain and ID range before writing.
- Validate unit/category values against current model choices before writing.
- Validate aliases with the same conflict rules as `seed_charge_aliases`.
- Emit machine-readable counts for `exists`, `would_create`, `would_update`, `conflict`, `blocked`, and `missing_dependency`.
- Never delete, truncate, or deactivate records by default.
- Mark pilot/demo data clearly where the model has an existing safe field for that purpose, such as `metadata` or CSV naming conventions. Do not add schema just for this phase unless separately approved.
- Keep `--reset` out of staging/production. If added later, restrict it to disposable local development and require an explicit environment guard.

## 8. What should never be overwritten

- Existing organizations, especially inactive legacy hierarchy rows.
- Historical Quote/SPOT rows and their hierarchy references.
- ProductCode primary keys, codes, domain, commercial meaning, GST treatment, GL codes, or `percent_of_product_code` unless the seed pack explicitly owns the row and a dry-run reports the exact change.
- Rate tables, rate validity windows, pricing behavior, SPOT envelopes, SPE charge lines, and quote calculation behavior.
- Existing `Company`, `Contact`, `CustomerCommercialProfile`, customer discounts, or supplier records.
- User passwords, tokens, groups, permissions outside the seed-owned system role/permission set, or manually curated memberships.
- Airport/location rows referenced by quotes unless a separate reviewed cleanup phase approves it.
- Any real sensitive customer/supplier data in docs, fixtures, or committed CSVs.

## 9. Suggested Phase 13.1B implementation plan

1. Add a read-only readiness command first:
   - `python backend/manage.py air_freight_pilot_seed_audit --format json`
   - It should inspect hierarchy, roles, memberships, ProductCodes, aliases, currencies, airports/locations, and customer/supplier anonymization readiness.
2. Add focused tests for the audit command:
   - Existing data returns `exists`.
   - Missing data returns `missing`.
   - Conflicting ProductCode code/ID returns `conflict`.
   - No writes occur in audit mode.
3. Add an apply-capable command only after audit output is accepted:
   - Default to dry-run.
   - Use additive, idempotent writes only.
   - Produce before/after counts.
4. Keep ProductCode seeding separate from rate seeding:
   - Extract/centralize Air Freight ProductCode definitions before touching rates.
   - Do not run corridor rate seed commands merely to create ProductCodes.
5. Add an anonymized pilot sample-data pack only if the business confirms sample scenarios:
   - Use fake customer/supplier names.
   - Validate with existing customer seed validators.
   - Do not commit real emails, account terms, or commercial customer data.
6. Run staging verification in dry-run first, then apply only after review approval.

## 10. Exact verification commands for staging

Run these first without writing data:

```bash
python backend/manage.py check
python backend/manage.py seed_final_rbac_hierarchy --dry-run
python backend/manage.py import_reference_data --currencies docs/templates/reference-data-hub/currencies.csv --countries docs/templates/reference-data-hub/countries.csv --cities docs/templates/reference-data-hub/cities.csv --airports docs/templates/reference-data-hub/airports.csv --locations docs/templates/reference-data-hub/locations.csv --dry-run
python backend/manage.py seed_charge_aliases --dry-run
python backend/manage.py normalize_locations --dry-run
pytest backend/quotes/tests
git diff --check
graphify update .
```

When Phase 13.1B adds the dedicated audit command, staging should also run:

```bash
python backend/manage.py air_freight_pilot_seed_audit --format json
```

Apply-mode commands must not be run in staging until the dry-run output has been reviewed and explicitly approved.
