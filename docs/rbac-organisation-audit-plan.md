# Organisation, Branch, Department, and Permission RBAC Audit Plan

Date: 2026-06-09

Current checkout audited:

- Branch: `main`
- Commit: `eb60a8d53b078bc103bfdf66dc47cb4b303a303d`
- Repository state before report creation: clean working tree
- Scope: audit and implementation plan only. No application code, migrations, seed data, permission behavior, or UI behavior were changed.

## 1. Current State Summary

RateEngine currently has partial tenant and role concepts, but it does not have a complete Organisation / Branch / Department / Permission RBAC model.

The active tenant-like model is `parties.Organization`. It is used today as a workspace and branding owner, not as a full hierarchy root with branch, department, role, and permission relationships. `accounts.CustomUser.organization` and `quotes.Quote.organization` point at it. Shipments are also scoped by organisation. Customers, CRM, rate cards, and most pricing data are not organisation-scoped.

The current user model has:

- `role`: one of `sales`, `manager`, `finance`, `admin`.
- `department`: nullable text choice limited to `AIR`, `SEA`, `LAND`.
- `organization`: nullable FK to `parties.Organization`.
- two visibility overrides: `can_view_buy_charges_override` and `can_view_margins_override`.

There is no current `Branch` model, no current `Department` model, no role table, no permission table, no user membership table, and no explicit branch or department ownership on quotes, SPOT envelopes, customers, CRM records, or rate cards.

The quote and SPOT access selectors in `backend/quotes/selectors.py` are the current security choke point for quote-like records:

- Admin and finance see all quotes and all SPOT envelopes.
- Managers see their own records and records created by users with the same current `CustomUser.department`.
- Sales users see their own records.

This is a creator-department selector, not branch or organisation RBAC. It also depends on the creator user's current department, not immutable quote-owned scope fields.

Sensitive charge visibility is not consistently protected by permission semantics. Backend `CustomUser.can_view_buy_charges` currently returns `True` for every authenticated role, and the frontend `VIEW_COGS` permission includes `sales`. That means quote serializers and UI checks that appear to mask buy costs for sales do not mask them in practice.

## 2. Existing Models and Tables Involved

### Accounts

- `accounts.CustomUser`
  - Existing fields: `role`, `department`, `organization`, `can_view_buy_charges_override`, `can_view_margins_override`.
  - Django `groups` and `user_permissions` exist through `AbstractUser`, but project-specific access checks use hardcoded role helper properties instead.
- `accounts.permissions`
  - DRF permissions are role based.
  - The file comment matrix says sales cannot view COGS/buy rates, but the active `CustomUser.can_view_cogs` path currently allows sales.
- `accounts.user_management.UserViewSet`
  - Manager/admin user management exists.
  - Current queryset is `CustomUser.objects.all()` and is not restricted by requester organisation.

### Organisation and parties

- `parties.Organization`
  - Active tenant/workspace and branding context.
  - Used by `/api/auth/me/` and public quote branding.
- `parties.OrganizationBranding`
  - One-to-one branding record.
- `parties.Company`, `parties.Contact`, address models, and customer commercial profile data
  - No organisation, branch, or department owner on current customer records.
  - Customer list/search/contact APIs are global to authenticated users.

### Quotes

- `quotes.Quote`
  - Has `organization`, `customer`, `contact`, `mode`, `shipment_type`, `service_scope`, route fields, `created_by`, lifecycle fields, and `request_details_json`.
  - Does not have branch, department, membership, owner, or permission scope fields.
- `quotes.QuoteVersion`, `QuoteLine`, `QuoteTotal`, `QuoteEvent`
  - Store historical payloads, charge lines, cost totals, sell totals, margin-relevant metadata, and lifecycle events.
  - These are workflow-critical and sensitive because quote history can expose buy cost, rate source, margin, audit metadata, and original request payloads.

### SPOT

- Active SPOT persistence is the SPE envelope model:
  - `SpotPricingEnvelopeDB`
  - `SPESourceBatchDB`
  - `SPEChargeLineDB`
  - `SPEAcknowledgementDB`
  - `SPEManagerApprovalDB`
- SPOT envelopes have `created_by` and optional `quote`.
- SPOT envelopes do not have organisation, branch, or department fields.
- Active API surface is `/api/v3/spot/analyze-reply/` and `/api/v3/spot/envelopes/*`.
- Legacy quote-scoped SPOT-rate CRUD must remain deprecated and must not be revived.

### Pricing and rates

V4 rate tables are in `pricing_v4` and include export, import, domestic, local, sell, and COGS records. They are currently scoped by lane/location/scope/counterparty/date concepts, not organisation or branch.

The rate-management APIs are mostly manager/admin only. That limits access by role, but it does not create branch or permission scoping.

### Shipments

- `shipments.Shipment`, `ShipmentAddressBookEntry`, `ShipmentTemplate`, and `ShipmentSettings` are organisation-scoped.
- `Shipment.branch` exists as a text field populated from origin code in a migration.
- Shipment APIs filter by `request.user.organization`, but they do not yet filter by branch membership.

### CRM

- `crm.Opportunity`, `Interaction`, and `Task` are not organisation, branch, or department scoped.
- Authenticated users can read all CRM records.
- Sales, manager, and admin roles can write CRM records.

## 3. Existing API Endpoints Affected

The following endpoints must be considered affected by a real RBAC implementation.

### Auth and user management

- `/api/auth/login/`
- `/api/auth/me/`
- `/api/auth/register/`
- `/api/auth/users/`
- `/api/auth/organizations/`

`/api/auth/me/` is the frontend source for role, organisation branding, and current buy/margin visibility flags. Any permission-model change must extend this response carefully and preserve existing frontend expectations during transition.

### Quotes

- `/api/v3/quotes/`
- `/api/v3/quotes/compute/`
- `/api/v3/quotes/<quote_id>/`
- `/api/v3/quotes/<quote_id>/versions/`
- `/api/v3/quotes/<quote_id>/transition/`
- `/api/v3/quotes/<quote_id>/clone/`
- `/api/v3/quotes/<quote_id>/pdf/`
- `/api/v3/quotes/public/`
- `/api/v3/reports/*`

These are quote-first and workflow-critical. Changes here must be phased behind central selectors and field masking tests before any UI filtering changes.

### SPOT

- `/api/v3/spot/validate-scope/`
- `/api/v3/spot/evaluate-trigger/`
- `/api/v3/spot/standard-charges/`
- `/api/v3/spot/analyze-reply/`
- `/api/v3/spot/envelopes/`
- `/api/v3/spot/envelopes/<id>/`
- `/api/v3/spot/envelopes/<id>/acknowledge/`
- `/api/v3/spot/envelopes/<id>/compute/`
- `/api/v3/spot/envelopes/<id>/create-quote/`
- `/api/v3/spot/envelopes/<id>/sources/<source_batch_id>/review/`
- `/api/v3/spot/envelopes/<id>/charges/<charge_line_id>/manual-resolution/`
- `/api/v3/spot/envelopes/<id>/charges/<charge_line_id>/conditional-resolution/`

SPOT must stay on the SPE envelope and V4 adapter path. Do not add new code against removed quote-scoped SPOT-rate CRUD.

### Customers and parties

- `/api/v3/customers/`
- `/api/v3/parties/search/`
- `/api/v3/parties/companies/search/`
- `/api/v3/parties/companies/<company_id>/contacts/`
- `/api/v3/branding/organization/`
- public branding logo routes

