# RateEngine

RateEngine streamlines and automates air-freight quoting for freight forwarders.

## Technology Stack

- **Backend**: Python, Django, Django REST Framework
- **Frontend**: Next.js (React), TypeScript
- **Styling**: Tailwind CSS
- **Database**: PostgreSQL

## Architecture Overview

The project currently runs on the **Pricing V4 "Greenfield" Engine**. This architecture enforces a strict separation between Buy Rates (COGS) and Sell Rates to ensure commercial accuracy and auditability.

For detailed documentation, see:
- [**Pricing V4 Overview**](docs/pricing_v4_overview.md) (Active)
- [**Pricing V3 Overview**](docs/pricing_v3_overview.md) (Legacy/Deprecated)

### Architecture Diagram

```mermaid
graph TD
    A[API Request /api/v4/quotes/compute] --> B[Quote Orchestrator]
    B --> C{Determine Scope}
    C -- Import/Export --> D[International Engine]
    C -- Domestic --> E[Domestic Engine]
    D --> F[Resolve COGS (Buy Rates)]
    D --> G[Resolve Sell Rates]
    F --> H[Apply Margins & Strategy]
    G --> H
    H --> I[Final Quote Response]
```

## Getting Started

To run locally, use two terminals.

### Terminal 1: Backend

1.  **Change directory:**
    ```bash
    cd backend
    ```
2.  **Create and activate a virtual environment:**
    ```bash
    # Windows
    python -m venv .venv && .\\.venv\\Scripts\\activate
    # Unix/macOS
    python -m venv .venv && source .venv/bin/activate
    ```
3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
4.  **Configure database:**

    Set the `DATABASE_URL` environment variable. You can use the provided Docker Compose setup for a local PostgreSQL instance:
    ```bash
    # Unix/macOS
    ./scripts/dev_db_up.sh
    export DATABASE_URL=postgres://rateengine:rateengine@127.0.0.1:5432/rateengine

    # Windows PowerShell
    ./scripts/dev_db_up.ps1
    $env:DATABASE_URL = "postgres://rateengine:rateengine@127.0.0.1:5432/rateengine"
    ```
5.  **Run migrations and start server:**
    ```bash
    python manage.py migrate
    python manage.py runserver
    ```

### Terminal 2: Frontend

1.  **Change directory and install:**
    ```bash
    cd frontend
    npm install
    ```
2.  **Start Next.js dev server:**
    ```bash
    npm run dev
    ```

## API Usage

### Authentication

The API uses token-based authentication. Obtain a token by sending a POST request to `/api/auth/login/`:

```bash
curl -X POST http://127.0.0.1:8000/api/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"username":"sales_user","password":"sales_password"}'
```

### Quote Computation

To compute a quote, send a POST request to `/api/v4/quotes/compute/`:

```bash
curl -X POST http://localhost:8000/api/v4/quotes/compute/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Token YOUR_TOKEN" \
  -d \
  '{
    "mode": "AIR",
    "origin_airport": "POM",
    "destination_airport": "LAE",
    "incoterm": "FOB",
    "payment_term": "PREPAID",
    "is_dangerous_goods": false,
    "items": [{"weight_kg": 50}],
    "customer_id": "c7a8b9c0-d1e2-f3a4-b5c6-d7e8f9a0b1c2"
  }'
```

## Makefile Shortcuts

- `make db-up` — start Postgres via Docker Compose (prints `DATABASE_URL`).
- `make db-down` — stop Compose services.
- `make db-logs` — tail Postgres logs.
- `make backend-install` — create venv and install backend deps.
- `make backend-run` — run Django dev server.
- `make test-backend` — run backend migrations and tests.
- `make frontend-install` — install frontend deps.
- `make frontend-dev` — start Next.js dev server.

## CORS

Frontend allowed origins are `http://localhost:3000` and `http://127.0.0.1:3000` (see `backend/rate_engine/settings.py`). Update there for other hosts.

## CI: FX Refresh Workflow

- Workflow: `.github/workflows/fx-refresh.yml` calls `POST /api/fx/refresh` twice on weekdays near 9:00am Sydney (DST-safe):
  - Cron: `0 22 * * 1-5` and `0 23 * * 1-5` (UTC)
- Required GitHub Secrets:
  - `FX_REFRESH_URL` e.g., `https://yourdomain/api/fx/refresh`
  - `FX_REFRESH_TOKEN` bearer token mapped to a Manager/Finance identity

## FX Configuration & Troubleshooting

- Env vars (optional, with defaults):
  - `FX_STALE_HOURS` (default `24`): Warn if latest stored rate for a pair is older than this (hours).
  - `FX_ANOMALY_PCT` (default `0.05`): Warn if absolute change vs previous rate exceeds this fraction.
  - `BSP_FX_URL`: Override BSP rates URL if needed.
  - `FX_MID_RATES`: JSON mid-rate table for Env fallback.
- Resilience behavior:
  - BSP scrape failure falls back to Env provider automatically.
- Verify end‑to‑end locally:
  - `python manage.py fetch_fx --pairs USD:PGK,PGK:USD`

## Contributor Guidelines

### Project Structure

-   `backend/`: Django project `rate_engine` with apps `accounts`, `core`, `pricing_v2`, and `quotes`.
-   `frontend/`: Next.js (TypeScript + Tailwind) app.

### Coding Style

-   **Backend**: Follow PEP 8 with descriptive `snake_case` modules and class-based views.
-   **Frontend**: TypeScript uses ESLint and Prettier defaults. Components use `PascalCase`, and hooks/utilities use `camelCase`.

### Testing

-   **Backend**: Run `python manage.py test` before submitting backend work.
-   **Frontend**: Frontend tests live beside components.

### Commits & Pull Requests

-   Commits use imperative, scope-prefixed messages (e.g., `feat(pricing): add tier lookup`).
-   PRs summarize intent, key changes, and tests executed.
