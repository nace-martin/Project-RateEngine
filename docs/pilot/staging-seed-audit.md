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

## 11. Phase 13.1B read-only audit command

Phase 13.1B adds a dedicated read-only management command:

```bash
python backend/manage.py air_freight_pilot_seed_audit --format json
python backend/manage.py air_freight_pilot_seed_audit --format text
```

The command does not create, update, delete, truncate, or overwrite database records. It has no apply mode, no reset mode, and no seed mode.

Sample JSON shape:

```json
{
  "status": "not_ready",
  "summary": {
    "missing_count": 3,
    "conflict_count": 1,
    "warning_count": 0
  },
  "hierarchy": {},
  "roles_memberships": {},
  "product_codes": {},
  "charge_aliases": {},
  "locations": {},
  "currencies": {},
  "pilot_data": {},
  "conflicts": [
    {
      "section": "product_codes",
      "detail": "Air Freight has 2 possible ProductCodes; review mapping."
    }
  ],
  "missing": [
    {
      "section": "charge_aliases",
      "item": "fsc"
    }
  ],
  "warnings": [],
  "recommended_next_actions": [
    "Review missing reference data before Air Freight UAT."
  ]
}
```

Interpretation:

- `ready`: no missing required reference data, no conflicts, and no warnings.
- `ready_with_warnings`: required reference data is present, but non-blocking membership/model warnings need review.
- `not_ready`: at least one required item is missing or at least one conflict needs human resolution.

Use the JSON output for staging sign-off evidence. Use text output only for quick operator checks.

## 12. Phase 13.1C actual audit result and remediation checklist

Phase 13.1C ran the Phase 13.1B read-only audit command against the current environment. No seed writes, migrations, frontend changes, production code changes, or database mutations were performed.

Commands run:

```bash
python backend/manage.py air_freight_pilot_seed_audit --format json
python backend/manage.py air_freight_pilot_seed_audit --format text
```

Actual audit summary:

- Status: `not_ready`
- Missing items: `10`
- Conflicts: `8`
- Warnings: `0`
- Hierarchy readiness: canonical organization, operating entities, branches, and departments are present.
- Roles and membership readiness: required roles are present; active and primary memberships are complete in the audited environment.
- Currency readiness: `PGK`, `USD`, `AUD`, `SGD`, and `EUR` are present.
- Location readiness: `POM`, `LAE`, `BNE`, `SYD`, `SIN`, `HKG`, `NRT`, `LAX`, and `AKL` have matching location coverage.
- Pilot/demo data: no obvious pilot/demo company records were reported; output contains counts only and no sensitive customer details.

Issue classification:

