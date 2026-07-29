# Air Freight Pilot Staging Readiness

Status: Phase 15C readiness record.

Final decision: **NOT READY**.

This document records the staging readiness checks required before AF15A-01 through AF15A-12 can run. It intentionally records only non-secret identifiers and evidence. Do not add credentials, tokens, passwords, private database connection strings, or Secret Manager values.

## 1. Scope and guardrails

Phase 15C prepares the environment only. It must not change pricing, quote totals, GST, FX, margin, ProductCode governance rules, finalization rules, RBAC rules, public quote output, or production data.

Required active architecture from repository deployment docs:

- Frontend: Google Cloud Run service.
- Backend/API: Google Cloud Run service.
- Database: Cloud SQL PostgreSQL reached by the backend through Cloud SQL connectivity.
- Migrations: Cloud Run Job executed before web service deployment.
- Secrets: Google Secret Manager references and GitHub Actions secrets; values must not be committed.
- Storage: Google Cloud Storage bucket configured by `GS_BUCKET_NAME`.

Deprecated Vercel/Render beta deployment is not the active architecture for this readiness gate.

## 2. Environment identity

| Item | Expected / source | Phase 15C evidence | Status |
| --- | --- | --- | --- |
| Staging frontend URL | Staging Cloud Run frontend URL or approved custom domain. | Not provided to this agent session. | Blocked |
| Staging backend/API URL | Staging Cloud Run backend URL used by `NEXT_PUBLIC_API_BASE_URL`. | Not provided to this agent session. | Blocked |
| Staging database | Staging Cloud SQL PostgreSQL instance, separate from production. | Not provided to this agent session. | Blocked |
| Deployment platform | Google Cloud Run per `docs/cloud_run_deployment.md` and `docs/github_actions_deployment.md`. | Repository docs reviewed. Actual staging project/service names not provided. | Partially confirmed |
| Current deployed commit | Commit served by staging frontend/backend. | Not available. Repository branch starts from `f14c3ba2` after PR #292, but deployed staging commit is unverified. | Blocked |

## 3. Configuration readiness checklist

| Area | Required verification | Phase 15C result | Status |
| --- | --- | --- | --- |
| Backend env vars | `DJANGO_DEBUG=False`, `DJANGO_SECRET_KEY`, `DATABASE_URL`, `INSTANCE_CONNECTION_NAME`, `ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`, `GS_BUCKET_NAME`, `GEMINI_API_KEY`. | Not verified in staging; no cloud project/service access in this session. | Blocked |
| Frontend env vars | `NEXT_PUBLIC_API_BASE_URL` points at staging backend; `NEXT_PUBLIC_BACKEND_HOSTNAME` matches backend host. | Not verified in staging. | Blocked |
| Database connectivity | Backend health/check confirms Cloud SQL connectivity against staging DB. | Not verified in staging. | Blocked |
| Auth | Sales, manager, admin, and finance/read-only users can authenticate. | Not verified in staging. | Blocked |
| Storage | GCS bucket exists, service account can read/write required media. | Not verified in staging. | Blocked |
| Secrets | Required Secret Manager references exist and are accessible by service accounts. Values are not exposed. | Not verified in staging. | Blocked |
| CORS/CSRF/API | Frontend can authenticate and call backend API without cross-origin failures. | Not verified in staging. | Blocked |

## 4. Migration and seed readiness

Run these commands only against the staging backend/database after confirming the target environment is staging:

```bash
python backend/manage.py migrate --noinput
python backend/manage.py air_freight_pilot_seed_plan --format json
python backend/manage.py air_freight_pilot_seed_plan --format json --apply
python backend/manage.py air_freight_pilot_seed_audit --format json
```

Expected interpretation:

- `migrate --noinput`: all migrations applied to staging DB.
- seed plan dry run: `status` is `ready_for_apply` before apply.
- seed apply: creates/reuses only approved scoped pilot ProductCodes and ChargeAliases; broad FSC, generic handling, and miscellaneous recoveries remain out of apply scope.
- seed audit: `ready` or `ready_with_warnings` with only accepted conservative manual-review warnings.

Phase 15C execution result:

| Command | Staging result | Status |
| --- | --- | --- |
| `migrate --noinput` | Not run; no staging DB access. | Blocked |
| `air_freight_pilot_seed_plan --format json` | Not run in staging. | Blocked |
| `air_freight_pilot_seed_plan --format json --apply` | Not run; apply must wait for reviewed dry-run output against staging. | Blocked |
| `air_freight_pilot_seed_audit --format json` | Not run in staging. | Blocked |

No seed apply, cleanup, backfill, pricing change, or migration was run from this agent session.

## 5. Staging user readiness

Required non-secret user evidence:

| Test user | Required role | Organization | Operating entity | Branch | Department | Phase 15C status |
| --- | --- | --- | --- | --- | --- | --- |
| Air pilot sales user | sales | Express Freight Management | EFM PNG or approved pilot entity | Port Moresby or approved pilot branch | Air Freight | Not provided / not verified |
| Air pilot manager user | manager | Express Freight Management | EFM PNG or approved pilot entity | Port Moresby or approved pilot branch | Air Freight | Not provided / not verified |
| Air pilot admin user | admin | Express Freight Management | EFM PNG or approved pilot entity | Port Moresby or approved pilot branch | Air Freight | Not provided / not verified |
| Air pilot finance/read-only user | finance or approved read-only role | Express Freight Management | EFM PNG or approved pilot entity | Port Moresby or approved pilot branch | Air Freight | Not provided / not verified |

