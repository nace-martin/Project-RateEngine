# Phase 5B: Docker Hardening for Cloud Run Readiness

## 1. Summary of Improvements

### Backend Container
- **Multi-Stage Build**: Implemented a two-stage build process.
    - **Builder Stage**: Installs build-essential and libpq-dev, generates wheels for all dependencies.
    - **Final Stage**: Uses a slim image, installs only `libpq5` (runtime lib), and installs Python packages from pre-built wheels. This reduces attack surface and potentially image size.
- **Non-Root Execution**: Added `appuser` and `appgroup`. The container now runs as a non-privileged user.
- **Dynamic Port Support**: Modified the entrypoint to bind Gunicorn to the `${PORT}` environment variable provided by Cloud Run (defaulting to 8000 for local dev).
- **Stateless Prep**: Removed the risky `python manage.py migrate` from the startup entrypoint. Migrations are now a manual or automated "job" concern, preventing race conditions during scaling.
- **Startup Safety**: Improved logging in `entrypoint.prod.sh`.

### Frontend Container
- **Standalone Optimization**: Enabled `output: 'standalone'` in `next.config.ts`. This allows Next.js to produce a minimal production build including only the necessary files from `node_modules`.
- **Multi-Stage Build**: Optimized to copy only the standalone output, public assets, and static files.
- **Non-Root Execution**: Added `nextjs` user. The container runs as non-root.
- **Telemetry Disabled**: Explicitly disabled Next.js telemetry in both build and runtime stages.
- **Port Support**: Fully supports the `$PORT` environment variable used by Cloud Run.

## 2. Environment Variable Audit

### Backend
- **Runtime**: `PORT`, `DEBUG`, `SECRET_KEY`, `DATABASE_URL`, etc.
- **Cloud Run Implication**: All variables should be provided via Cloud Run environment configuration or Secret Manager mounts in Phase 5E.

### Frontend
- **Build-Time**: `NEXT_PUBLIC_API_BASE_URL` is baked into the JavaScript bundles during the `npm run build` step in the Dockerfile.
- **Runtime**: `PORT`, `HOSTNAME`, `NODE_ENV`.
- **Cloud Run Implication**: Because `NEXT_PUBLIC_` variables are baked at build time, separate images might be needed for Staging vs Production if the backend URLs differ, OR we must use a dynamic configuration strategy in Phase 5E/F.

## 3. Remaining Production Blockers
- **Cloud SQL Connectivity**: Connection via Unix sockets is not yet configured in Django settings.
- **Secret Manager**: Application still expects `.env` or direct env vars; needs transition to Secret Manager.
- **Media Storage**: Still uses local `/app/media`. Needs `django-storages` + GCS.
- **Migration Job**: A dedicated workflow to run migrations as a Cloud Run Job is needed.

## 4. Migration Behavior Changes
- **Old Behavior**: Entrypoint ran `python manage.py migrate --noinput`.
- **New Behavior**: Entrypoint logs that migrations are skipped.
- **Rationale**: Cloud Run instances scale horizontally. If 5 instances start at once, they all try to migrate the same DB. This is dangerous and can cause startup timeouts or DB locks.