Customer search and contacts are currently global to authenticated users and are a likely data-leakage surface once branch scoping matters.

### Pricing and rate management

- `/api/v4/quote/calculate/`
- `/api/v4/quote/counterparty-hints/`
- `/api/v4/rates/*`
- `/api/v4/rates/upload/`
- `/api/v4/rate-cards/`
- `/api/v4/discounts/*`
- `/api/v4/product-codes/`
- `/api/v4/agents/`
- `/api/v4/carriers/`

The pricing engine itself should continue to be deterministic. RBAC should restrict who can read or manage rates and which scoped rate records they can touch. It should not change rate selection rules in the same PR.

### Shipments

- `/api/v3/shipments/`
- `/api/v3/shipments/address-book/`
- `/api/v3/shipments/templates/`
- `/api/v3/shipments/settings/`
- shipment document download and PDF actions

Shipments already have organisation scoping. Branch scoping can be introduced here later, but it must not be mixed into quote RBAC without an explicit workflow test plan.

### CRM

- `/api/v3/crm/opportunities/`
- `/api/v3/crm/interactions/`
- `/api/v3/crm/tasks/`

CRM quote logging is coupled to quote creation and SPOT create-quote. Do not break quote-derived CRM logging while introducing CRM visibility filters.

## 4. Frontend Areas Affected

The frontend currently treats role and `/api/auth/me/` visibility booleans as the source for UI affordances. This is UX gating only and must not become the security source of truth.

Affected areas include:

- `frontend/src/context/auth-context.tsx`
  - Stores the `User` object from `/api/auth/me/` in local storage and refreshes it on load.
- `frontend/src/lib/types.ts`
  - Current `User.permissions` only supports `can_view_buy_charges` and `can_view_margins`.
- `frontend/src/lib/permissions.ts`
  - Hardcoded role permission matrix.
  - Sales currently has `VIEW_COGS`.
- `frontend/src/hooks/usePermissions.ts`
  - Uses backend booleans when present, otherwise falls back to role matrix.
- `frontend/src/components/app-sidebar.tsx`
  - Navigation is role gated, not permission scoped.
- Quote workflow screens:
  - quote list
  - quote create/edit/detail
  - SPOT rate-entry page
  - quote PDF/public quote paths
  - charge cards and pricing breakdown components
- Management reporting pages:
  - revenue, cost, GP, margin, user performance, dashboard metrics
- Customer and CRM pages:
  - customer directory/search/contact picker
  - CRM opportunities/interactions/tasks
- Pricing/rate-management pages:
  - rates, logical rate cards, FX/rate tooling
- Shipment pages:
  - shipment list/detail/address book/templates/settings

Frontend implementation should come after backend permissions and selectors exist. UI hiding alone is not sufficient.

## 5. Current Leakage and Overreach Risks

### Buy cost and margin-adjacent leakage

Sales users currently can view buy costs because:

- Backend `CustomUser.can_view_buy_charges` returns true for all authenticated roles.
- `CustomUser.can_view_cogs` aliases that helper.
- `V3QuoteLineSerializer` and `V3QuoteTotalSerializer` only mask cost fields if `can_view_cogs` is false.
- Frontend `VIEW_COGS` includes sales and `usePermissions()` trusts `/api/auth/me/` buy-charge booleans.

The code comments in `accounts.permissions` say sales should not view COGS, so the current behavior and stated policy are inconsistent.

### Quote result and compute payload leakage

Quote detail and compute paths can return cost fields through:

- persisted `QuoteLine` and `QuoteTotal` serializers,
- canonical quote result payloads,
- compatibility compute endpoints that build response lines containing `cost_pgk`,
- `request_details_json` and latest quote version payloads.

Before permission behavior changes, tests must prove that sales users without buy-cost permission cannot retrieve cost fields through list, detail, version, compute, recompute, export, PDF, or reporting paths.

### SPOT cost leakage

SPOT compute returns line `cost_pgk`, source, and total cost. SPE charge lines are inherently buy-side source data. Access currently follows `get_spes_for_user`, which is creator-department/global role based. It is not organisation/branch scoped, and the response does not implement separate buy-cost masking.

### Customer and contact leakage

All authenticated users can read active customers, search parties, and list contacts for a company. Current `Company` and `Contact` records have no organisation or branch ownership field, so branch RBAC cannot be enforced without a schema and backfill step.

### CRM leakage

CRM opportunities, interactions, and tasks are globally readable to authenticated users. This is incompatible with branch or department-specific commercial visibility unless CRM gets scope fields and selectors.

### User management overreach

Manager/admin user management lists `CustomUser.objects.all()` and the organisation list endpoint returns all organisations to managers/admins. This is too broad if managers should only manage users in their own organisation, branch, or department.

### Reporting leakage

Reporting endpoints use quote selectors for quote access, which is good, but they aggregate cost, GP, and margin data. Under current selectors, finance/admin get global data and managers get creator-department data. There is no branch filter or permission-specific financial masking.

### Shipment branch gap

Shipments are organisation-scoped, but `Shipment.branch` is a text field and not used as an access boundary.

## 6. Migration Risks

The local `backend/db.sqlite3` snapshot contains:

- 3 organisations: `efm-express-air-cargo`, `efm`, and `test-org`.
- 17 users.
- 57 quotes, all under `efm-express-air-cargo`.
- 55 SPOT envelopes.
- 235 companies and 297 contacts.
- 4 shipments, all under `efm-express-air-cargo` with branch `POM`.
- 66 CRM opportunities.
- Some users have no organisation.
- Some users are already under `test-org`, but no current quotes or shipments are under `test-org`.

This means an RBAC migration cannot assume a single clean production organisation or that every user has a valid organisation. It also cannot move users, quotes, shipments, or customers across organisations without an explicit data migration plan and manual approval.

Specific risks:

- Backfilling branch or department from `CustomUser.department` is lossy because the quote's historical creator department can change.
- Branch data does not exist for quotes, SPOT, customers, CRM, or rate cards.
- Existing shipment `branch` values are text and look like origin station codes, not branch records.
- Public quote branding relies on `Quote.organization`.
- User organisation drives `/api/auth/me/` branding and shipment scoping.
- Adding non-null constraints too early will break existing rows with missing scope.
- Renaming `Organization` to `Organisation` in code would create churn without solving RBAC. Keep the current model name unless there is a product-level reason to rename it.
- Rate tables contain deterministic pricing inputs. Adding organisation or branch ownership to rates should be additive first and must not alter deterministic selection order in the same change.

## 7. Target Data Model

Recommended target model, introduced additively:

- `Organization`
  - Keep existing model as the tenant/workspace and branding owner.
  - UI can use "Organisation" wording without renaming the Django model.
- `Branch`
  - FK to `Organization`.
  - Stable code, name, active flag.
  - Optional address and operational metadata later.
- `Department`
  - FK to `Organization`.
  - Optional FK to `Branch` if departments are branch-local.
  - Stable code such as `AIR`, `SEA`, `LAND`, `FINANCE`, `ADMIN`.
  - Active flag.
- `Permission`
  - Stable code, description, active flag.
  - Examples: `quote.view.own`, `quote.view.department`, `quote.view.branch`, `quote.create`, `quote.edit`, `quote.finalize`, `quote.view.buy_cost`, `quote.view.margin`, `spot.create`, `spot.review`, `rate.view.sell`, `rate.view.buy`, `rate.edit`, `customer.view.branch`, `crm.view.branch`, `report.view.financials`, `user.manage.branch`.
- `Role`
  - FK to `Organization` or global template flag.
  - Name and active flag.
