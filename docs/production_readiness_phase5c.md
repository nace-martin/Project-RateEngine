# Phase 5C: Django Production Settings for Cloud Run

## 1. Summary of Improvements

### Security Hardening
- **SSL/HTTPS**: Enabled `SECURE_SSL_REDIRECT` and strict cookie settings (`SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`) for production.
- **HSTS**: Implemented HTTP Strict Transport Security with a 1-year duration in production.
- **Proxy Awareness**: Configured `SECURE_PROXY_SSL_HEADER` to correctly handle HTTPS termination at the Google Front End (GFE).
- **Headers**: Enforced `X-Frame-Options: DENY`, `SECURE_CONTENT_TYPE_NOSNIFF: True`, and strict `SECURE_REFERRER_POLICY`.
- **Environment Awareness**: Strict validation of `DJANGO_SECRET_KEY`, `ALLOWED_HOSTS`, and `DATABASE_URL` in production mode.

### Stateless Asset Management
- **Static Files (WhiteNoise)**: Integrated WhiteNoise to serve static assets directly from the Django container with compression and caching headers. This removes the need for a separate Nginx container or GCS-backed static serving.
- **Media Files (GCS Prep)**: Prepared `django-storages` integration for Google Cloud Storage. Media handling is now "GCS-ready" via the `USE_GCS` and `GS_BUCKET_NAME` environment variables.

### Observability
- **Structured Logging**: Implemented `python-json-logger` for non-DEBUG environments. Logs are now emitted as structured JSON, making them immediately searchable and actionable in Google Cloud Logging and Error Reporting.
- **Log Scoping**: Refined log levels for Django core, security, and application-specific modules.

## 2. Environment Variable Audit (Production)

| Variable | Requirement | Purpose |
| :--- | :--- | :--- |
| `DJANGO_DEBUG` | Optional (False) | Toggles production/dev mode. |
| `DJANGO_SECRET_KEY` | **Required** | Cryptographic signing key. |
| `ALLOWED_HOSTS` | **Required** | List of valid hostnames for the service. |
| `DATABASE_URL` | **Required** | PostgreSQL connection string. |
| `CORS_ALLOWED_ORIGINS`| **Required** | Frontend domain allowlist. |
| `CSRF_TRUSTED_ORIGINS`| **Required** | Domain allowlist for CSRF protection. |
| `USE_X_FORWARDED_PROTO`| Optional | Set `True` for Cloud Run HTTPS awareness. |
| `USE_GCS` | Optional | Set `True` to enable Google Cloud Storage. |
| `GS_BUCKET_NAME` | Required if GCS | GCS bucket for media uploads. |
| `SERVE_STATIC_FILES`| Optional | Toggle for legacy static serving (default: False in prod). |
| `SERVE_MEDIA_FILES` | Optional | Toggle for legacy media serving (default: False in prod). |

## 3. Risks & Compatibility
- **CORS/CSRF**: Correct origins must be configured in `CORS_ALLOWED_ORIGINS` and `CSRF_TRUSTED_ORIGINS` once the Cloud Run URLs are known.
- **Secret Management**: Currently expects raw environment variables; will transition to Secret Manager in Phase 5E.

## 4. Validation Performed
- Verified `python manage.py collectstatic` with WhiteNoise compression.
- Verified that local development (SQLite/Debug) still functions without modification.
- Audited security headers using Django's security checklist logic.
