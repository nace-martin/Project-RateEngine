# Phase 5E: Secret Manager Integration

## Overview
This phase prepares RateEngine for secure production secret management using Google Secret Manager (GSM). It introduces a flexible `SecretResolver` that allows production environments to reference secrets via a special URI scheme while maintaining zero-config compatibility for local development.

## Secret Resolution Strategy
The `SecretResolver` (implemented in `backend/core/secrets.py`) acts as a proxy for environment variables. It detects strings starting with `sm://` and attempts to resolve them using the Google Cloud Secret Manager API.

### Supported URI Formats
1.  **Short Format (Default Project):** `sm://SECRET_NAME`
    *   Resolves the `latest` version of `SECRET_NAME`.
    *   Requires `GOOGLE_CLOUD_PROJECT` environment variable to be set.
2.  **Versioned Short Format:** `sm://SECRET_NAME/VERSION`
    *   Resolves a specific version (e.g., `sm://DJANGO_SECRET_KEY/2`).
3.  **Full Resource Path:** `sm://projects/PROJECT_ID/secrets/SECRET_NAME/versions/VERSION`
    *   Used for cross-project secret access or explicit resource mapping.

### Local Development / Fallback
If an environment variable value does **not** start with `sm://`, the resolver returns it as a plain string. This ensures that existing `.env` files and standard environment variables continue to work without modification or GCP credentials.

## Protected Production Settings
The following settings have been updated to use the secret resolver:
*   `DJANGO_SECRET_KEY`
*   `DATABASE_URL`
*   `ALLOWED_HOSTS` (List resolved via `sm://`)
*   `CORS_ALLOWED_ORIGINS` (List)
*   `CSRF_TRUSTED_ORIGINS` (List)
*   `INSTANCE_CONNECTION_NAME` (Cloud SQL)
*   `GS_BUCKET_NAME` (Cloud Storage)
*   `GEMINI_API_KEY` (AI Intake)

## IAM Requirements
For the resolver to function in production (e.g., on Cloud Run), the service account running the application must have the following IAM role:
*   `roles/secretmanager.secretAccessor`

## Security Principles
1.  **No Leaks:** Secret values are never logged. The resolver only logs the *attempt* to resolve a specific secret name.
2.  **Fail Fast:** In production, if an `sm://` reference cannot be resolved (due to missing permissions, network errors, or non-existent secrets), the application will raise a `RuntimeError` and fail to start, preventing an insecure or broken state.
3.  **Lazy Loading:** The Google Cloud SDK is only imported and initialized if an `sm://` secret is actually requested, keeping the local environment lean.
