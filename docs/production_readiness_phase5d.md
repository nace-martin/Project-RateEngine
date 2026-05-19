# Phase 5D: Cloud SQL & Migration Jobs

## 1. Summary of Changes

### Cloud SQL Readiness
- **Unix Socket Support**: Updated `backend/rate_engine/settings.py` to support Google Cloud SQL's Unix socket connection strategy.
- **Dynamic Configuration**: When the `INSTANCE_CONNECTION_NAME` environment variable is present, Django automatically overrides the database host to point to `/cloudsql/<INSTANCE_CONNECTION_NAME>`. This is the recommended way for Cloud Run services to connect to Cloud SQL.
- **Protocol Compatibility**: Connection remains compatible with standard `DATABASE_URL` (host/port) for local development and other platforms (Render).

### Migration Job Architecture
- **Decoupled Migrations**: Migrations are now completely separated from the web service startup.
- **New Entrypoint**: Created `backend/entrypoint.migrate.sh` specifically for running migrations.
- **Cloud Run Job**: In production, migrations will be executed as a **Cloud Run Job** before the web service deployment. This prevents race conditions and startup timeouts during horizontal scaling.
- **Single Artifact**: The same Docker image is used for both the web service and the migration job, differing only in the execution command (`ENTRYPOINT` or `command` override).

## 2. Environment Variables (Database)

| Variable | Requirement | Purpose |
| :--- | :--- | :--- |
| `DATABASE_URL` | **Required** | Standard connection string (e.g. `postgres://user:pass@host:port/db`). |
| `INSTANCE_CONNECTION_NAME`| **Optional** | GCP Project:Region:Instance name. Triggers Unix socket connection. |

## 3. Deployment Flow (Preview)

1. **Build**: GitHub Actions builds the unified backend Docker image and pushes to Artifact Registry.
2. **Migrate**: GitHub Actions triggers a Cloud Run Job execution using the new image and `entrypoint.migrate.sh`.
3. **Deploy**: Once the migration job succeeds, GitHub Actions updates the Cloud Run web service with the new image.

## 4. Risks & Blockers
- **IAM Permissions**: The Cloud Run service account must have the `Cloud SQL Client` role.
- **Network Ingress**: Cloud SQL must be configured to allow connections from the Cloud Run service (authorized networks or VPC connector if internal only).
- **PostgreSQL Version**: Ensure Cloud SQL version matches local/dev PostgreSQL versions where practical.

## 5. Validation Performed
- Verified that `INSTANCE_CONNECTION_NAME` logic in `settings.py` correctly modifies the `HOST` field.
- Verified that local dev (SQLite) remains untouched.
- Verified `entrypoint.migrate.sh` runs the correct Django management command.
