# Phase 5A: Production Readiness & Cloud Run Architecture Audit

## 1. Audit of Current State

### Deployment & Config Files
- **Backend Dockerfile (`backend/Dockerfile`)**: Functional but lacks multi-stage optimization. Uses a root user. Hardcodes port 8000.
- **Backend Entrypoint (`backend/entrypoint.prod.sh`)**: Runs `migrate` and `collectstatic` on every startup. This is a race condition risk in auto-scaling environments like Cloud Run.
- **Frontend Dockerfile (`frontend/Dockerfile`)**: Uses Next.js standalone mode, which is excellent for Cloud Run. However, build-time environment variables are baked into the image.
- **Docker Compose**: `docker-compose.prod.yml` exists but is tailored for local production-like testing, not cloud deployment.
- **Render/Vercel Config**: `render.yaml` and Vercel-specific patterns are present but will be replaced.
- **GitHub Actions**: Strong CI foundation (`ci.yml`, `gemini-dispatch.yml`) but lacks GCP deployment flows.
- **Environment Handling**: Relies on `.env` files. Frontend environment variables are split between build-time and runtime.
- **Django Settings**: configured for Postgres but lacks production-grade storage (GCS), security headers for proxies, and structured logging.

## 2. Production Readiness Assessment

| Component | Status | Gap |
| :--- | :--- | :--- |
| **Django Backend** | Ready-ish | Needs non-root user, dynamic port, and secure proxy headers. |
| **Next.js Frontend** | Ready-ish | Environment variable handling needs clarification for multi-environment builds. |
| **Cloud SQL** | Not Ready | Connection logic (Unix sockets) and IAM authentication not yet implemented. |
| **Secret Manager** | Not Ready | Application code and deployment scripts don't yet fetch from Secret Manager. |
| **Media Storage** | **Critical Gap** | Currently uses local ephemeral storage; will lose data on container restart. |
| **Migrations** | Risk | Startup migrations can cause race conditions. Needs a dedicated Cloud Run Job. |
| **Logging** | Gap | Needs structured JSON logging for integration with Cloud Logging. |
| **Health Checks** | Basic | Needs refinement for Cloud Run's specific probe requirements. |

## 3. Risk Ranking

1.  **HIGH: Data Loss (Ephemeral Storage)**: Media files (logos, documents) are stored locally. Cloud Run instances are ephemeral.
2.  **HIGH: Migration Race Conditions**: Multiple instances trying to migrate the same DB simultaneously during a rollout.
3.  **MEDIUM: Hardcoded Ports**: Entrypoint hardcodes `8000`, while Cloud Run injects `$PORT`.
4.  **MEDIUM: Hardcoded Hostnames**: `frontend/next.config.ts` has a hardcoded Render URL for image optimization.
5.  **MEDIUM: Security Headers**: Missing `SECURE_PROXY_SSL_HEADER` and `USE_X_FORWARDED_HOST`, which are required when running behind Cloud Run's GFE.
6.  **LOW: Large Image Sizes**: Docker images are not currently optimized for fast startup/pull times.

## 4. Recommended Architecture

### Web Services
- **Services**: Two Cloud Run services (Backend and Frontend).
- **Ingress**: External HTTP(S) Load Balancer (optional but recommended for global scale) or Cloud Run direct ingress.

### Data & Storage
- **Database**: Cloud SQL PostgreSQL. Connection via Cloud SQL Auth Proxy or Unix Sockets.
- **Storage**: Google Cloud Storage (GCS).
    - `django-storages[google]` for Media files.
    - WhiteNoise for Static files (simpler than GCS for static).
- **Secrets**: Google Secret Manager. Mounted as volumes or injected as env vars via deployment scripts.

### Execution Strategy
- **Migrations**: Cloud Run Job triggered by GitHub Actions *before* the main service update.
- **Static Files**: `collectstatic` run during Docker build phase.

## 5. Phase 5 Implementation Roadmap

- **5B: Docker Hardening**: Multi-stage builds, non-root users, dynamic `$PORT` support, and startup optimization.
- **5C: Django Production Settings**: Configure `django-storages`, WhiteNoise, structured logging, and production security headers.
- **5D: Cloud SQL & Migration Jobs**: Implement connection logic and create a Cloud Run Job for migrations.
- **5E: Secret Manager Integration**: Update logic to validate/fetch secrets and ensure no local `.env` dependency in production.
- **5F: GHA Cloud Run Deployment**: Build and push to Artifact Registry; deploy to Cloud Run with tag-based rollouts.
- **5G: Observability**: Configure Cloud Logging, Error Reporting, and custom health check endpoints.
- **5H: Cleanup**: Remove `render.yaml`, Vercel configs, and legacy local-production scripts.

## 6. Files to Change (Forecast)

- `backend/Dockerfile`
- `backend/entrypoint.prod.sh`
- `backend/rate_engine/settings.py`
- `backend/requirements.txt`
- `frontend/Dockerfile`
- `frontend/next.config.ts`
- `.github/workflows/deploy.yml` (New)