- `RolePermission`
  - FK role to permission.
- `UserMembership`
  - FK user, organization, branch nullable, department nullable, role.
  - Primary membership flag.
  - Active flag.
  - This supports users in multiple branches/departments without overloading `CustomUser.department`.

Add scope fields only after these foundations exist:

- `Quote.organization`, existing.
- `Quote.branch`, nullable FK.
- `Quote.department`, nullable FK.
- `Quote.owner`, optional FK or use `created_by` until ownership semantics are defined.
- `SpotPricingEnvelopeDB.organization`, nullable FK.
- `SpotPricingEnvelopeDB.branch`, nullable FK.
- `SpotPricingEnvelopeDB.department`, nullable FK.
- `Company.organization`, nullable FK or many-to-many if shared customers are real.
- `Company.branch`, nullable FK or a company access table if customers can span branches.
- CRM opportunity/interactions/tasks organisation, branch, department, and owner fields.
- Rate table organisation/branch scope only when the business rule is explicit. Until then, keep global rates global.

Do not make these fields non-null until data has been backfilled and read paths have proven stable.

## 8. Target Permission Model

Backend permission checks should become code-based and data-scoped.

The security source of truth should be centralized in backend services/selectors, for example:

- `accounts.rbac.permissions` for resolving a user's effective permission codes.
- `accounts.rbac.scope` for resolving accessible organisation, branch, and department IDs.
- quote selectors for quote/SPE access.
- customer selectors for company/contact access.
- CRM selectors for opportunity/interaction/task access.
- rate selectors for rate-card access.
- serializer masking helpers for sensitive fields.

Permissions should answer two separate questions:

1. Can the user perform this action?
2. Which records and fields can the user access?

Suggested permission categories:

- Quote workflow:
  - create, view own, view department, view branch, edit draft, recompute, finalize, transition, clone, export PDF.
- SPOT workflow:
  - create envelope, analyze reply, review source batches, resolve charge exceptions, acknowledge, compute, create quote.
- Financial visibility:
  - view sell charges.
  - view buy charges.
  - view margin.
  - view rate source/audit metadata.
- Customer:
  - view customer, create customer, edit customer, view contact.
- CRM:
  - view, create, edit, close, view interactions, manage tasks.
- Rate management:
  - view sell rates, view buy rates, edit rates, upload rates, manage aliases/product codes.
- Reporting:
  - view own metrics, view branch metrics, view organisation financials, export reports.
- User administration:
  - view users, create users, assign roles, manage branch memberships.

Frontend should receive an effective permission list and scope summary from `/api/auth/me/`, but frontend checks must remain UX-only.

## 9. Phased Implementation Plan

### Phase 0: Audit baseline

Status: completed by this report.

Keep this phase read-only except for the report document. Record Fallow baseline, graph context, current selector behavior, and DB snapshot.

### Phase 1: Schema-only RBAC foundation

Add `Branch`, `Department`, `Permission`, `Role`, `RolePermission`, and `UserMembership` models.

Seed default roles and permissions that mirror current behavior as closely as possible. Do not change quote, SPOT, customer, CRM, shipment, or rate visibility in this phase.

Add admin registration for the new models if useful for inspection.

Tests:

- Migrations apply cleanly.
- Default permissions are seeded idempotently.
- Existing users can still log in.
- `/api/auth/me/` remains backward compatible.

### Phase 2: User membership backfill

Create a data migration or management command that assigns each user a primary membership from existing `CustomUser.organization` and `CustomUser.department`.

Users with null organisation must be reported and assigned only through an approved data decision.

Do not remove `CustomUser.role` or `CustomUser.department` yet. Keep them as compatibility fields while new memberships are proven.

Tests:

- Every active user has either a valid membership or appears in an explicit exception report.
- Existing role helper behavior is unchanged.

### Phase 3: Add nullable scope fields to business records

Add nullable branch and department FKs to quote and SPE records first. Then add customer, CRM, shipment, and rate-card scope fields in separate PRs.

Backfill quote and SPE scope conservatively:

- Prefer immutable record fields where they exist.
- If falling back to creator membership, record that source in audit metadata or a migration report.
- Do not infer branch from shipment route unless the business confirms that station code equals branch.

Tests:

- Existing quote list/detail/compute/recompute/version flows still pass.
- Existing SPOT draft, analyze, compute, and create-quote flows still pass.
- Public quote rendering and branding are unchanged.

### Phase 4: Central backend RBAC services and selectors

Introduce effective-permission and effective-scope services.

Update quote and SPE selectors to support new scope logic, but keep behavior equivalent until a feature flag or explicit migration cutover enables branch filtering.

Add serializer masking helpers that do not depend on frontend state.

Tests:

- Sales without buy-cost permission cannot retrieve buy cost through quote list/detail/version/compute/SPOT/report responses.
- Users cannot access quote or SPE detail URLs outside allowed scope.
- Managers see only records allowed by explicit membership scope.
- Finance/admin behavior is explicit and tested.

#### Initial scope foundation helper PR

The first implementation PR for this phase adds central helper functions and
tests only. It does not enforce new row-level filtering for quotes, SPOT,
customers, CRM, shipments, reports, pricing, or rate management.

Current model commitments for this PR:

- `accounts.UserMembership` is the target membership model. Do not create a
  parallel `UserOrgMembership` model.
- `parties.Organization` remains the tenant/workspace root and branding owner.
  Do not rename it to `Organisation` in code.
- `parties.Company` remains for external parties such as customers, suppliers,
  agents, and carriers. It must not be reused for internal legal entities.
- `LegalEntity` and `BranchDepartment` are deferred until the business
  structure and migration rules are confirmed.

Compatibility rules for the helper layer:

- Prefer active `UserMembership` rows when they exist.
- Fall back to `CustomUser.role`, `CustomUser.department`, and
  `CustomUser.organization` only when no active membership exists.
- Treat null branch or department memberships as organization-wide only for
  roles or permissions that already represent organization-wide access. Normal
  sales or manager memberships need explicit branch and department membership
  before branch-aware enforcement begins.
- Deny anonymous or inactive users, and avoid global access for ordinary users.

#### Selector visibility regression test PR

The next small PR adds read-only regression tests for current quote and SPE
visibility. It does not change selectors, serializers, permissions, schema, or
business visibility.

Current legacy selector behavior captured by tests:

- Quote and SPE list/detail access uses `quotes.selectors.get_quotes_for_user`,
  `get_quote_for_user`, and `get_spes_for_user`.
- Admin and finance users see broadly.
- Managers see their own records and records created by users with the same
  legacy `CustomUser.department`.
- Managers without a legacy department fall back to own records only.
- Sales users see own records only.
- Anonymous users are denied by selectors or DRF authentication.
- Inactive users are not denied by the legacy selector layer if they are already
  treated as authenticated. This is a known compatibility/security risk to fix
  during the permission-service cutover, not in the regression-test PR.

Known mismatch documented for cutover:

- Current quote and SPE selectors ignore `UserMembership` entirely.
- The new `accounts.scope` helper can derive a different branch or department
  from active membership than `CustomUser.department`.
- Until selector cutover, legacy selector behavior remains authoritative for
  quote, SPE, and report visibility.

Report inheritance:

- Reporting endpoints that call `get_quotes_for_user` inherit the same legacy
  quote selector scope. Regression tests should pin this rather than duplicate
  report-specific RBAC logic.

#### Selector scope comparison harness PR