| Section | Item | Classification | Pilot impact | Remediation |
| --- | --- | --- | --- | --- |
| ProductCodes | `import_handling` | Missing canonical seed data | Blocker if import handling charges are in pilot supplier replies | Add or map a reviewed ProductCode using current ProductCode fields only. |
| ProductCodes | `storage_warehouse` | Missing canonical seed data | Blocker if storage or warehouse recoveries are in pilot supplier replies | Add or map a reviewed ProductCode using current ProductCode fields only. |
| ProductCodes | `misc_recoveries` | Missing canonical seed data | Blocker for unmatched recoveries that must be quoted rather than rejected | Add or map a reviewed miscellaneous recovery ProductCode. |
| ChargeAlias | `freight` | Missing canonical seed data | Blocker for common supplier freight labels | Add a reviewed alias after ProductCode mapping is confirmed. |
| ChargeAlias | `screening` | Missing canonical seed data | Blocker for security screening labels | Add a reviewed alias after ProductCode mapping is confirmed. |
| ChargeAlias | `awb` | Missing canonical seed data | Blocker for AWB/document labels | Add a reviewed alias after ProductCode mapping is confirmed. |
| ChargeAlias | `handling` | Missing canonical seed data | Blocker for generic handling labels | Add only with scoped direction/mode rules, or leave for manual review if ambiguous. |
| ChargeAlias | `import handling` | Missing canonical seed data | Blocker for import handling labels | Add after `import_handling` ProductCode mapping exists. |
| ChargeAlias | `export handling` | Missing canonical seed data | Blocker for export handling labels | Add a reviewed alias to the confirmed export handling ProductCode. |
| ChargeAlias | `storage` | Missing canonical seed data | Blocker for storage labels | Add after `storage_warehouse` ProductCode mapping exists. |
| ProductCodes | Air Freight has multiple possible ProductCodes | Duplicate/conflict | Blocker for automated mapping until direction/domain mapping is confirmed | Confirm canonical mapping for export, import, and domestic air freight. |
| ProductCodes | Fuel surcharge has multiple possible ProductCodes | Duplicate/conflict | Blocker for automated mapping until charge scope is confirmed | Confirm whether pickup/cartage fuel codes are separate from main air freight fuel surcharge. |
| ProductCodes | Security surcharge has multiple possible ProductCodes | Duplicate/conflict | Blocker for automated mapping until security vs screening semantics are confirmed | Confirm canonical security/screening ProductCode mapping by direction. |
| ProductCodes | AWB / documentation has multiple possible ProductCodes | Duplicate/conflict | Blocker for automated mapping until AWB and documentation semantics are confirmed | Decide whether AWB and documentation remain separate codes or share aliases by scope. |
| ProductCodes | Customs pass-through has multiple possible ProductCodes | Duplicate/conflict | Blocker where customs pass-through charges appear in pilot replies | Confirm export/import/origin/destination customs mapping. |
| ChargeAlias | `air freight` maps to multiple ProductCodes | Duplicate/conflict | Blocker unless scoped aliases are intended and deterministic | Review existing scope fields before adding or changing aliases. |
| ChargeAlias | `documentation fee` maps to multiple ProductCodes | Duplicate/conflict | Blocker unless scoped aliases are intended and deterministic | Review existing scope fields before adding or changing aliases. |
| ChargeAlias | `terminal fee` maps to multiple ProductCodes | Duplicate/conflict | Blocker unless scoped aliases are intended and deterministic | Review existing scope fields before adding or changing aliases. |
| Locations | `LAX` location exists without airport-backed match | Harmless warning | Non-blocking unless pilot validation requires an Airport row for LAX | Leave as-is for Phase 13.1C; review in Phase 13.1D only if airport-backed validation is required. |
| Pilot data | No obvious pilot/demo company records | Harmless warning | Non-blocking for reference-data readiness | Keep anonymized pilot customer/supplier pack separate from reference-data seeding. |

Blocker list before Air Freight pilot UAT:

- ProductCode coverage is missing for `import_handling`, `storage_warehouse`, and `misc_recoveries`.
- ChargeAlias coverage is missing for `freight`, `screening`, `awb`, `handling`, `import handling`, `export handling`, and `storage`.
- ProductCode conflicts must be resolved for Air Freight, Fuel surcharge, Security surcharge, AWB / documentation, and Customs pass-through before any seed apply command is added.
- ChargeAlias conflicts for `air freight`, `documentation fee`, and `terminal fee` must be reviewed against existing scope fields before new aliases are added.

Recommended Phase 13.1D scope:

1. Produce a reviewed canonical mapping table for each ambiguous ProductCode coverage bucket, including domain, direction, unit, and existing code reuse decision.
2. Add a dry-run-only seed plan first for missing ProductCodes and ChargeAliases; do not add write mode until the plan output is reviewed.
3. Use additive, idempotent logic only after approval. Never delete, truncate, overwrite, or reset staging/production-like data.
4. Scope ChargeAliases by current model fields such as mode and direction where needed; avoid broad generic aliases for ambiguous labels.
5. Keep pilot customers and suppliers in a separate anonymized data pack. Do not mix customer/supplier sample data with reference-data seeding.
6. Treat the LAX airport-backed gap as optional unless the pilot workflow requires an Airport row instead of Location-only coverage.

## 13. Phase 13.1D canonical mapping decisions

