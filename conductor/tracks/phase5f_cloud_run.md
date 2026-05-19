# Phase 5F Implementation Plan: Cloud Run Deployment Automation

## Objective
Fully automate the deployment of RateEngine to Google Cloud Run via GitHub Actions, establishing a secure, stateless, and rollback-safe production environment while removing legacy Render/Vercel configurations.

## Scope & Impact
This phase focuses entirely on deployment infrastructure. It does not alter business logic or core product features. Local development will remain unaffected. The changes will establish a professional CI/CD pipeline using Google Cloud best practices.

## Implementation Steps

### 1. GitHub Actions Workflow Creation
**File:** `.github/workflows/deploy-production.yml`
**Strategy:** Implement a unified pipeline that enforces a safe deployment sequence:
1.  **Auth & Build:** Authenticate via Workload Identity Federation, build backend/frontend images, and push to Google Artifact Registry (GAR).
2.  **Migration Job:** Update and execute a Cloud Run Job (`rateengine-migrate`) using the new backend image and `entrypoint.migrate.sh`.
3.  **Backend Deploy:** Only if migrations succeed, deploy the Cloud Run Web Service (`rateengine-backend`). Configure Cloud SQL unix sockets, Secret Manager references, and health checks.
4.  **Frontend Deploy:** Deploy the Next.js Cloud Run Web Service (`rateengine-frontend`), injecting the backend API URL as a build arg / env var.

### 2. Deployment Architecture Configuration
*   **Backend Service:**
    *   Uses `--add-cloudsql-instances` to mount the Unix socket.
    *   Sets `--service-account` to a dedicated least-privilege SA.
    *   Maps secrets using `--set-secrets` pointing to GSM.
    *   Configures liveness probe targeting `/api/health/`.
*   **Frontend Service:**
    *   Sets `--service-account` to a dedicated least-privilege SA.
    *   Passes `NEXT_PUBLIC_API_BASE_URL` securely.

### 3. Cleanup Legacy Configurations
*   **Remove:** `render.yaml`
*   **Modify:** `frontend/next.config.ts` - Remove the hardcoded Render hostname in `remotePatterns`. Replace it with an environment variable (`NEXT_PUBLIC_BACKEND_HOSTNAME`) or a wildcard configuration suitable for Cloud Run.
*   **Deprecate:** Rename or add a deprecation notice to `docs/vercel-render-beta-deploy.md`.

### 4. Documentation
Create the following required documents in `docs/`:
*   `cloud_run_deployment.md`: Details the GCP architecture (Cloud Run, Cloud SQL, Secret Manager, IAM roles).
*   `github_actions_deployment.md`: Explains the workflow, required GitHub secrets (e.g., `GCP_WORKLOAD_IDENTITY_PROVIDER`, `GCP_SERVICE_ACCOUNT`), and triggers.
*   `runtime_environment_matrix.md`: Maps out exactly which environment variables and secrets are required for the Backend, Frontend, and Migration Job.

## Verification
*   Confirm GitHub Actions syntax is valid via `actionlint` or manual inspection.
*   Verify `next.config.ts` builds successfully without Render dependencies.
*   Ensure no real secrets are hardcoded in the workflow files.