The selector comparison harness is for tests and migration planning only. It
compares current legacy selector results with membership-derived scope results
without changing runtime enforcement.

Rules for this PR:

- Legacy selectors remain authoritative for quote, SPE, and report visibility
  until an explicit cutover PR changes them.
- Comparison results must not be used by production API views, serializers, or
  services.
- The harness may report mismatches where active `UserMembership.department`
  differs from legacy `CustomUser.department`.
- Active users with no active memberships should compare equal to legacy
  behavior because `accounts.scope` intentionally falls back to legacy fields.
- Anonymous users should compare as denied on both sides.
- Inactive users are a known compatibility mismatch: legacy selectors may still
  return own records if the user is already treated as authenticated, while the
  scope helper denies inactive users.
- No enforcement, schema, migration, customer, CRM, shipment, pricing, report,
  rate, buy-cost, or margin behavior changes are made by the comparison harness.

#### Visibility diagnostics command PR

Add a read-only management command for comparing real-data quote and SPE
visibility before selector cutover:

```bash
python backend/manage.py rbac_compare_visibility
python backend/manage.py rbac_compare_visibility --format json --show-details
python backend/manage.py rbac_compare_visibility --user USERNAME_OR_ID
```

The command is a pre-cutover diagnostic tool only. It reports, per user, current
legacy selector visibility, membership-derived expected visibility, matching
record counts, legacy-only counts, membership-only counts, and mismatch flags.
Record ID lists are omitted by default and shown only with `--show-details`.

Rules for the diagnostics command:

- Legacy selectors remain authoritative until a later explicit enforcement PR.
- The command must not write to the database or modify users, memberships,
  quotes, SPEs, reports, pricing, or rates.
- Mismatch output should be used to clean `UserMembership` data before changing
  production selectors.
- A common expected mismatch is active `UserMembership.department` differing
  from legacy `CustomUser.department`.
- Inactive users are excluded by default and included only with
  `--include-inactive`.
- This diagnostic PR does not change access behavior, buy-cost visibility,
  margin visibility, schema, migrations, or frontend behavior.

Suggested next step after diagnostics:

- Run the command against non-production and production snapshots, review
  mismatch counts by user, and prepare a data-cleanup/backfill PR before any
  selector cutover.

#### Nullable Quote and SPE scope field PR

Add nullable future-RBAC scope fields to `Quote` and `SpotPricingEnvelopeDB`
without changing selector behavior:

- `Quote.branch`
- `Quote.department`
- `Quote.owner`
- `SpotPricingEnvelopeDB.organization`
- `SpotPricingEnvelopeDB.branch`
- `SpotPricingEnvelopeDB.department`
- `SpotPricingEnvelopeDB.owner`

These fields exist for future backfill and enforcement only. Current quote and
SPE selectors remain legacy-authoritative until an explicit selector cutover PR.
The fields must remain nullable until production data is audited and safely
backfilled.

Add a dry-run-only command:

```bash
python backend/manage.py rbac_scope_backfill_report
python backend/manage.py rbac_scope_backfill_report --format json --show-details
```

The command reports possible backfill candidates and must not write to the
database. Safe candidate sources are limited to existing record fields and the
creator user's explicit RBAC data:

- Existing `Quote.organization`.
- Exactly one active `UserMembership` on `created_by`.
- Legacy `CustomUser.organization` or `CustomUser.department`, reported
  separately as fallback only.

The command must not infer branch or department from route, origin,
destination, station code, mode, customer, shipment lane, or pricing lane.

With `--show-details`, unknown Quote and SPE rows include only safe inspection
fields: model, id, reference, created_by id/username, created_at, and reason
such as `no_created_by` or `no_membership`. Use this to decide whether unknown
SPOT rows need a valid creator, manual scope, legacy exemption, or exclusion
from hard-cutover requirements.

For hard-cutover planning, the report also includes read-only readiness counts:
total records, scoped records, unscoped records, unscoped ready records,
unscoped draft records, unscoped records created by test/dev users, unscoped
records with no creator, ambiguous records, and `hard_cutover_ready`.
Use `--show-problems` to list only rows that still depend on cleanup or legacy
fallback before removing compatibility behavior.

This PR does not change access behavior, buy-cost visibility, margin visibility,
frontend behavior, selectors, customer access, CRM, shipments, reports, pricing,
or rates.

Suggested next step after nullable fields:

- Run the dry-run report against production-like data, review ambiguous and
  unknown rows, then prepare a non-destructive data cleanup/backfill plan before
  enabling any scope-based selectors.

#### Create-time Quote and SPE scope assignment PR

Populate nullable RBAC scope fields on newly created `Quote` and
`SpotPricingEnvelopeDB` records only. Existing rows are not changed and no data
migration is added.

Create-time rules:

- Anonymous or inactive users do not assign scope.
- Exactly one active `UserMembership` assigns organization, branch, department,
  and owner from that membership.
- Multiple active memberships assign only values all memberships agree on.
  Ambiguous branch or department values remain null.
- Users with no active memberships assign legacy `CustomUser.organization` and
  owner only.
- Legacy `CustomUser.department` text is not mapped to `parties.Department`.
- Explicitly supplied scope values are never overwritten.

The create-time assignment must not infer branch or department from route,
origin, destination, station code, lane, mode, customer, shipment data, or
pricing data.

This PR does not change quote or SPE visibility, selectors, buy-cost visibility,
margin visibility, customer access, CRM, shipments, reports, pricing, rates, or
frontend behavior.

#### Controlled Quote and SPE scope backfill command PR

Add a write-capable command for old unscoped `Quote` and `SpotPricingEnvelopeDB`
rows:

```bash
python backend/manage.py rbac_scope_backfill
python backend/manage.py rbac_scope_backfill --write --model quote
python backend/manage.py rbac_scope_backfill --format json --show-details
```

The default mode is dry-run/read-only. Database writes require explicit
`--write`.

Write rules:

- Only records whose `created_by` has exactly one active `UserMembership` are
  safe candidates.
- Fill missing fields only.
- `Quote`: fill missing organization, branch, department, and owner.
- `SpotPricingEnvelopeDB`: fill missing organization, branch, department, and
  owner.
- Existing non-null scope values are never overwritten.
- Ambiguous memberships, missing memberships, missing creators, inactive
  creators, and unresolved scope remain for manual cleanup.

The command must not infer branch or department from route, lane, origin,
destination, station code, mode, customer, shipment data, or pricing data.

This PR does not change selectors, access enforcement, buy-cost visibility,
margin visibility, customer access, CRM, shipments, reports, pricing, rates, or
frontend behavior.

Suggested next step after controlled backfill:

- Run diagnostics and dry-run backfill on development or staging data, review
  skipped rows, run `--write` only after approval, then prepare a separate
  selector cutover plan.

#### Transitional Quote and SPE scoped selector PR

Update only `Quote` and `SpotPricingEnvelopeDB` selectors so manager visibility
prefers durable scope fields where those fields exist:

- Scoped records with `branch` or `department` use the record-owned scope fields,
  not the creator user's current legacy department.
- Branch/department-unscoped records keep the existing legacy fallback: own
  records plus records created by users in the same legacy
  `CustomUser.department`.
- Admin, finance, and superuser broad visibility remains unchanged.
- Sales visibility remains own-records-only.
- Anonymous users remain denied by selectors/DRF authentication.

This is a transitional selector mode, not the final RBAC hard cutover. It keeps
old unscoped Quote and SPE rows visible through the documented compatibility
fallback while allowing backfilled and newly created scoped rows to stop moving
when a creator's legacy department changes.

