# Production Launch Execution Sheet

Last updated: 2026-03-28

Use this as the practical cutover sheet for the current repo state.

Read together with:
- [production-cutover-checklist.md](/C:/Users/commercial.manager/dev/Project-RateEngine/docs/production-cutover-checklist.md)
- [vercel-render-beta-deploy.md](/C:/Users/commercial.manager/dev/Project-RateEngine/docs/vercel-render-beta-deploy.md)
- [go-live-status-tracker.md](/C:/Users/commercial.manager/dev/Project-RateEngine/docs/go-live-status-tracker.md)

## Target Deployment Shape

- frontend: `Vercel`
- backend API: `Render Web Service`
- database: `Render Postgres`
- scheduler: `Render Cron Job`

## Platform Settings

### Render Backend

Use these values:

- Root Directory: `backend`
- Runtime: `Python`
- Build Command:

```bash
pip install -r requirements.txt && python manage.py collectstatic --noinput
```

- Pre-Deploy Command:

```bash
python manage.py migrate --noinput
```

- Start Command:

```bash
gunicorn rate_engine.wsgi:application --bind 0.0.0.0:$PORT --workers 4 --threads 2 --access-logfile - --error-logfile -
```

- Health Check Path: `/api/health/`
- Persistent Disk Mount Path: `/opt/render/project/src/backend/branding`

### Vercel Frontend

Use these values:

- Framework Preset: `Next.js`
- Root Directory: `frontend`
- Install Command: default
- Build Command: default
- Output Directory: default
- Node Version: `20`

## Production Environment Variables

### Render Backend Required Values

Replace the placeholder domains below with your actual deployed frontend/backend URLs.

```dotenv
DATABASE_URL=<from Render Postgres connection string>
DJANGO_SECRET_KEY=<generate a new 50+ char secret>
DJANGO_DEBUG=false
ALLOWED_HOSTS=rateengine-beta-api.onrender.com
CORS_ALLOWED_ORIGINS=https://project-rate-engine.vercel.app
CSRF_TRUSTED_ORIGINS=https://project-rate-engine.vercel.app,https://rateengine-beta-api.onrender.com
FRONTEND_BASE_URL=https://project-rate-engine.vercel.app
GEMINI_API_KEY=<new production Gemini key>
USE_X_FORWARDED_PROTO=true
SERVE_STATIC_FILES=true
SERVE_MEDIA_FILES=false
ENABLE_BROWSABLE_API=false
```

If you add custom domains, append them instead of replacing the existing values.

Example with custom domains:

```dotenv
ALLOWED_HOSTS=rateengine-beta-api.onrender.com,api.rateengine.app
CORS_ALLOWED_ORIGINS=https://project-rate-engine.vercel.app,https://beta.rateengine.app
CSRF_TRUSTED_ORIGINS=https://project-rate-engine.vercel.app,https://beta.rateengine.app,https://rateengine-beta-api.onrender.com,https://api.rateengine.app
FRONTEND_BASE_URL=https://beta.rateengine.app
```

### Vercel Frontend Required Values

```dotenv
NEXT_PUBLIC_API_BASE_URL=https://rateengine-beta-api.onrender.com
```

If you switch the backend to a custom API domain, update this value to that final URL.
The current Vercel production domain is:
- `https://project-rate-engine.vercel.app`

### Render Cron Job

Use this command:

```bash
python manage.py fetch_fx --pairs USD:PGK,PGK:USD,AUD:PGK,PGK:AUD
```

Use this schedule:

```text
0 7 * * 1-5
```

The cron job should inherit:
- `DATABASE_URL`
- `DJANGO_SECRET_KEY`
- `DJANGO_DEBUG=false`
- `ALLOWED_HOSTS`
- `CORS_ALLOWED_ORIGINS`
- `CSRF_TRUSTED_ORIGINS`
- `FRONTEND_BASE_URL`
- `USE_X_FORWARDED_PROTO=true`

## Secrets Rules

- Do not reuse the development Gemini key from any local `.env` file as the production key.
- Generate a fresh production `DJANGO_SECRET_KEY`.
- Keep `DJANGO_DEBUG=false`.
- Keep `ENABLE_BROWSABLE_API=false`.
- Keep `SERVE_MEDIA_FILES=false`; branding logos and shipment documents already use explicit app endpoints.

## Cutover Checklist

### 1. Deploy Infrastructure

- Create Render Postgres.
- Create Render backend from `backend/`.
- Attach the persistent disk at `/opt/render/project/src/backend/branding`.
- Create the Render cron job for FX refresh.
- Create the Vercel project from `frontend/`.

### 2. Verify Backend Boot

- Open `https://<backend>/api/health/`
- Confirm response is:

```json
{"status":"ok","database":"ok"}
```

- Confirm Render deploy logs show successful `migrate` and `collectstatic`.

### 3. Verify Frontend Wiring

- Open the Vercel frontend.
- Confirm login page loads.
- Log in with an admin or manager user.
- Confirm no CORS or CSRF errors in browser network requests.

### 4. Create And Verify Launch Users

- Verify production `system admin` login.
- Verify production `manager` login.
- Verify production `sales` login.
- Verify token generation for the production `system admin`.

Planned launch users from the current checklist:
- `Nace Martin` <`nason.s.martin@gmail.com`>
- `Evgenii Tsoi` <`evgenii.tsoi@efmpng.com`>
- `Julie-Anne Hasing` <`julie-anne.hasing@efmpng.com`>

### 5. Verify Launch Data

- Import final launch customers.
- Import final launch contacts.
- Confirm each launch customer has at least one usable contact.
- Confirm approved launch corridors are explicitly documented.
- Confirm whether any non-`POM` PNG import destinations are in launch scope.

### 6. Verify Branding

- Upload the tenant branding in `Settings -> Branding`.
- Confirm the logo renders in:
- internal UI
- public quote page
- generated PDF

### 7. Functional UAT In Deployed Environment

Run and record one successful example of each:

1. Export standard quote on an approved launch lane
2. Import standard quote on an approved launch lane
3. Import `A2D` `DG`
4. Import `A2D` `AVI` or `HVC`
5. Domestic quote if domestic is in launch scope
6. One intentionally valid SPOT-required case
7. Finalize at least one quote
8. Generate and open at least one PDF

Pass criteria for each:
- compute succeeds on the intended path
- no unwanted SPOT trigger
- `has_missing_rates` is false unless the case is intentionally incomplete/SPOT
- line items look commercially correct

### 8. FX Verification

- Confirm one active production policy only.
- Run or verify the FX refresh job.
- Confirm fresh `USD/PGK` and `AUD/PGK` rates are present.
- Capture the timestamp of the latest FX snapshot.

### 9. Final Go / No-Go

Go only if all are true:
- production env vars verified
- migrations/static build verified
- production users verified
- customer/contact import verified
- corridor list approved
- deployed UAT completed
- FX current
- scheduler verified

If any item is still open, keep status:
- `GO-LIVE HOLD`
