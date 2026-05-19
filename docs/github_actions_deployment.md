# GitHub Actions Deployment Workflow

## Workflow Overview
The unified deployment workflow (`.github/workflows/deploy-production.yml`) automates the build, push, and deployment of RateEngine to Google Cloud.

## Triggers
*   **Manual Trigger:** `workflow_dispatch` (allows manual production releases).
*   **Automatic Trigger (Optional):** Push to `main` (can be configured).

## Safe Deployment Sequence
To prevent downtime and ensure data integrity, the workflow follows a strict sequence:
1.  **Build & Push:** Simultaneously build backend and frontend images and push to Google Artifact Registry.
2.  **Run Migrations:** Update and execute the Cloud Run Job `rateengine-migrate`. If this step fails, the workflow terminates, and the web services are NOT deployed.
3.  **Deploy Backend:** Deploy the `rateengine-backend` service. Cloud Run performs a rolling update; if the new revision fails to start (e.g., due to bad config), it will not receive traffic.
4.  **Deploy Frontend:** Deploy the `rateengine-frontend` service, pointing it to the updated backend.

## Required GitHub Secrets
The following secrets must be configured in the GitHub repository:
*   `GCP_PROJECT_ID`: Your Google Cloud Project ID.
*   `GCP_WORKLOAD_IDENTITY_PROVIDER`: Full resource name of the WIF provider.
*   `GCP_SERVICE_ACCOUNT`: The email of the Service Account used for deployment (e.g., `github-deployer@...`).
*   `GAR_LOCATION`: Region for Artifact Registry (e.g., `us-central1`).
*   `CLOUD_RUN_REGION`: Region for Cloud Run (e.g., `us-central1`).
*   `CLOUD_SQL_INSTANCE_NAME`: Full connection name (`PROJECT:REGION:INSTANCE`).
*   `BACKEND_SERVICE_NAME`: (e.g., `rateengine-backend`).
*   `FRONTEND_SERVICE_NAME`: (e.g., `rateengine-frontend`).
*   `MIGRATION_JOB_NAME`: (e.g., `rateengine-migrate`).