Verification must confirm the canonical hierarchy:

```text
Organization: Express Freight Management
OperatingEntity: EFM PNG / EFM Australia / EFM Fiji / EFM Solomon Islands
Branch: Port Moresby / Lae / Brisbane / Suva / Honiara
Department: Air Freight / Sea Freight / Customs / Transport
```

Do not create or update users without explicit staging admin approval and a non-secret credential handoff process.

## 6. Endpoint and workflow readiness

| Workflow | Required verification | Phase 15C status |
| --- | --- | --- |
| Live Exception Workspace | `/quotes/spot/<envelope_id>/exception-workspace` loads a live Draft Quote payload, not demo data. | Blocked: no staging URL/SPE ID. |
| ProductCode selector | Results are direction/domain scoped from trusted route countries, not free-text direction. | Blocked: no live workspace. |
| Finalize endpoint | `/api/v3/spot/envelopes/<envelope_id>/draft-quote/finalize/` reachable for authorized user and blocks unresolved items. | Blocked: no staging API/user. |
| Reopen endpoint | `/api/v3/spot/envelopes/<envelope_id>/draft-quote/reopen/` reachable for manager/admin and forbidden for sales/finance/cross-scope/unauthenticated users. | Blocked: no staging API/user. |
| Test SPE/quote creation | Required pilot SPEs/quotes can be created without mutating production data. | Blocked: no staging access. |

## 7. AF15A scenario record preparation

The following scenario records are required before Phase 15B can resume. IDs must be filled with real staging SPE/quote IDs after creation.

| Scenario | Required staging record | SPE ID | Quote ID | Status |
| --- | --- | --- | --- | --- |
| AF15A-01 | Export POM/PG to BNE/AU airport-to-airport quote with air freight, fuel surcharge, AWB, screening. | Pending | Pending | Not prepared |
| AF15A-02 | Import SIN/SG to POM/PG airport-to-door quote with freight, destination handling, storage. | Pending | Pending | Not prepared |
| AF15A-03 | Air quote with explicit `fuel surcharge` and broad `FSC`. | Pending | Pending | Not prepared |
| AF15A-04 | Air quote with generic `handling` only. | Pending | Pending | Not prepared |
| AF15A-05 | Air quote with `misc recovery`. | Pending | Pending | Not prepared |
| AF15A-06 | Air quote with customs/pass-through wording. | Pending | Pending | Not prepared |
| AF15A-07 | Air quote with AWB/docs/terminal ambiguity. | Pending | Pending | Not prepared |
| AF15A-08 | Quote/envelope with unknown unstructured documentation-fee item for existing ProductCode mapping. | Pending | Pending | Not prepared |
| AF15A-09 | Quote/envelope with unknown charge requiring new ProductCode request. | Pending | Pending | Not prepared |
| AF15A-10 | Continuation of AF15A-09 request lifecycle with rejected/corrected/resubmitted request. | Pending | Pending | Not prepared |
| AF15A-11 | Completed reviewed quote for finalize/reopen/edit/re-finalize path. | Pending | Pending | Not prepared |
| AF15A-12 | Finalized quote/envelope for unauthorized-role checks. | Pending | Pending | Not prepared |

## 8. Remaining blockers

| Blocker ID | Blocker | Owner | Required action |
| --- | --- | --- | --- |
| P15C-ENV-01 | Staging frontend URL not provided/verified. | Deployment owner / project maintainer | Provide non-secret staging frontend URL and confirm it serves the intended environment. |
| P15C-ENV-02 | Staging backend/API URL not provided/verified. | Deployment owner / project maintainer | Provide non-secret staging backend URL and confirm `/api/health/` or equivalent health endpoint. |
| P15C-ENV-03 | Staging database identity/connectivity not verified. | Deployment owner / DBA | Confirm staging Cloud SQL instance and run migrations against staging only. |
| P15C-ENV-04 | Current deployed commit not verified. | Deployment owner | Confirm frontend/backend revisions are deployed from the intended commit after PR #292 or deploy the target commit. |
| P15C-CONFIG-01 | Required env vars, secrets, storage, CORS/CSRF, and frontend API configuration not verified. | Deployment owner | Verify Cloud Run service configuration without exposing secret values. |
| P15C-SEED-01 | Seed dry run/apply/audit not executed in staging. | Admin/support with staging access | Run dry run, review output, apply only if `ready_for_apply`, then run audit and attach non-secret JSON summaries. |
| P15C-USER-01 | Staging users and memberships not verified. | Admin/support | Create or verify sales, manager, admin, and finance/read-only users with canonical Air Freight hierarchy memberships. |
| P15C-WORKFLOW-01 | Live workspace, ProductCode selector, finalize/reopen endpoints, and test SPE/quote creation not verified. | Admin/support + pilot manager | Create test SPEs/quotes and verify endpoint/UI reachability by role. |

## 9. Decision

**NOT READY**

Phase 15B may resume only after all P15C blockers above are closed with non-secret staging evidence in this document and `docs/pilot/air-freight-pilot-evidence.md`.
