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
