# RBAC Membership Backfill & Data Validation Report

Date: 2026-06-09  
Branch: `chore/rbac-membership-backfill-validation`  
Base: `main` at PR #108 merge commit `c2740c0aa047c413959959bcfdcb50316b445c88`

## Scope

This Phase 2 validation ran the Phase 1 RBAC foundation migrations and seed command against the current local database. It validates the new branch, department, role, permission, and user membership data without enforcing RBAC or changing runtime access behaviour.

No quote, SPOT, customer, CRM, shipment, reporting, rate, pricing, PDF, public quote, sales buy-cost/COGS, `CustomUser.role`, or `CustomUser.department` behaviour was changed.

## Commands Run

```powershell
git fetch origin
git switch main
git merge --ff-only origin/main
git switch -c chore/rbac-membership-backfill-validation
npx fallow --format json
npx fallow dead-code --format json
npx fallow dupes --format json
npx fallow health --format json
python backend\manage.py migrate
python backend\manage.py seed_rbac_foundation --json
python backend\manage.py seed_rbac_foundation --json
```

## Seed Command Output

First run:

```json
{
  "branches": {"created": 10, "existing": 0},
  "departments": {"created": 15, "existing": 0},
  "memberships": {"created": 15, "existing": 0, "updated": 0},
  "permissions": {"created": 32, "existing": 0},
  "reported": {
    "users_missing_department": [
      "admin",
      "admin_user",
      "finance",
      "nas",
      "nason.martin",
      "sysadmin",
      "unassigned_user"
    ]
  },
  "role_permissions": {"created": 95, "existing": 0},
  "roles": {"created": 4, "existing": 0},
  "skipped": {
    "null_organization": ["system_user", "testuser"],
    "unknown_department": [],
    "unknown_role": []
  }
}
```

Second run:

```json
{
  "branches": {"created": 0, "existing": 10},
  "departments": {"created": 0, "existing": 15},
  "memberships": {"created": 0, "existing": 15, "updated": 0},
  "permissions": {"created": 0, "existing": 32},
  "reported": {
    "users_missing_department": [
      "admin",
      "admin_user",
      "finance",
      "nas",
      "nason.martin",
      "sysadmin",
      "unassigned_user"
    ]
  },
  "role_permissions": {"created": 0, "existing": 95},
  "roles": {"created": 0, "existing": 4},
  "skipped": {
    "null_organization": ["system_user", "testuser"],
    "unknown_department": [],
    "unknown_role": []
  }
}
```

Result: the seed command is idempotent on this database. The second run created no rows, updated no memberships, and preserved the same reported/skipped user lists.

## Existing Organisations Found

| Organisation slug | Name | Active | Users |
| --- | --- | ---: | ---: |
| `efm` | Express Freight Management | yes | 0 |
| `efm-express-air-cargo` | EFM Express Air Cargo | yes | 10 |
| `test-org` | Test Org | yes | 5 |

## Branches Created/Found

10 branches were created on the first run and found on the second run. Branches were created only for the default EFM organisation slugs.

| Organisation slug | Branch codes |
| --- | --- |
| `efm` | `BNE`, `FIJ`, `LAE`, `POM`, `SOL` |
| `efm-express-air-cargo` | `BNE`, `FIJ`, `LAE`, `POM`, `SOL` |
| `test-org` | none |

All seeded branches are active. No users were assigned to a branch because existing user data does not carry an unambiguous branch field.

## Departments Created/Found

15 departments were created on the first run and found on the second run. Each organisation received the same five active department records: `ADMIN`, `AIR`, `FINANCE`, `LAND`, and `SEA`.

| Organisation slug | Department codes |
| --- | --- |
| `efm` | `ADMIN`, `AIR`, `FINANCE`, `LAND`, `SEA` |
| `efm-express-air-cargo` | `ADMIN`, `AIR`, `FINANCE`, `LAND`, `SEA` |
| `test-org` | `ADMIN`, `AIR`, `FINANCE`, `LAND`, `SEA` |

Department `branch` remains null for all records, preserving compatibility with the current `CustomUser.department` code-only field.

## Roles Created/Found

Four system roles were created on the first run and found on the second run. No organisation-specific roles were created.

| Scope | Role code | Name | Permission count |
| --- | --- | --- | ---: |
| system | `admin` | Admin | 32 |
| system | `finance` | Finance | 15 |
| system | `manager` | Manager | 28 |
| system | `sales` | Sales | 20 |

These roles mirror the current compatibility role values: `CustomUser.role` remains present and unchanged.

## Permissions Created/Found

32 permissions were created on the first run and found on the second run:

`crm.manage`, `crm.view`, `customer.manage`, `customer.view`, `fx.edit`, `quote.clone`, `quote.create`, `quote.edit`, `quote.export_pdf`, `quote.finalize`, `quote.transition`, `quote.view.buy_cost`, `quote.view.department`, `quote.view.margin`, `quote.view.organization`, `quote.view.own`, `quote.view.sell`, `rate.edit`, `rate.view.buy`, `rate.view.sell`, `report.view.financials`, `report.view.own`, `shipment.manage`, `shipment.view`, `spot.acknowledge`, `spot.analyze`, `spot.compute`, `spot.create`, `spot.create_quote`, `spot.review`, `system.settings`, `user.manage`.

