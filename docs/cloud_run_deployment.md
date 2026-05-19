# Cloud Run Deployment Architecture

## Overview
RateEngine is deployed as a suite of stateless containers on Google Cloud Run. This architecture ensures high availability, automatic scaling, and simplified infrastructure management.

## Components

### 1. Backend Web Service (`rateengine-backend`)
*   **Platform:** Cloud Run (fully managed).
*   **Runtime:** Python 3.11 (Django + DRF).
*   **Connectivity:**
    *   **Cloud SQL:** Connects via a Unix socket mounted at `/cloudsql/<INSTANCE_CONNECTION_NAME>`.
    *   **Secret Manager:** Consumes secrets using the `sm://` URI convention resolved at runtime.
*   **IAM:** Runs under a dedicated Service Account (`rateengine-backend-sa`) with `roles/secretmanager.secretAccessor` and `roles/cloudsql.client`.

### 2. Frontend Web Service (`rateengine-frontend`)
*   **Platform:** Cloud Run (fully managed).
*   **Runtime:** Node.js 20 (Next.js Standalone).
*   **Connectivity:** Communicates with the backend via the public API URL.
*   **IAM:** Runs under a dedicated Service Account (`rateengine-frontend-sa`).

### 3. Database Migration Job (`rateengine-migrate`)
*   **Platform:** Cloud Run Job.
*   **Runtime:** Backend Docker image with `entrypoint.migrate.sh`.
*   **Execution:** Executed by GitHub Actions prior to updating the backend web service.

## Security Hardening
*   **Least Privilege:** Each service runs under its own Service Account with minimum required permissions.
*   **Secrets:** No secrets are stored in environment variables in plain text; they are either Secret Manager references or injected via GitHub Secrets.
*   **Non-Root Users:** Both backend and frontend containers run as non-root users (`appuser` and `nextjs`).
*   **Health Checks:** Liveness and startup probes ensure that only healthy revisions receive traffic.