Phase 13.1D is a reviewed mapping table only. It does not add seed writes, migrations, frontend changes, production behavior changes, or database mutations.

Inspection sources:

- `python backend/manage.py air_freight_pilot_seed_audit --format json`
- `pricing_v4.ProductCode` fields: `id`, `code`, `description`, `domain`, `category`, `default_unit`
- `pricing_v4.ChargeAlias` scope fields: `match_type`, `mode_scope`, `direction_scope`, `product_code`, `is_active`
- `docs/spot-canonical-charge-architecture.md` for known `FSC` and `Handling` ambiguity

Canonical ProductCode decisions:

| Coverage bucket | Mode | Direction | Decision | ProductCode | Existing id | Rationale |
| --- | --- | --- | --- | --- | --- | --- |
| Air Freight | EXPORT | MAIN | Reuse | `EXP-FRT-AIR` | `1001` | Existing export main air freight code. |
| Air Freight | IMPORT | MAIN | Reuse | `IMP-FRT-AIR` | `2001` | Existing import main air freight code. |
| Air Freight | DOMESTIC | MAIN | Reuse | `DOM-FRT-AIR` | `3001` | Existing domestic main air freight code. |
| Fuel surcharge | EXPORT | MAIN | Reuse | `EXP-FSC-AIR` | `1002` | Airline fuel surcharge for export air freight. |
| Fuel surcharge | EXPORT | ORIGIN | Reuse | `EXP-FSC-PICKUP` | `1060` | Pickup/cartage fuel is separate from airline fuel. |
| Fuel surcharge | IMPORT | ORIGIN | Reuse | `IMP-FSC-PICKUP` | `2060` | Existing import origin pickup fuel surcharge. |
| Fuel surcharge | IMPORT | DESTINATION | Reuse | `IMP-FSC-CARTAGE-DEST` | `2080` | Existing import destination cartage fuel surcharge. |
| Fuel surcharge | DOMESTIC | MAIN | Reuse | `DOM-FSC` | `3030` | Existing domestic fuel surcharge. |
| Security surcharge / screening | EXPORT | ORIGIN | Reuse | `EXP-SCREEN` | `1040` | Existing export screening code covers security screening. |
| Security surcharge / screening | IMPORT | ORIGIN | Reuse | `IMP-SEC-ORIGIN` | `2041` | Existing import origin airport security fee. |
| Security surcharge / screening | DOMESTIC | ORIGIN | Reuse | `DOM-SECURITY` | `3020` | Existing domestic security surcharge. |
| AWB | EXPORT | ORIGIN | Reuse | `EXP-AWB` | `1011` | Existing export AWB fee. |
| Documentation | EXPORT | ORIGIN | Reuse | `EXP-DOC` | `1010` | Existing export documentation fee. |
| AWB | IMPORT | ORIGIN | Reuse | `IMP-AWB-ORIGIN` | `2011` | Existing import origin AWB fee. |
| Documentation | IMPORT | ORIGIN | Reuse | `IMP-DOC-ORIGIN` | `2010` | Existing import origin documentation fee. |
| Documentation | IMPORT | DESTINATION | Reuse | `IMP-DOC-DEST` | `2022` | Existing import destination documentation fee. |
| AWB | DOMESTIC | ORIGIN | Reuse | `DOM-AWB` | `3012` | Existing domestic AWB fee. |
| Documentation | DOMESTIC | ORIGIN | Reuse | `DOM-DOC` | `3010` | Existing domestic documentation fee. |
| Customs pass-through | EXPORT | ORIGIN | Reuse | `EXP-CLEAR` | `1020` | Existing export customs clearance. |
| Customs pass-through | EXPORT | DESTINATION | Reuse | `EXP-CLEAR-DEST` | `1080` | Existing destination clearance for export flow. |
| Customs pass-through | IMPORT | ORIGIN | Reuse | `IMP-CUS-CLR-ORIGIN` | `2002` | Existing import origin customs clearance. |
| Customs pass-through | IMPORT | DESTINATION | Reuse | `IMP-CLEAR` | `2020` | Existing import destination customs clearance. |
| Export handling | EXPORT | ORIGIN | Reuse | `EXP-HANDLE` | `1032` | Existing export handling fee. |
| Import handling | IMPORT | DESTINATION | Create | `IMP-HANDLE-DEST` | TBD | No import handling ProductCode exists in audit output. |
| Storage / warehouse | IMPORT | DESTINATION | Create | `IMP-STORAGE-DEST` | TBD | No storage/warehouse ProductCode exists; pilot storage is expected to be destination/local unless business says otherwise. |
| Miscellaneous recoveries | ANY | ANY | Do not create broad code yet | TBD | TBD | Generic recoveries are too ambiguous for automatic quote mapping without business classification. |

