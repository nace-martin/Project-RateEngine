# Vercel + Render Beta Deploy

Last updated: 2026-03-20

This is the exact beta deployment shape for the current repo:

- frontend: `Vercel`
- backend API: `Render Web Service`
- database: `Render Postgres`
- scheduler: `Render Cron Job`

Use this with:
- [production-cutover-checklist.md](/C:/Users/commercial.manager/dev/Project-RateEngine/docs/production-cutover-checklist.md)
- [go-live-status-tracker.md](/C:/Users/commercial.manager/dev/Project-RateEngine/docs/go-live-status-tracker.md)
- [beta-readiness-efm.md](/C:/Users/commercial.manager/dev/Project-RateEngine/docs/beta-readiness-efm.md)

## Architecture

- Vercel hosts the Next.js app from `frontend/`
- Render hosts the Django API from `backend/`
- Render Postgres provides the production database
- Render Cron refreshes FX on schedule
- uploaded branding assets are stored on a Render persistent disk mounted at `backend/branding`

## Repo Support Added

The repo now includes:

- [render.yaml](/C:/Users/commercial.manager/dev/Project-RateEngine/render.yaml)
- public health endpoint: `/api/health/`
- environment flags for serving uploaded branding media and Django static files in the beta API service

## Vercel Setup

Create a new Vercel project and point it at this repo.

Recommended settings:

- Framework preset: `Next.js`
- Root Directory: `frontend`
- Install Command: default
- Build Command: default
- Output Directory: default
- Node version: `18`

Required environment variables:

- `NEXT_PUBLIC_API_BASE_URL=https://<your-render-backend>.onrender.com`

Optional later:

- custom frontend domain such as `beta.rateengine.app`

## Render Setup

### Option A: Blueprint

Use the repo-level [render.yaml](/C:/Users/commercial.manager/dev/Project-RateEngine/render.yaml).

It creates:

- `rateengine-beta-db`
- `rateengine-beta-api`
- `rateengine-beta-fetch-fx`

Values you must provide during setup:

- `ALLOWED_HOSTS`
- `CORS_ALLOWED_ORIGINS`
- `CSRF_TRUSTED_ORIGINS`
- `FRONTEND_BASE_URL`
- `GEMINI_API_KEY`

The FX cron job inherits the core Django env vars from the backend service, so you do not have to enter them twice.

### Option B: Manual

If you do not want Blueprint sync, create the same resources manually:

1. Render Postgres
2. Render Web Service for `backend/`
3. Render Cron Job for FX refresh
4. Persistent disk mounted to `/opt/render/project/src/backend/branding`

## Render Web Service Settings

Use these exact settings for the backend:

- Environment: `Python`
- Root Directory: `backend`
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

- Health Check Path:

```text
/api/health/
```

- Persistent Disk:
  - Mount Path: `/opt/render/project/src/backend/branding`
  - Size: `1 GB`

## Render Backend Environment Variables

Required:

- `DATABASE_URL`
- `DJANGO_SECRET_KEY`
- `DJANGO_DEBUG=false`
- `ALLOWED_HOSTS`
- `CORS_ALLOWED_ORIGINS`
- `CSRF_TRUSTED_ORIGINS`
- `FRONTEND_BASE_URL`
- `GEMINI_API_KEY`
- `USE_X_FORWARDED_PROTO=true`
- `SERVE_STATIC_FILES=true`
- `SERVE_MEDIA_FILES=true`

Recommended values:

- `ALLOWED_HOSTS=<your-render-backend>.onrender.com`
- `CORS_ALLOWED_ORIGINS=https://<your-vercel-project>.vercel.app`
- `CSRF_TRUSTED_ORIGINS=https://<your-vercel-project>.vercel.app,https://<your-render-backend>.onrender.com`
- `FRONTEND_BASE_URL=https://<your-vercel-project>.vercel.app`

If you later add custom domains, append them instead of replacing the existing values.

## Render Cron Job

Current repo-supported recurring job:

```bash
python manage.py fetch_fx --pairs USD:PGK,PGK:USD,AUD:PGK,PGK:AUD
```

Recommended schedule for beta:

```text
0 7 * * 1-5
```

Notes:

- this runs at 07:00 UTC on weekdays unless you change the cron timezone behavior in Render
- the repo does not currently contain the older `cleanup_stale_drafts` or `archive_quotes` commands, so do not configure those jobs yet

## First Deploy Checklist

1. Deploy the Render database
2. Deploy the Render backend
3. Confirm `https://<backend>/api/health/` returns `{"status":"ok","database":"ok"}`
4. Deploy the Vercel frontend
5. Confirm login works from Vercel to Render
6. Create or verify the three EFM beta users
7. Upload EFM branding in `Settings -> Branding`
8. Confirm logo renders in:
   - internal UI
   - public quote page
   - PDF quote
9. Run:
   - one standard quote
   - one SPOT quote
   - one public quote page
   - one PDF export

## Important Beta Notes

- uploaded branding files are now expected to live on the Render persistent disk at `backend/branding`
- the API service is configured to serve media and Django static files directly for beta simplicity
- this is acceptable for a small beta, but a more production-hardened setup should later move static/media behind a dedicated asset strategy

## Go / No-Go For Beta

Do not invite beta users until all are true:

- backend health endpoint is green
- frontend can authenticate against backend
- branding logo renders from the deployed backend
- FX cron is configured
- EFM users can log in
- one quote flow and one SPOT flow succeed end-to-end