This PR must not change customer access, CRM, shipments, reports, pricing,
rates, buy-cost visibility, margin visibility, ProductCode flows, frontend
behavior, create-time assignment, or backfill commands.

Suggested next step after transitional selectors:

- Run visibility diagnostics again against development/staging data, clean or
  manually scope any remaining unscoped rows, then prepare a later PR to remove
  the legacy fallback only after data cleanup is complete.

#### Customer, CRM, Shipment, and Reports RBAC visibility audit

Date: 2026-06-19

Branch: `audit/rbac-customer-crm-report-scope`

Scope: read-only audit of customer/company/contact, CRM, shipment, and report
visibility after the Quote/SPOT transitional selector work. No runtime code,
schema, migrations, selector logic, pricing, ProductCode, buy-cost, margin,
frontend behavior, or business visibility was changed.

Current Quote/SPOT context carried into this audit:

- Quote: 60/60 scoped, `hard_cutover_ready=true`.
- SPOT: 62/70 scoped, `hard_cutover_ready=false`.
- 8 SPOT records remain unscoped: 4 ready records created by `testuser` with no
  membership and 4 draft records with no `created_by`.
- `rbac_compare_visibility` reports 0 mismatches.
- Quote and SPE selectors now prefer durable scope fields and retain legacy
  fallback. Hard cutover remains intentionally deferred.

Fallow baseline for this audit:

- `npx fallow --format json`: exit 0, Fallow 2.88.3, 99 total issues.
- `npx fallow dead-code --format json`: exit 1 with valid findings JSON, 99
  total issues including 1 unused file, 79 unused exports, 17 unused types, and
  1 unused dev dependency.
- `npx fallow dupes --format json`: exit 0, 224 files scanned, 57 files with
  clones, 20 clone groups, 4,883 duplicated lines, 10.780677352408707 percent
  duplication.
- `npx fallow health --format json`: exit 1 with valid findings JSON. Relevant
  hotspots include customer edit UI, CRM opportunity UI, shipment detail UI, and
  dashboard/reporting UI. These are audit evidence only and were not cleaned up.

Observed visibility by domain:

- Customers, companies, and contacts are effectively authenticated-global reads.
  `Company` and `Contact` have no organization, branch, department, or durable
  owner scope fields. `Company.account_owner` exists but is not used for access
  filtering. Customer writes are admin-only through `CustomerAccessPermission`.
- Customer list and search use global active customer querysets. The contact
  endpoint performs `get_object_or_404(Company, pk=company_id)` and then returns
  active contacts for that company, so direct company ID lookup is not scoped.
- CRM opportunities, interactions, and tasks are authenticated-global reads.
  Sales, manager, and admin can write. Opportunities and tasks have `owner`
  fields, interactions have `author`, but no CRM view filters by the current
  user's owner, organization, branch, or department unless the client supplies a
  query parameter.
- CRM direct object access inherits the same global queryset. A user who knows
  an opportunity, interaction, task, owner, or company ID can request it unless
  blocked by authentication or write-role checks.
- Shipments are organization-scoped in the primary viewsets through
  `request.user.organization`: shipment list/detail/actions, address book,
  templates, settings, and document download all filter through the user's
  organization or a shipment already filtered by organization.
- Shipment branch is a text field, not an FK to `parties.Branch`, and is not an
  access boundary. Shipment role checks still use legacy `request.user.role`.
- Shipment serializers use global related-object querysets for customer
  company/contact links and locations. This does not bypass shipment object
  scoping, but it can attach globally visible customer/contact records into an
  organization-scoped shipment address book entry.
- New reporting endpoints generally call `get_quotes_for_user`, so they inherit
  the transitional Quote selector: durable scope fields first, legacy fallback
  for unscoped records, broad admin/finance visibility, manager branch or
  department visibility where scoped, and sales own-record visibility where
  allowed by endpoint permissions.
- Report endpoint permissions are still role-based via
  `IsManagerOrAdmin | IsFinanceOrAdmin`. They do not use permission codes such
  as `report.view.financials`.
- Report outputs expose cost, gross profit, and margin metrics to permitted
  report roles. There is no separate financial-field masking in the reporting
  layer yet.
- Legacy `dashboard` reporting now uses the scoped quote queryset for
  `conversion` totals. This fixes the previously audited global
  `Quote.objects.exclude(is_archived=True)` aggregate while preserving response
  shape and field names.

Global access risks:

- Customer/company/contact reads are global for every authenticated user.
- CRM reads and direct ID access are global for every authenticated user.
- CRM owner/company query parameters allow authenticated users to enumerate
  another owner or company's CRM data.
- Reporting financial outputs are role-gated but not permission-code gated, and
  do not mask financial fields independently of endpoint access.
- Reports should continue to derive quote data through `get_quotes_for_user` or
  an equivalent scoped selector. The legacy dashboard conversion aggregate has
  been fixed to follow that rule.

Missing scope fields:

- `Company`: missing organization, branch, department, and access policy fields.
  `account_owner` exists but is not enough for branch or department RBAC.
- `Contact`: missing independent organization, branch, department, and owner
  fields; it only belongs to `Company`.
- `CustomerCommercialProfile`: inherits only through `Company`; no direct scope.
- `Opportunity`, `Interaction`, and `Task`: missing organization, branch, and
  department fields. `Opportunity.owner`, `Task.owner`, and `Interaction.author`
  are available for future owner-scoped filtering.
- `Shipment`: has `organization` and a text `branch`; it is missing branch FK,
  department FK, and owner field.
- Reporting has no persisted model scope; it must be scoped through source
  selectors and field-level financial permissions.

Unclear relationships:

- Customer scope is a product decision: customers may be organization-local,
  branch-local, shared across branches, or shared globally. Current `Company`
  uniqueness by name assumes a single global customer namespace.
- Contact scope follows customer scope, but direct contact email uniqueness may
  conflict with branch-specific customer records.
- CRM scope likely needs to follow opportunity ownership and customer scope, but
  quote-derived CRM logging must keep working when opportunities are created
  from quote/SPOT workflows.
- Shipment branch text currently looks operational and user-entered. It should
  not be treated as an RBAC branch until mapped to `parties.Branch` by an
  explicit data plan.
- Reporting scope should continue to inherit quote selectors, but financial
  fields need separate permission semantics before hardening.

Direct ID access risks:

- `/api/v3/parties/companies/<company_id>/contacts/` resolves `Company` by
  primary key with no scope filter.
- `/api/v3/crm/opportunities/<id>/`, `/api/v3/crm/interactions/<id>/`, and
  `/api/v3/crm/tasks/<id>/` resolve through global CRM querysets.
- CRM query params `company`, `opportunity`, and `owner` are not constrained to
  the requester scope.
- Shipment direct shipment/document IDs are organization-filtered and are not
  currently a cross-organization IDOR risk, but branch-level IDOR remains
  unenforced.

Safe next PR order:

1. Customer/Company/Contact read-only diagnostics: added
   `python backend\manage.py rbac_customer_contact_report`. Do not add fields or
   filters yet.
2. CRM read-only diagnostics: report opportunities, interactions, and tasks by
   owner, author, linked company, linked quote-derived activity, and missing
   owner/author. Do not enforce owner scope yet.
3. Shipment branch diagnostics: compare `Shipment.branch` text values to
   `parties.Branch.code` within the shipment organization and report unmapped or
   ambiguous rows. Do not treat text branch as RBAC enforcement yet.