ChargeAlias mapping decisions:

| Raw label | Match type | Mode scope | Direction scope | Decision | Target ProductCode | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| `air freight` | EXACT | EXPORT | MAIN | Keep existing | `EXP-FRT-AIR` | Existing alias id `1`; not a conflict when scoped by mode/direction. |
| `air freight` | EXACT | IMPORT | MAIN | Keep existing | `IMP-FRT-AIR` | Existing alias id `16`; not a conflict when scoped by mode/direction. |
| `air freight` | EXACT | DOMESTIC | MAIN | Keep existing | `DOM-FRT-AIR` | Existing alias id `33`; not a conflict when scoped by mode/direction. |
| `freight` | EXACT | EXPORT | MAIN | Create scoped alias | `EXP-FRT-AIR` | Missing common supplier label. |
| `freight` | EXACT | IMPORT | MAIN | Create scoped alias | `IMP-FRT-AIR` | Missing common supplier label. |
| `freight` | EXACT | DOMESTIC | MAIN | Create scoped alias | `DOM-FRT-AIR` | Missing common supplier label. |
| `fsc` | EXACT | ANY | ANY | Do not add more broad aliases | Existing `IMP-FSC-PICKUP` alias must be reviewed | Existing alias id `68` maps broad `fsc` to import pickup fuel and is unsafe for export/domestic contexts. |
| `fuel surcharge` | EXACT | EXPORT | MAIN | Create scoped alias | `EXP-FSC-AIR` | Needed to avoid using pickup/cartage fuel for airline fuel. |
| `fuel surcharge` | EXACT | IMPORT | ORIGIN | Create scoped alias | `IMP-FSC-PICKUP` | Only if pilot imports use this phrase for origin pickup fuel. |
| `fuel surcharge` | EXACT | IMPORT | DESTINATION | Create scoped alias | `IMP-FSC-CARTAGE-DEST` | Only if pilot imports use this phrase for destination cartage fuel. |
| `fuel surcharge` | EXACT | DOMESTIC | MAIN | Review existing | `DOM-FSC` | Existing alias id `40` is DOMESTIC/ORIGIN; confirm whether MAIN is required. |
| `security surcharge` | EXACT | EXPORT | ORIGIN | Create scoped alias | `EXP-SCREEN` | Existing coverage is ProductCode-only; alias is missing for export. |
| `security surcharge` | EXACT | IMPORT | ORIGIN | Create scoped alias | `IMP-SEC-ORIGIN` | Existing coverage is ProductCode-only; alias is missing for import. |
| `security surcharge` | EXACT | DOMESTIC | ORIGIN | Keep existing | `DOM-SECURITY` | Existing alias id `39`. |
| `screening` | EXACT | EXPORT | ORIGIN | Create scoped alias | `EXP-SCREEN` | Missing common supplier label. |
| `screening` | EXACT | IMPORT | ORIGIN | Create scoped alias | `IMP-SEC-ORIGIN` | Use only for origin security screening. |
| `awb` | EXACT | EXPORT | ORIGIN | Create scoped alias | `EXP-AWB` | Missing common AWB label. |
| `awb` | EXACT | IMPORT | ORIGIN | Create scoped alias | `IMP-AWB-ORIGIN` | Missing common AWB label. |
| `awb` | EXACT | DOMESTIC | ORIGIN | Create scoped alias | `DOM-AWB` | Missing common AWB label. |
| `documentation fee` | EXACT | EXPORT | ORIGIN | Keep existing | `EXP-DOC` | Existing alias id `3`; scoped mapping is valid. |
| `documentation fee` | EXACT | IMPORT | ORIGIN | Keep existing | `IMP-DOC-ORIGIN` | Existing alias id `18`; scoped mapping is valid. |
| `documentation fee` | EXACT | IMPORT | DESTINATION | Keep existing | `IMP-DOC-DEST` | Existing alias id `28`; scoped mapping is valid. |
| `documentation fee` | EXACT | DOMESTIC | ORIGIN | Keep existing | `DOM-DOC` | Existing alias id `35`; scoped mapping is valid. |
| `terminal fee` | EXACT | EXPORT | ORIGIN | Keep existing | `EXP-TERM` | Existing alias id `8`; Phase 13.1D does not add terminal aliases. |
| `terminal fee` | EXACT | DOMESTIC | ORIGIN | Keep existing | `DOM-TERMINAL` | Existing alias id `37`; Phase 13.1D does not add terminal aliases. |
| `handling` | EXACT | EXPORT | ORIGIN | Create scoped alias only if business accepts generic handling | `EXP-HANDLE` | Generic label is ambiguous across origin/destination. |
| `handling` | EXACT | IMPORT | DESTINATION | Create scoped alias only after new ProductCode approval | `IMP-HANDLE-DEST` | Requires import handling ProductCode first. |
| `export handling` | EXACT | EXPORT | ORIGIN | Create scoped alias | `EXP-HANDLE` | Missing explicit export handling label. |
| `import handling` | EXACT | IMPORT | DESTINATION | Create scoped alias after new ProductCode approval | `IMP-HANDLE-DEST` | Requires import handling ProductCode first. |
| `storage` | EXACT | IMPORT | DESTINATION | Create scoped alias after new ProductCode approval | `IMP-STORAGE-DEST` | Do not create broad storage alias until scope is confirmed. |

