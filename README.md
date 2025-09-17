# Project-RateEngine

## RateEngine MVP

RateEngine streamlines and automates air-freight quoting for freight forwarders.

> For a detailed breakdown of status, architecture, and roadmap, see the [Project Brief](./docs/PROJECT_BRIEF.md).

## Getting Started (Quick)

- Backend: `cd backend && python -m venv .venv && . .venv/Scripts/activate` (Windows) or `cd backend && python -m venv .venv && source .venv/bin/activate` (Unix); then `pip install -r requirements.txt`; set `DATABASE_URL=postgres://...`; run `python manage.py migrate && python manage.py runserver`.
- Frontend: `cd frontend && npm install && npm run dev` (expects API at `http://127.0.0.1:8000`).
- Full contributor guide: see [AGENTS.md](./AGENTS.md).

## Technology Stack

- Backend: Python, Django, Django REST Framework
- Frontend: Next.js (React), TypeScript
- Styling: Tailwind CSS
- Database: PostgreSQL (required via `DATABASE_URL`)

## Detailed Setup

To run locally, use two terminals.

### Terminal 1: Backend

1. Change directory:
   ```bash
   cd backend
   ```
2. Create and activate a virtual environment:
   ```bash
   # Windows
   python -m venv .venv && .\\.venv\\Scripts\\activate
   # Unix/macOS
   python -m venv .venv && source .venv/bin/activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. (Recommended) Create a .env from example and configure DB:
   ```bash
   # From repo root
   copy .env.example .env   # Windows
   # or
   cp .env.example .env     # Unix/macOS
   # then edit .env and set DATABASE_URL
   ```
   The backend automatically loads variables from `.env` at startup.

   SECRET_KEY note:
   - Always set `SECRET_KEY` in production.
   - If omitted locally, the app uses a dev-only insecure default and logs a warning.
   - Generate a strong key: `python -c "import secrets; print(secrets.token_urlsafe(50))"`.

   Alternatively, set the environment variable directly:
   ```bash
   # Windows (PowerShell)
   $env:DATABASE_URL = "postgres://USER:PASSWORD@HOST:PORT/DBNAME"
   # Unix/macOS
   export DATABASE_URL="postgres://USER:PASSWORD@HOST:PORT/DBNAME"
   ```
5. Run migrations and start server:
   ```bash
   python manage.py migrate
   python manage.py runserver
   ```
   Backend runs at http://127.0.0.1:8000 (admin: /admin).

### Terminal 2: Frontend

1. Change directory and install:
   ```bash
   cd frontend
   npm install
   ```
2. Start Next.js dev server:
   ```bash
   npm run dev
   ```
   Frontend runs at http://localhost:3000.
   If needed, copy `frontend/.env.local.example` to `frontend/.env.local` to set `NEXT_PUBLIC_API_BASE`.

## Verify Backend & CORS

- Login (token issuance):
  ```bash
  curl -X POST http://127.0.0.1:8000/api/auth/login/ \
    -H "Content-Type: application/json" \
    -d '{"username":"sales_user","password":"sales_password"}'
  ```
- Compute quote (requires token):
  ```bash
  curl -X POST http://127.0.0.1:8000/api/quote/compute \
    -H "Authorization: Token YOUR_TOKEN" -H "Content-Type: application/json" \
    -d '{"org_id":1,"origin_iata":"SYD","dest_iata":"POM","shipment_type":"EXPORT","service_scope":"AIRPORT_AIRPORT","pieces":[{"weight_kg":"10"}]}'
  ```
- CORS: Frontend allowed origins are `http://localhost:3000` and `http://127.0.0.1:3000` (see `backend/rate_engine/settings.py`). Update there for other hosts.

### API Error Format

- All error responses use the DRF convention: a JSON object with a single `detail` key.
- Examples:
  - `{"detail": "Invalid credentials"}` (401)
  - `{"detail": "Invalid JSON"}` (400)
  - `{"detail": "Forbidden"}` (403)
  - Validation errors from DRF serializers may return a field-keyed object; handle those per field.

### Authorization Policy

- Authentication: DRF TokenAuth is required for protected endpoints (e.g., `/api/quote/compute`).
- Compute permissions:
  - `manager` and `finance` roles may quote for any organization.
  - `sales` may quote only for organizations where they have an explicit membership (`accounts.OrganizationMembership`) with `can_quote=True`.
  - Unauthorized org access returns `403` with `{ "detail": "Forbidden for organization" }`.
  - You can adjust this policy in `QuoteComputeView` if your org/user model differs.

