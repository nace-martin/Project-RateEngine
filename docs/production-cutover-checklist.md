# Production Cutover Checklist

Last updated: 2026-03-19

This is the execution checklist for the final production cutover.

Use it with:
- [pre-production-runbook.md](/C:/Users/commercial.manager/dev/Project-RateEngine/docs/pre-production-runbook.md)
- [go-live-status-tracker.md](/C:/Users/commercial.manager/dev/Project-RateEngine/docs/go-live-status-tracker.md)
- [launch-corridor-matrix.md](/C:/Users/commercial.manager/dev/Project-RateEngine/docs/launch-corridor-matrix.md)
- [vercel-render-beta-deploy.md](/C:/Users/commercial.manager/dev/Project-RateEngine/docs/vercel-render-beta-deploy.md)
- [production-launch-execution-sheet.md](/C:/Users/commercial.manager/dev/Project-RateEngine/docs/production-launch-execution-sheet.md)

## Hard Stop Rules

Do not launch if any of these fail:

- launch corridor list is not explicitly approved
- production `system admin`, `manager`, and `sales` users are not verified
- production env vars are not verified
- migrations or static collection fail
- FX snapshot is stale or missing
- final customer/contact import is incomplete
- final UAT is not complete
- scheduled jobs are not configured

## T-7 To T-3 Days

### 1. Launch Scope Approval

Owner: Pricing / Business

Pass criteria:
- [launch-corridor-matrix.md](/C:/Users/commercial.manager/dev/Project-RateEngine/docs/launch-corridor-matrix.md) is reviewed
- exact go-live export, import, and domestic lanes are marked approved
- any non-`POM` PNG import destinations in scope are explicitly listed

Evidence:
- approved lane list captured in writing

### 2. Customer and Contact Readiness

Owner: Customer Ops

Pass criteria:
- final launch customer file exists
- final launch contact file exists
- all launch customers have at least one usable contact
- no critical customer is missing from the import set

Evidence:
- import validation output saved
- spot check of real customer/contact selection in app

### 3. Pricing Scope Validation

Owner: Pricing

Pass criteria:
- approved lanes exist in the seeded coverage
- any missing tariffs are identified before launch week
- special-cargo expectations are clear:
  - import `DG` / `AVI` / `HVC` to `POM` standard-quote
  - domestic `SCR` / `AVI` / `HVC` / `OOG` standard-quote
  - `DG` / `PER` domestic still SPOT if unchanged

Evidence:
- checked against [launch-corridor-matrix.md](/C:/Users/commercial.manager/dev/Project-RateEngine/docs/launch-corridor-matrix.md)

## T-2 To T-1 Days

### 4. Production Environment Verification

Owner: Platform / DevOps

Required env vars:
- `DATABASE_URL`
- `DJANGO_SECRET_KEY`
- `ALLOWED_HOSTS`
- `CORS_ALLOWED_ORIGINS`
- `CSRF_TRUSTED_ORIGINS`
- `FRONTEND_BASE_URL`
- `GEMINI_API_KEY`
- `USE_X_FORWARDED_PROTO=true` if TLS terminates upstream
- `SERVE_STATIC_FILES=true`

Pass criteria:
- production settings load without error
- app boots cleanly in prod mode
- no missing-secret or host-header errors

Evidence:
- successful boot logs

### 5. Production Migration and Static Build

Owner: Platform / DevOps

Commands:

```bash
python manage.py check
python manage.py migrate
python manage.py collectstatic --noinput
```

Pass criteria:
- all commands succeed
- no failed migrations
- static assets are available in production

Evidence:
- command output captured

### 6. Production Users and Access

Owner: Admin / Security

Planned launch users:
- system admin: `Nace Martin` <`nason.s.martin@gmail.com`>
- manager: `Evgenii Tsoi` <`evgenii.tsoi@efmpng.com`>
- sales: `Julie-Anne Hasing` <`julie-anne.hasing@efmpng.com`>
- finance: not required for this launch phase

Pass criteria:
- `system admin` login verified
- `manager` login verified
- `sales` login verified
- API token generation works for the production system admin

Evidence:
- successful login check for each role

### 7. FX and Policy Verification

Owner: Finance / Pricing

Pass criteria:
- one active production policy only
- FX snapshot is current
- `USD/PGK` and `AUD/PGK` are present

Suggested command:

```bash
python manage.py fetch_fx --pairs USD:PGK,PGK:USD,AUD:PGK,PGK:AUD
```

Evidence:
- FX timestamp captured
- active policy name recorded

## Launch Day

### 8. Pre-Open Functional Checks

Owner: QA / Business

Run these in the deployed environment:

1. Export standard quote on an approved launch lane
2. Import standard quote on an approved launch lane
3. Import `A2D` `DG`
4. Import `A2D` `AVI` or `HVC`
5. Domestic `GCR`
6. Domestic `SCR` or `AVI`
7. One intentionally valid SPOT-required case

Pass criteria for each:
- compute succeeds in the expected path
- no unwanted SPOT trigger
- `has_missing_rates` is false unless the case is intentionally SPOT/incomplete
- line items look commercially correct

Evidence:
- quote references captured

### 9. Finalize and PDF Checks

Owner: QA / Business

Pass criteria:
- at least one export quote finalizes
- at least one import quote finalizes
- at least one domestic quote finalizes if domestic is in scope
- PDFs generate and render correctly

Evidence:
- quote refs and PDF confirmation recorded

### 10. Scheduler Verification

Owner: Platform / DevOps

Required recurring jobs:
- FX refresh

Commands used by schedulers:

```bash
python manage.py fetch_fx --pairs USD:PGK,PGK:USD,AUD:PGK,PGK:AUD
```

Pass criteria:
- jobs are configured in production
- first scheduled run is confirmed or manually proven

Evidence:
- scheduler config or run logs captured

## Go / No-Go Decision

Owner: Product / Business / Platform / Pricing

Go only if all are true:
- corridor list approved
- production users verified
- production env verified
- FX current
- policy correct
- customer/contact import verified
- UAT pass complete
- scheduler configured

If any item is still open, keep status:
- `GO-LIVE HOLD`

## Signoff Record

Fill this in at cutover time.

| Area | Owner | Status | Evidence |
| --- | --- | --- | --- |
| Corridor approval |  |  |  |
| Customer/contact import |  |  |  |
| Production env vars |  |  |  |
| Migrations/static |  |  |  |
| System admin user |  |  |  |
| Manager user |  |  |  |
| Sales user |  |  |  |
| FX current |  |  |  |
| Policy verified |  |  |  |
| Export UAT |  |  |  |
| Import UAT |  |  |  |
| Domestic UAT |  |  |  |
| SPOT UAT |  |  |  |
| PDF verification |  |  |  |
| Scheduler verification |  |  |  |