4. Add nullable customer/CRM/shipment scope fields only after diagnostics prove
   the backfill sources are safe. Keep selectors unchanged.
5. Add create-time scope assignment for customer/CRM/shipment records. Keep old
   rows on legacy behavior until backfill is approved.
6. Cut over selectors domain by domain: reports first, then customer/contact,
   then CRM, then shipment branch filtering.
7. Add permission-code-based financial report masking after selector boundaries
   are stable.


#### Phase 8A: CRM Discovery and Design

Date: 2026-06-20

Branch: `chore/rbac-crm-discovery-design`

Scope: read-only CRM RBAC diagnostics and design only. No schema, migrations,
selector/access behavior, frontend behavior, Quote/SPOT selectors, CRM
enforcement, pricing, ProductCode, or financial visibility was changed.

Diagnostic command added:

```bash
python backend/manage.py rbac_crm_report
python backend/manage.py rbac_crm_report --format json --show-details
```

The command is read-only and reports only safe identifiers in detail mode: CRM
record id, model/type/status, owner or author username, company id/name, linked
quote id/reference where available, and created timestamp. It does not print
notes, summaries, outcomes, task descriptions, email bodies, phone numbers,
addresses, commercial values, pricing, margins, buy cost, uploaded files, or
full payloads.

Local diagnostic output on the current SQLite snapshot:

- Combined CRM records: 267.
- Opportunities: 69 total, 69 with owner, 0 missing owner, 69 linked to company,
  69 linked to customer company, 47 linked to quotes, 0 with durable
  organization/branch/department scope fields, 69 likely globally accessible.
- Interactions: 198 total, 198 with author, 0 missing author, 198 linked to
  company, 198 linked to customer company, 154 linked to quotes, 0 with durable
  organization/branch/department scope fields, 198 likely globally accessible.
- Tasks: 0 total in this snapshot.
- Combined linked-to-quote count: 201.
- Combined records with durable organization, branch, or department scope: 0.
- Combined records likely globally accessible today: 267.

Current CRM access risks:

- CRM viewsets use `permissions.IsAuthenticated` for reads and
  `CrmWritePermission` for writes. Safe methods are allowed for every
  authenticated user.
- `OpportunityViewSet.get_queryset()` starts from all active opportunities and
  only narrows when the client supplies `company`, `status`, `owner`,
  `service_type`, or `priority`.
- `InteractionViewSet.get_queryset()` starts from all interactions and only
  narrows when the client supplies `company` or `opportunity`.
- `TaskViewSet.get_queryset()` starts from all tasks and only narrows when the
  client supplies `owner`, `status`, `due_date`, `company`, or `opportunity`.
- Detail endpoints inherit those global base querysets, so direct ID access is
  authenticated-global today.
- Client-supplied `owner`, `company`, and `opportunity` filters are not
  constrained to the requester's organization, branch, department, membership,
  or own records.

Current ownership fields are useful but not sufficient:

- `Opportunity.owner` exists and is fully populated in the current snapshot.
- `Interaction.author` exists and is fully populated in the current snapshot.
- `Task.owner` exists, but there are no task rows in the current snapshot.
- `Opportunity.won_by` and `Task.completed_by` are event/audit fields, not
  durable access scope.
- Owner/author can support an initial own-record fallback, but cannot express
  branch, department, organization, shared-customer, delegated, or team access.

Durable scope fields are likely needed before CRM enforcement:

- `Opportunity`, `Interaction`, and `Task` are missing organization, branch,
  and department fields.
- `Company` remains the natural customer anchor, but current customer records
  still lack durable organization/branch/department scope. CRM scope cannot be
  made reliable until customer scope is decided.
- Quote-derived CRM data can sometimes infer a linked quote through
  `Opportunity.quotes`, but quote linkage is incomplete and must not be the only
  CRM scope source.

Recommended CRM scope model:

- Add nullable `organization`, `branch`, `department`, and owner-style scope to
  CRM records in a later schema PR, after customer scope is decided.
- Use `Opportunity` as the primary CRM scope root. Interactions and tasks should
  inherit or validate against their linked opportunity when present, and fall
  back to company plus owner/author only when no opportunity exists.
- Keep quote-derived CRM logging intact: quote and SPOT create-quote flows
  should populate CRM scope from the quote's durable scope when an opportunity
  is created or linked.
- Keep old unscoped rows readable through legacy behavior until a backfill and
  explicit selector cutover are approved.

Recommended next phase:

1. Run customer/company/contact scope diagnostics first and decide whether
   customers are organization-local, branch-local, shared across branches, or
   globally shared.
2. Add nullable customer and CRM scope fields in separate schema-only PRs.
3. Add create-time scope assignment for CRM records from quote scope,
   opportunity scope, or the actor's single active membership. Do not infer
   branch from route, station code, mode, or free-text CRM fields.
4. Add a CRM scope backfill dry-run command. Write mode should require explicit
   approval and should fill missing fields only.
5. Cut over CRM selectors in a later PR after diagnostics and backfill prove the
   fallback behavior is safe.

Customer/contact diagnostics added on 2026-06-19:

```text
Customer/contact RBAC diagnostic report

Mode: read-only
Companies: total=236, customers=227, contacts=298, no_account_owner=235, no_detected_link=214
Links: companies_with_quotes=20, companies_with_spot=11, contacts_with_company=298, contacts_with_customer_company=297, contacts_with_quotes=21
Company types: internal=6, vendor=7, customer=227, carrier=1, agent=10

Available future scoping fields:
  Company: account_owner, is_customer, is_agent, is_carrier, audience_type, company_type, is_active, created_at, updated_at
  Contact: company, is_primary, is_active
```

Recommended next steps:

- Do not enforce customer/contact RBAC from the current data alone. `Company`
  and `Contact` still lack durable organization, branch, and department scope.
- Treat `Company.account_owner` as a weak candidate only; it is missing on most
  current rows and does not model shared customer visibility.
- Use quote, SPOT-through-quote, CRM, and shipment address-book links as
  backfill evidence, not as runtime selectors, until a separate schema/backfill
  PR defines ownership rules.
- Run CRM diagnostics next before choosing whether customer scope follows
  account owner, quote ownership, CRM owner, organization, branch, department,
  or an explicit access table.


#### Phase 8B — Customer/CRM Scope Foundation Plan

Date: 2026-06-20

Branch: `docs/rbac-customer-crm-scope-foundation-plan`

Scope: design only. No schema, migrations, selectors, access behavior,
frontend behavior, Quote/SPOT selectors, CRM enforcement, pricing, ProductCode,
or financial visibility should change in this phase.

Inputs used:

- `rbac_customer_contact_report`: 236 companies, 227 customers, 298 contacts,
  235 companies without `account_owner`, 214 companies with no detected quote,
  SPOT-through-quote, CRM, or shipment link, 20 companies linked to quotes, 11
  linked to SPOT-through-quote, and 21 contacts linked to quotes.
- `rbac_crm_report`: 267 CRM records, all with owner or author, 267 linked to
  company, 201 linked to quote-derived opportunities, 0 durable organization,
  branch, or department scope fields, and all likely globally accessible today.

Recommended fields by model:

- `Company`: add nullable `organization`, `branch`, `department`, and keep
  `account_owner` as an owner-like field. Add `created_by` only if product wants
  audit ownership for newly created companies; do not rely on it for legacy
  backfill unless historical data exists.
- `Contact`: add nullable `organization`, `branch`, `department`, and optional
  `owner` or `created_by` only if contacts can be individually owned apart from
  their company. Default contact scope should mirror `Contact.company`.
