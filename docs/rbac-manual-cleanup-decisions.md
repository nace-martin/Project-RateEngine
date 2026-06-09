# RBAC Manual Cleanup Decisions

Date: 2026-06-09  
Branch: `chore/rbac-manual-cleanup-decisions`  
Source context: `docs/rbac-membership-backfill-report.md`

## Scope

This document records manual cleanup decisions needed before RBAC enforcement work. It is report-only and does not change application code, migrations, seed logic, runtime access behaviour, or sales buy-cost/COGS visibility.

## Decisions

| Subject | Recommended decision | Enforcement note |
| --- | --- | --- |
| `system_user` | Treat as a service/system account. Exclude from user-facing RBAC unless a concrete operational need is identified. | Do not guess an organisation. If this account needs runtime access, assign an explicit organisation and system/service role first. |
| `testuser` | Treat as test-only. Assign to `test-org` for test data, or deactivate/remove from real data. | Do not leave active in production-like data without an explicit organisation membership. |
| `admin`, `admin_user`, `sysadmin` | Use organisation-wide admin scope. Department and branch can remain null only because the role is organisation/global scoped. | Admin scope should not depend on department filters. Confirm each account belongs to the correct organisation before enforcement. |
| `finance` | Use organisation-wide finance scope with cross-department visibility. | Finance should not be blocked by department-level quote/reporting filters, but this document does not implement that behaviour. |
| `nas`, `nason.martin` | Use organisation-wide commercial/admin scope with multi-department access across Air, Sea, Land/Transport, and Finance visibility as needed. | Record explicit multi-department memberships before department enforcement. Do not infer department access from null membership data. |
| `unassigned_user` | Deactivate or assign explicitly before enforcement. | This user must not pass through enforcement with null department data by accident. |
| Branch assignment strategy | Branch assignment must not be guessed from existing data. Branch null is allowed only for organisation-wide/global roles. | Normal sales and manager users should receive explicit branch memberships before branch enforcement. |
| Multi-department users | Represent multi-department access explicitly with additional memberships or a documented cross-department role. | Do not overload null department to mean all departments for normal users. |
| `test-org` handling | Keep as test/demo data unless it has a real operational purpose. Add branch records only if branch-aware tests or demos need them. | Do not mix `test-org` assumptions into production RBAC policy. |
| Sales buy-cost/COGS policy | Sales users may view sell charges but should not view buy cost, COGS, GP, or margin by default. | This is a future policy decision only. Do not change current sales buy-cost/COGS visibility in this branch. |

## Pre-Enforcement Checklist

- Confirm whether `system_user` remains excluded from user-facing RBAC.
- Assign, deactivate, or remove `testuser` from real data.
- Confirm organisation ownership for `admin`, `admin_user`, `sysadmin`, `finance`, `nas`, and `nason.martin`.
- Add explicit department and branch memberships for normal sales and manager users.
- Add explicit multi-department memberships for cross-functional commercial/admin users.
- Decide whether `test-org` remains test-only and whether it needs branch records.
- Implement sales buy-cost/COGS restrictions only in a dedicated enforcement phase, with quote/SPOT/pricing regression coverage.

## Phase Readiness

RBAC enforcement should not begin until the cleanup decisions above are applied or intentionally documented as accepted exceptions. The immediate next phase can safely be another report-only or schema-compatible planning step, but not access filtering.