## Docker Compose (Postgres) and Test Runner

- Start Postgres via Docker Compose from repo root:
  - Unix/macOS: `./scripts/dev_db_up.sh`
  - Windows PowerShell: `./scripts/dev_db_up.ps1`
  - Then set `DATABASE_URL` as printed, e.g.:
    - Unix/macOS: `export DATABASE_URL=postgres://rateengine:rateengine@127.0.0.1:5432/rateengine`
    - Windows PowerShell: `$env:DATABASE_URL = "postgres://rateengine:rateengine@127.0.0.1:5432/rateengine"`

- Run backend tests:
  - Unix/macOS: `./scripts/test_backend.sh`
  - Windows PowerShell: `./scripts/test_backend.ps1`
  - Direct `python manage.py test` uses an in-memory SQLite database (see `backend/rate_engine/settings.py`), so your dev Postgres stays untouched.

### Seed Sample Routes\n\nUse the targeted management commands when you want lane data without loading the full sandbox dataset.\n\n- python manage.py seed_bne_to_pom � seeds the AUD BUY ratecard for BNE?POM (including lane breaks and surcharges).\n\n### Makefile Shortcuts (repo root)

- `make db-up` — start Postgres via Docker Compose (prints `DATABASE_URL`).
- `make db-down` — stop Compose services.
- `make db-logs` — tail Postgres logs.
- `make backend-install` — create venv and install backend deps.
- `make backend-run` — run Django dev server.
- `make test-backend` — run backend migrations and tests.
- `make frontend-install` — install frontend deps.
- `make frontend-dev` — start Next.js dev server.

Notes:
- Legacy `rate_engine` models have been retired; the managed schema now lives across the `core`, `organizations`, `pricing`, and `quotes` apps.
- The `accounts` app (including `OrganizationMembership`) is managed by Django and will be migrated automatically.

## CI: FX Refresh Workflow

- Workflow: `.github/workflows/fx-refresh.yml` calls `POST /api/fx/refresh` twice on weekdays near 9:00am Sydney (DST-safe):
  - Cron: `0 22 * * 1-5` and `0 23 * * 1-5` (UTC)
- Request body (example):
  - `{"pairs":["USD:PGK","PGK:USD","AUD:PGK","PGK:AUD"],"provider":"bsp_html"}`
- Required GitHub Secrets:
  - `FX_REFRESH_URL` e.g., `https://yourdomain/api/fx/refresh`
  - `FX_REFRESH_TOKEN` bearer token mapped to a Manager/Finance identity
- Auth header:
  - The workflow uses `Authorization: Bearer <token>`. If calling Django directly, switch to `Authorization: Token <key>` (DRF TokenAuth), or place the API behind a gateway that translates Bearer→Token.
- Manual run: trigger via “Run workflow” (workflow_dispatch) to verify 200 OK and summary payload.

## FX Configuration & Troubleshooting

- Env vars (optional, with defaults):
  - `FX_STALE_HOURS` (default `24`): Warn if latest stored rate for a pair is older than this (hours). Included as `fx_age_hours` in API response when available.
  - `FX_ANOMALY_PCT` (default `0.05`): Warn if absolute change vs previous rate exceeds this fraction (e.g., `0.05` = 5%).
  - `BSP_FX_URL`: Override BSP rates URL if needed.
  - `FX_MID_RATES`: JSON mid-rate table for Env fallback, e.g. `{ "USD": { "PGK": 3.75 }, "PGK": { "USD": 0.2667 } }`.

- Resilience behavior:
  - BSP scrape failure (network/HTML) falls back to Env provider automatically and logs a clear WARN.
  - Staleness and anomaly checks run for both API and CLI refresh paths.

- Verify end‑to‑end locally:
  - Backend deps: `cd backend && pip install -r requirements.txt`
  - Migrations: `python manage.py migrate`
  - CLI (BSP, default): `python manage.py fetch_fx --pairs USD:PGK,PGK:USD`
  - CLI (force fallback): set `BSP_FX_URL=http://127.0.0.1:1` to simulate failure; rerun and observe WARN + ENV usage.
  - API: `curl -X POST "$API/fx/refresh" -H "Authorization: Token <key>" -H "Content-Type: application/json" -d '{"pairs":["USD:PGK","PGK:USD"],"provider":"bsp_html"}'`
  - Tests: `pytest -q` (ensure `DATABASE_URL` points to Postgres).