- `Opportunity`: add nullable `organization`, `branch`, `department`, and keep
  existing `owner` as the owner field.
- `Interaction`: add nullable `organization`, `branch`, `department`, and keep
  existing `author` as the creator/owner-like field. When linked to an
  opportunity, its durable scope should match the opportunity.
- `Task`: add nullable `organization`, `branch`, `department`, and keep existing
  `owner`; `completed_by` remains audit metadata, not access scope.

Backfill source priority:

1. Existing durable scope on the linked parent record, once fields exist:
   contact from company, interaction/task from opportunity, CRM records from
   linked company where company scope is already resolved.
2. Linked quote scope through `Quote.customer` or `Opportunity.quotes`, but only
   when all linked quotes agree on organization, branch, and department. If
   linked quotes disagree, report ambiguity and leave the field null.
3. Linked CRM opportunity scope for interactions and tasks. This is safe only
   after opportunity scope has already been assigned or backfilled.
4. Linked company/customer scope for opportunities, interactions, and tasks.
   This is safe only after company scope has already been assigned or
   backfilled.
5. Creator, owner, author, or account-owner membership, but only when that user
   has exactly one active membership and no stronger linked-record scope exists.
6. Legacy `CustomUser.organization` may fill organization only as a fallback
   candidate. Legacy `CustomUser.department` text should be reported but not
   mapped to `parties.Department` without an explicit mapping decision.

Unsafe inference rules:

- Do not infer branch or department from route, origin, destination, station
  code, shipment mode, service type, lane text, customer name, email domain,
  address, phone number, free-text notes, CRM summaries, task descriptions, or
  interaction outcomes.
- Do not use sparse `Company.account_owner` as the sole enforcement basis. It
  is missing on 235 of 236 companies in the current diagnostic snapshot and
  does not represent shared customer visibility.
- Do not copy scope from a quote set, CRM set, or shipment set when linked rows
  point to multiple organizations, branches, or departments.
- Do not make fields non-null, hide records, or deny direct IDs in the same PR
  that introduces scope fields.
- Do not treat global customer uniqueness as proof that customers are globally
  shared. That is a product decision, not a backfill rule.

Customer and CRM relationship:

- Company should be the customer scope root. Contact scope follows company
  scope by default.
- Opportunity should be the CRM scope root. Its preferred scope source is the
  company/customer scope, overridden only by unanimous linked quote scope when
  the business confirms quote-derived opportunities should follow quote scope.
- Interaction and Task should inherit from Opportunity when present; otherwise
  they inherit from Company. Owner/author membership is a fallback only.
- Quote-derived CRM logging must populate CRM scope from the quote's durable
  scope when creating or linking an opportunity. This keeps quote-first logging
  stable without changing Quote/SPOT selectors.

Ambiguous or missing scope handling:

- Leave ambiguous fields null and report the reason: `no_link`,
  `no_membership`, `multiple_memberships`, `conflicting_quote_scope`,
  `conflicting_crm_scope`, or `conflicting_company_scope`.
- Keep unscoped legacy rows on current authenticated-global behavior until
  controlled backfill and transitional selector diagnostics prove the fallback
  is safe.
- Require explicit manual decisions for high-value customers, shared customers,
  customers with conflicting quote scopes, and records with no detected links.

Proposed implementation sequence:

1. Schema-only PR: add nullable fields to Company, Contact, Opportunity,
   Interaction, and Task. No selectors, no migrations that write data, and no
   frontend changes beyond generated migration files.
2. Create-time population PR: populate new records from explicit parent scope,
   quote scope, or single active membership. Preserve existing API response
   shapes and write behavior.
3. Dry-run backfill report PR: add `rbac_customer_crm_scope_report` or extend
   existing diagnostics to show candidate scope, ambiguity reason, and safe
   identifiers only.
4. Controlled backfill PR: dry-run by default, `--write` required, fill missing
   fields only, never overwrite non-null scope, and leave ambiguous rows null.
5. Transitional selectors PR: prefer durable scope fields where present and keep
   legacy authenticated-global fallback for unscoped rows.
6. Comparison diagnostics PR: compare legacy visibility with scoped visibility
   by role, organization, branch, department, owner, and direct ID cases.
7. Hard cutover PR: remove legacy fallback only after null/ambiguous counts are
   accepted and direct-ID denial tests pass.

Tests required later:

- Migration tests prove nullable fields add without data writes or non-null
  constraints.
- Create-time tests for company, contact, opportunity, interaction, and task
  scope assignment.
- Backfill dry-run tests for unanimous quote scope, conflicting quote scope,
  company inheritance, opportunity inheritance, single membership fallback,
  multiple memberships, and no-link rows.
- Selector tests for list filtering, direct ID denial, query-param containment,
  owner-only access, branch/department access, organization-wide access, and
  legacy fallback behavior before hard cutover.
- Quote and SPOT workflow regression tests proving quote-derived CRM logging
  still occurs and Quote/SPOT selectors are unchanged.

Risks:

- Customer scope is a business decision. Customers may be organization-local,
  branch-local, shared across branches, or globally shared.
- Contact email uniqueness may conflict with branch-local customer/contact
  modeling.
- Company/account ownership is too sparse for enforcement and may represent
  account-management responsibility rather than access scope.
- Existing CRM owner/author coverage is strong, but owner/author does not model
  team, branch, department, organization, delegated, or shared-customer access.
- 214 companies currently have no detected link source, so any automated
  customer backfill will leave a material manual-decision set.

Go/no-go criteria before enforcement:

- Go only when nullable fields exist, create-time population is live, dry-run
  reports show acceptable null and ambiguity counts, controlled backfill has
  been reviewed, and comparison diagnostics show expected visibility.
- Go only when customer sharing semantics are explicitly decided.
- Go only when direct ID tests and query-param containment tests are ready.
- No-go if customer scope is still undecided, account owner is still the only
  candidate source, linked records conflict, or Quote/SPOT CRM logging has not
  been regression-tested.

#### Phase 8C - Schema-only Nullable Scope Fields

Date: 2026-06-20

Branch: `feat/rbac-customer-crm-scope-fields`

Scope: schema-only nullable scope fields. No selectors, access behavior,
frontend behavior, data backfill, create-time population, Quote/SPOT selector
changes, CRM enforcement, pricing, ProductCode, or financial visibility changed.

Nullable scope fields added:

- `Company.organization`, `Company.branch`, `Company.department`.
- `Contact.organization`, `Contact.branch`, `Contact.department`.
- `Opportunity.organization`, `Opportunity.branch`, `Opportunity.department`.
- `Interaction.organization`, `Interaction.branch`, `Interaction.department`.
- `Task.organization`, `Task.branch`, `Task.department`.

All fields are nullable, blankable foreign keys with `on_delete=SET_NULL` and
future-RBAC help text. Existing owner-style fields remain unchanged:
`Company.account_owner`, `Opportunity.owner`, `Interaction.author`,
`Task.owner`, `Opportunity.won_by`, and `Task.completed_by`.

No data was populated in this phase. Existing rows remain unscoped until a later
dry-run and controlled backfill phase. Existing serializers use explicit field
lists, so these new scope fields are not exposed through current APIs in this
phase.

Next phase:

1. Add create-time population for new Customer/Company/Contact and CRM records
   from explicit parent scope, quote scope, or single active membership.
2. Add or extend dry-run diagnostics to report candidate scope and ambiguity
   reasons for old rows.
