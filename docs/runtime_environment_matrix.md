# Runtime Environment Matrix

## Backend Environment Variables
| Variable | Source | Purpose |
| :--- | :--- | :--- |
| `DJANGO_DEBUG` | Literal (`False`) | Enforces production mode. |
| `DJANGO_SECRET_KEY` | Secret Manager (`sm://...`) | Django encryption key. |
| `DATABASE_URL` | Secret Manager (`sm://...`) | PostgreSQL connection string (using Unix socket). |
| `INSTANCE_CONNECTION_NAME` | GitHub Secret / Env | Required for Cloud SQL Auth Proxy. |
| `ALLOWED_HOSTS` | Secret Manager (`sm://...`) | Comma-separated allowlist of domains. |
| `CORS_ALLOWED_ORIGINS` | Secret Manager (`sm://...`) | Frontend domain(s). |
| `GS_BUCKET_NAME` | Secret Manager (`sm://...`) | GCS bucket for media. |
| `GEMINI_API_KEY` | Secret Manager (`sm://...`) | AI extraction key. |

## Frontend Environment Variables
| Variable | Source | Purpose |
| :--- | :--- | :--- |
| `NEXT_PUBLIC_API_BASE_URL` | Runtime Env | Public URL of the backend API. |
| `NEXT_PUBLIC_BACKEND_HOSTNAME` | Runtime Env | Used for Next.js Image optimization patterns. |

## Migration Job Environment Variables
| Variable | Source | Purpose |
| :--- | :--- | :--- |
| `DATABASE_URL` | Secret Manager (`sm://...`) | Access to the production database. |