Unresolved business questions:

1. Should import handling be destination-only for the pilot, or is an origin import handling ProductCode also required?
2. Should storage/warehouse be import destination-only, or should export origin and domestic storage codes be created too?
3. Should miscellaneous recoveries be a real ProductCode, or should miscellaneous labels remain manual-review-only until classified?
4. Should `fsc` broad `ANY/ANY -> IMP-FSC-PICKUP` be retired, narrowed, or left active for compatibility?
5. Should domestic `Fuel Surcharge` remain `DOMESTIC/ORIGIN`, or should Phase 13.1E propose a separate `DOMESTIC/MAIN` alias?
6. Should generic `handling` be seeded at all, or should only explicit `export handling` and `import handling` labels be accepted?

Recommended Phase 13.1E dry-run seed-plan scope:

1. Add a read-only dry-run plan command or report section that outputs the ProductCodes and ChargeAliases it would create, skip, or flag for manual review.
2. Include create candidates for `IMP-HANDLE-DEST` and `IMP-STORAGE-DEST` only after business confirms description, category, default unit, GST treatment, and GL codes.
3. Do not create a broad miscellaneous recovery ProductCode in the first dry-run plan; list it as `manual_review_required`.
4. Plan scoped aliases for `freight`, `fuel surcharge`, `security surcharge`, `screening`, `awb`, `export handling`, `import handling`, and `storage`.
5. Do not overwrite existing aliases. Report existing scoped aliases as `skip_existing`.
6. Report broad or ambiguous existing aliases, especially `fsc`, as `conflict_requires_review`.
7. Keep apply mode out of Phase 13.1E unless a later phase explicitly approves writes.

## 14. Phase 13.1F dry-run seed plan review

Phase 13.1F reran the merged dry-run seed plan from latest `main`. The command remained read-only: no apply mode, no database writes, no migrations, no frontend changes, and no ProductCode or ChargeAlias creation.