3. Run a controlled backfill only after the dry-run report is accepted.
4. Keep selectors and enforcement unchanged until comparison diagnostics are
   available.

### Phase 5: Apply read filters by domain

Apply selectors domain by domain:

1. Quotes and SPOT.
2. Reporting.
3. Customers and contacts.
4. CRM.
5. Shipments branch filtering.
6. Rate management.

Each domain should be its own PR or very small group of PRs. Do not combine quote workflow changes with CRM cleanup or rate refactors.

Tests:

- Direct URL access denial.
- List filtering.
- Search filtering.
- Create/update ownership assignment.
- Report aggregation boundaries.

### Phase 6: Sensitive financial field hardening

After selectors are stable, fix the buy-cost and margin visibility mismatch.

Business decision: sales users should not be controlled by a blanket
allow/deny rule. Buy cost and margin visibility must be permission-based. Some
sales users may be allowed to see buy cost or margin, and others may not.

Suggested future permission codes:

RateEngine permission codes should use dot-separated namespaces, for example
`domain.action.scope_or_field`.

- `quote.view.buy_cost`
- `quote.view.margin`
- `rate.view.buy`
- `report.view.financials`

Do not change current COGS or buy-cost visibility in the selector-regression PR.
Existing tests that assert sales can see COGS should remain as legacy
compatibility coverage until the permission-based rollout is implemented.

Tests:

- Quote detail does not include buy fields for users lacking `quote.view.buy_cost`.
- SPOT compute/create responses do not leak buy costs to users lacking `quote.view.buy_cost` or `spot.view.buy_cost`.
- Reporting endpoints do not return cost, GP, or margin to users lacking financial permissions.
- Frontend charge cards do not display fields that the backend omits.

### Phase 7: Frontend permission UX

Extend `/api/auth/me/` to include effective permission codes and scope summaries.

Update frontend route guards, navigation, buttons, forms, and charge display using permission codes, not only roles.

Frontend must tolerate both old and new response shapes during rollout.

Tests:

- Navigation visibility matches effective permissions.
- Hidden controls remain blocked server-side.
- Quote and SPOT workflows remain usable for permitted users.

### Phase 8: Constraints and cleanup

Only after production data is backfilled and tests prove behavior:

- Consider non-null constraints for scope fields.
- Consider retiring compatibility role helpers.
- Consider removing old `CustomUser.department` reliance.
- Consider deleting dead compatibility code.

Do not delete compatibility paths in the same PR that introduces branch filtering.

## 10. Test and Verification Plan

Automated tests should cover:

- RBAC model migrations and seed idempotence.
- Effective permissions by role and membership.
- Quote list/detail access for own, same department, same branch, same organisation, and denied records.
- Quote create, recompute, version create, transition, clone, PDF export.
- Standard quote cost and margin masking.
- SPOT envelope list/detail/update/acknowledge/compute/create-quote access.
- SPOT cost masking.
- Customer list/search/contact filtering.
- CRM opportunity/interaction/task filtering.
- Shipment organisation and branch filtering.
- Rate management read/write permissions.
- Reporting aggregation boundaries and financial-field masking.
- `/api/auth/me/` backward compatibility.

Manual verification is required for every phase that touches quote workflow:

- Create a standard quote.
- Recompute/edit the quote.
- Finalize/send the quote.
- View quote detail as sales, manager, finance, and admin.
- Generate quote PDF.
- Open public quote URL and confirm sell-only rendering and branding.
- Create a SPOT envelope from quote flow.
- Analyze SPOT reply text or PDF.
- Resolve/acknowledge SPOT charges.
- Create quote from SPOT envelope.
- Confirm CRM quote logging still occurs.
- Confirm customer search/contact selection still works only within intended scope.

If any of these cannot be manually verified, document why and list residual risk in the PR.

## 11. Fallow Baseline

Fallow was run from the project root as required before this audit.

Commands and results:

- `npx fallow --format json`
  - Exit code: 0.
  - Fallow version: 2.88.3.
  - Warning: cache save failed while renaming a temp cache into place.
  - Summary: 96 total issues.
  - Breakdown: 79 unused exports, 16 unused types, 1 unused dependency.
- `npx fallow dead-code --format json`
  - Exit code: 1 with valid JSON findings.
  - Treated as findings-present behavior, not an install failure.
  - Same issue class: unused exports/types and unused dependency `eslint-config-next`.
- `npx fallow dupes --format json`
  - Exit code: 0.
  - 218 files scanned.
  - 53 files with clones.
  - 18 clone groups and 66 clone instances.
  - 4,743 duplicated lines out of 42,887 total lines.
  - Duplication percentage: 11.059295357567562.
  - Notable examples: frontend script test harness duplication, CRM date formatting duplication, repeated SPOT request blocks in `frontend/src/lib/api.ts`, and repeated dialog blocks in `QuoteStatusBadge.tsx`.
- `npx fallow health --format json`
  - Exit code: 1 with valid JSON findings.
  - Critical/high-complexity hotspots include:
    - `frontend/src/app/quotes/spot/[speId]/page.tsx`
    - `frontend/src/lib/quote-detail-mapping.ts`
    - `frontend/src/app/dashboard/page.tsx`
    - `frontend/src/app/quotes/[id]/page.tsx`
    - `frontend/src/app/customers/[id]/edit/page.tsx`
    - `frontend/src/components/quotes/ChargeCard.tsx`
    - `frontend/src/lib/quote-edit-hydration.ts`
    - `frontend/src/components/forms/QuoteForm.tsx`
    - `frontend/src/components/crm/OpportunityForm.tsx`
    - `frontend/src/hooks/useQuoteLogic.ts`

Fallow findings should not be cleaned up opportunistically in RBAC PRs. Use them as risk evidence and split any cleanup into separate PRs.

## 12. What Not To Touch Yet

Do not touch these in the first implementation slice:

- Do not revive legacy quote-scoped SPOT-rate CRUD.
- Do not add code against `/api/v3/quotes/<quote_id>/ai-intake/`.
- Do not change V4 deterministic pricing selection rules.
- Do not change the SPOT overlay merge strategy.
- Do not change domestic missing-rate behavior.
- Do not rename `Organization` to `Organisation` in code.
- Do not move users, quotes, shipments, customers, or rates between organisations without a separate approved data migration.
- Do not make branch or department fields non-null immediately.
- Do not rely on frontend hiding as security.
- Do not change public quote branding or signed-token public quote rendering except for tests proving no regression.
- Do not mix CRM navigation/UI expansion into quote RBAC.
- Do not combine Fallow cleanup with RBAC schema, selectors, or workflow changes.

## 13. Safest First Implementation Slice

The safest first implementation PR after this report is schema-only and behavior-preserving:

1. Add `Branch`, `Department`, `Permission`, `Role`, `RolePermission`, and `UserMembership`.
2. Seed default permissions and role templates that mirror current behavior.
3. Backfill user memberships from existing `CustomUser.organization` and `CustomUser.department`, but only when the source data is unambiguous.
4. Report users with null organisation or ambiguous membership instead of guessing.
5. Keep `/api/auth/me/` backward compatible.
6. Add tests for migration, seed idempotence, and login/me compatibility.
7. Do not change quote, SPOT, customer, CRM, shipment, reporting, or rate visibility in that PR.

The second safest slice is central permission resolution and serializer masking tests, still with selectors kept equivalent. The buy-cost visibility mismatch should be fixed only after the expected sales behavior is explicitly confirmed, because current code allows sales buy-cost visibility while existing comments say the opposite.