95 role-permission links were created on the first run and found on the second run.

## User Memberships Created

15 active primary user memberships were created on the first run and found unchanged on the second run.

| Username | Organisation | Legacy role | Membership role | Legacy department | Membership department | Branch |
| --- | --- | --- | --- | --- | --- | --- |
| `admin` | `efm-express-air-cargo` | `admin` | `admin` | null | null | null |
| `admin_user` | `test-org` | `admin` | `admin` | null | null | null |
| `air_sales_pom` | `test-org` | `sales` | `sales` | `AIR` | `AIR` | null |
| `evgenii.tsoi` | `efm-express-air-cargo` | `manager` | `manager` | `AIR` | `AIR` | null |
| `finance` | `efm-express-air-cargo` | `finance` | `finance` | null | null | null |
| `joseph.kaima` | `efm-express-air-cargo` | `manager` | `manager` | `AIR` | `AIR` | null |
| `julie-anne.hasing` | `efm-express-air-cargo` | `sales` | `sales` | `AIR` | `AIR` | null |
| `manager` | `efm-express-air-cargo` | `manager` | `manager` | `AIR` | `AIR` | null |
| `nas` | `efm-express-air-cargo` | `admin` | `admin` | null | null | null |
| `nason.martin` | `efm-express-air-cargo` | `admin` | `admin` | null | null | null |
| `national_air_manager` | `test-org` | `manager` | `manager` | `AIR` | `AIR` | null |
| `sales` | `efm-express-air-cargo` | `sales` | `sales` | `AIR` | `AIR` | null |
| `sea_manager_lae` | `test-org` | `manager` | `manager` | `SEA` | `SEA` | null |
| `sysadmin` | `efm-express-air-cargo` | `admin` | `admin` | null | null | null |
| `unassigned_user` | `test-org` | `sales` | `sales` | null | null | null |

No non-null-organisation users were left without a membership.

## Users Skipped Because Organisation Is Null

The seed command did not guess an organisation for these users:

- `system_user`
- `testuser`

Both users remain without memberships and should be reviewed manually before any RBAC enforcement phase.

## Users Skipped Because Role Is Unknown

None.

## Users Skipped Because Department Is Unknown

None.

## Users With Ambiguous Membership Data

Seven users had a known organisation and role but no legacy department value:

- `admin`
- `admin_user`
- `finance`
- `nas`
- `nason.martin`
- `sysadmin`
- `unassigned_user`

The seed command created memberships for these users with `department=null` and reported them instead of guessing a department. This is behaviour-preserving now, but Phase 3 should not rely on department-scoped enforcement for these users until manual decisions are made.

## Duplicate Or Conflicting Membership Risks

No duplicate or conflicting membership risks were detected in the current local database:

- 0 users with more than one active primary membership.
- 0 memberships where the membership organisation differs from `CustomUser.organization`.
- 0 memberships where the membership department belongs to a different organisation.
- 0 memberships where the membership branch belongs to a different organisation.
- 0 memberships where a non-null legacy `CustomUser.department` differs from the membership department.
- 0 users with a non-null organisation and no membership.

Known residual risks:

- Branch assignment is not inferable from existing user records, so every membership branch remains null.
- `efm` has default branches and departments but no users in the local database.
- `test-org` has departments but no default branches because branch seeding is scoped to the default EFM organisation slugs.
- Seven memberships have null departments by design because legacy user records do not provide a department.
- Two users have null organisations and were intentionally skipped.

## Recommended Manual Cleanup Decisions

1. Decide whether `system_user` and `testuser` should receive an organisation membership or remain service/test accounts excluded from future RBAC enforcement.
2. Decide explicit departments for `admin`, `admin_user`, `finance`, `nas`, `nason.martin`, `sysadmin`, and `unassigned_user`, or document that their future access must be organisation/global-scoped.
3. Decide whether `test-org` needs branch records before any branch-aware UI or enforcement is introduced.
4. Decide whether `efm` should remain a seeded, userless organisation in the local data set or whether its purpose should be documented before enforcement.
5. Do not enforce department or branch filters until the null-organisation and null-department cases above have explicit manual decisions.

## Fallow Baseline Summary

Fallow was run as baseline evidence only. No cleanup was performed.

| Command | Result |
| --- | --- |
| `npx fallow --format json` | exit 0; 96 total check issues: 79 unused exports, 16 unused types, 1 unused dependency |
| `npx fallow dead-code --format json` | exit 1 due existing findings; 96 total issues with the same dead-code summary |
| `npx fallow dupes --format json` | exit 0; 18 clone groups, 66 clone instances, 4,743 duplicated lines, 11.059% duplication |
| `npx fallow health --format json` | exit 1 due existing health findings; top critical hotspots include `frontend/src/app/quotes/spot/%5BspeId%5D/page.tsx`, `frontend/src/lib/quote-detail-mapping.ts`, and `frontend/src/app/dashboard/page.tsx` |

## Phase 3 Readiness

It is safe to proceed to Phase 3 only as a planning/design step or as another behaviour-preserving validation phase.

It is not yet safe to enforce RBAC access filters until the manual cleanup decisions are resolved for:

- two users with null organisation: `system_user`, `testuser`;
- seven users with null department membership data;
- branch assignment strategy for users and any non-EFM organisations.