Commands run:

```bash
python backend/manage.py air_freight_pilot_seed_plan --format json
python backend/manage.py air_freight_pilot_seed_plan --format text
```

Reviewed plan status:

- Status: `blocked`
- ProductCode actions: create `2`, reuse `0`, conflict `0`
- ChargeAlias actions after hardening: create `14`, create after planned ProductCode `2`, skip `0`, blocked `0`, conflict `0`
- Blocked business decisions: `3`
- Warnings: `4`

Safety findings:

- The dry-run command is safe to keep as a prerequisite for future apply-mode work because it has no write path and no `--apply` flag.
- The plan correctly limits ProductCode create candidates to `IMP-HANDLE-DEST` and `IMP-STORAGE-DEST`.
- The plan does not create miscellaneous recoveries.
- The plan does not create broad ambiguous aliases such as generic `fsc` or generic `handling`.
- Phase 13.1F hardened alias planning so aliases targeting ProductCodes planned in the same dry-run are reported as `create_after_product_code`, not as false blocked items.
- GL values remain placeholders: `TBD-REV` and `TBD-COS` for both ProductCode candidates.

Remaining blockers before apply mode:

1. Replace placeholder GL revenue and cost codes for `IMP-HANDLE-DEST`.
2. Replace placeholder GL revenue and cost codes for `IMP-STORAGE-DEST`.
3. Confirm GST treatment and GST applicability for both import destination handling and import destination storage.
4. Keep `misc_recoveries` manual-review-only until specific commercial categories are approved.
5. Keep broad `fsc ANY/ANY` and generic `handling` out of apply scope unless business signs off a deterministic scoped mapping.

Recommended Phase 13.1G scope:

1. Add an apply-mode command only after GL and GST values are approved.
2. Keep dry-run as the default behavior and require an explicit `--apply` flag for writes.
3. Apply ProductCodes before dependent ChargeAliases in one transaction.
4. Refuse to apply if the current dry-run output has conflicts, blocked business decisions, placeholder GL codes, or validation errors.
5. Preserve existing ProductCodes and ChargeAliases; use additive creates only and skip existing scoped aliases.

## 15. Phase 13.1G apply-blocker decisions

Phase 13.1G is a docs-only decision record. No seed data was written, no apply mode was added, no migrations were added, no frontend files were changed, and no production command behavior was changed.

Final GL/GST decision table:

| Planned ProductCode | Description | Domain | Category | Unit | GST applicable | GST rate | GST treatment | Revenue GL | Cost GL | Decision |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-HANDLE-DEST` | Import Destination Handling | `IMPORT` | `HANDLING` | `SHIPMENT` | Yes | `0.1000` | `STANDARD` | `4400` | `5400` | Approved for guarded apply-mode planning. Use the existing handling/terminal GL pair. |
| `IMP-STORAGE-DEST` | Import Destination Storage / Warehouse | `IMPORT` | `HANDLING` | `SHIPMENT` | Yes | `0.1000` | `STANDARD` | `4400` | `5400` | Approved for guarded apply-mode planning. Treat pilot storage as destination handling/warehouse recovery, not as a miscellaneous recovery. |

Blocked business decision outcomes:

| Blocked item | Final decision | Phase 13.1H implication |
| --- | --- | --- |
| `misc_recoveries` | Do not seed in the Air Freight pilot apply scope. Keep miscellaneous recoveries as manual-review-only until specific recoverable categories and accounting treatment are approved. | Phase 13.1H must not create a miscellaneous ProductCode or alias. The audit may continue to report this as intentionally deferred. |
| `fsc ANY/ANY` | Do not create or update a broad `fsc` alias. Fuel surcharge aliases must remain direction and charge-scope specific because airline fuel, pickup fuel, cartage fuel, and domestic fuel are not interchangeable. | Phase 13.1H may apply only the scoped `fuel surcharge` mappings already approved by direction and scope. It must not add generic `fsc`. |
| Generic `handling` | Do not create a generic `handling` alias. Generic handling labels remain ambiguous across export origin handling, import destination handling, terminal, warehouse, and agent handling. | Phase 13.1H may apply explicit `export handling` and `import handling` aliases only. It must leave generic `handling` for manual review. |

Updated dry-run/apply readiness checklist:

| Gate | Status | Notes |
| --- | --- | --- |
| Dry-run remains default behavior | Ready | The existing seed-plan command has no apply path. |
| ProductCode create scope limited | Ready | Only `IMP-HANDLE-DEST` and `IMP-STORAGE-DEST` are approved create candidates. |
| Placeholder GL blockers resolved | Ready for next implementation | Final values are documented above. Phase 13.1H must encode these values before adding any write path. |
| GST treatment resolved | Ready for next implementation | Both planned ProductCodes use standard import GST treatment: `is_gst_applicable=True`, `gst_rate=0.1000`, `gst_treatment=STANDARD`. |
| Miscellaneous recoveries | Deferred | Intentionally excluded from apply mode. |
| Broad `fsc` alias | Deferred | Intentionally excluded from apply mode. |
| Generic `handling` alias | Deferred | Intentionally excluded from apply mode. |
| Conflict protection | Required for Phase 13.1H | Apply mode must refuse to run if ProductCode or ChargeAlias conflicts are present. |
| Placeholder protection | Required for Phase 13.1H | Apply mode must refuse to run if any planned GL field still starts with `TBD`. |
| Data mutation scope | Required for Phase 13.1H | Additive ProductCode and ChargeAlias creates only; no deletes, truncates, updates, resets, customer data, supplier data, migrations, or frontend changes. |

Recommendation for Phase 13.1H:

Phase 13.1H may add guarded apply mode only after the dry-run plan constants are updated to the approved GL/GST values in this section. The apply command should keep dry-run as the default, require an explicit `--apply`, run in a transaction, create ProductCodes before dependent ChargeAliases, skip exact existing records, and abort on conflicts, placeholder GL codes, or any non-deferred blocked decision.

## 16. Phase 13.1H guarded apply mode

Phase 13.1H adds an explicit apply path to the existing Air Freight pilot seed-plan command. Dry-run remains the default.

Usage:

```bash
python backend/manage.py air_freight_pilot_seed_plan --format json
python backend/manage.py air_freight_pilot_seed_plan --format text
python backend/manage.py air_freight_pilot_seed_plan --apply --format json
python backend/manage.py air_freight_pilot_seed_plan --apply --format text
```

Approved ProductCode values encoded for apply:

| ProductCode | GST applicable | GST rate | GST treatment | Revenue GL | Cost GL |
| --- | --- | --- | --- | --- | --- |
| `IMP-HANDLE-DEST` | Yes | `0.1000` | `STANDARD` | `4400` | `5400` |
| `IMP-STORAGE-DEST` | Yes | `0.1000` | `STANDARD` | `4400` | `5400` |

Apply safety rules:

- `--apply` is required for writes; without it the command only reports the plan.
- Apply uses one database transaction.
- ProductCodes are created before dependent ChargeAliases.
- Apply is additive only: it creates missing approved records and skips exact existing records.
- Apply never deletes, overwrites, deactivates, resets, or updates existing ProductCodes or ChargeAliases.
- Apply aborts before writing if conflicts, validation errors, placeholder GL codes, missing alias target ProductCodes, or in-scope blocked decisions are present.
- Deferred decisions remain out of apply scope: `misc_recoveries`, broad `fsc ANY/ANY`, and generic `handling`.

Expected Phase 13.1H apply scope:

| Object type | Create scope |
| --- | --- |
| ProductCodes | `IMP-HANDLE-DEST`, `IMP-STORAGE-DEST` |
| ChargeAliases | Approved scoped aliases only, including dependent `import handling` and `storage` after ProductCode creation |
| Excluded | Customer data, supplier data, miscellaneous recoveries, broad `fsc`, generic `handling`, migrations, frontend changes |
