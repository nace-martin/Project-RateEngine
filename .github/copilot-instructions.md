# Copilot / AI Agent Instructions — Project RateEngine

Short, focused guidance for AI coding agents working on this repository.

1. Big picture
   - Backend: Django REST API in `backend/` (project: `rate_engine`). Core apps: `accounts`, `core`, `pricing_v2`, `quotes`, `ratecards`, `services`.
   - Frontend: Next.js + TypeScript in `frontend/` (dev server: `npm run dev`).
   - V3 rating core: deterministic, pure-function pipeline. See `backend/pricing_v2/dataclasses_v3.py` and `backend/pricing_v2/pricing_service_v3.py` for the orchestration and pure functions.
   - Important API endpoints: `/api/v3/quotes/compute/` (V3 engine), `/api/auth/login/` (token auth), `/api/fx/refresh` (FX refresh webhook used by CI).

2. Typical developer workflows (explicit commands)
   - Backend (PowerShell):
     - Activate venv: `& .\.venv\Scripts\Activate.ps1`
     - Install deps: `pip install -r requirements.txt` (run from `backend/` or use `make backend-install`).
     - Start local Postgres for integration tests: `./scripts/dev_db_up.ps1` then set env: `$env:DATABASE_URL = 'postgres://rateengine:rateengine@127.0.0.1:5432/rateengine'`.
     - Run migrations & server: `python manage.py migrate` and `python manage.py runserver`.
     - Run backend tests: `python manage.py test` or `make test-backend`.
   - Frontend:
     - `cd frontend && npm install`
     - `cd frontend && npm run dev`

3. Project-specific conventions and patterns
   - Pricing V3: implemented as an orchestrator that normalizes a QuoteContext, rates against buy sources, maps buy=>sell, applies tax/fx and rounds. Look at the `V3 Architecture` diagram in `README.md` for flow.
   - Pure functions and dataclasses: `dataclasses_v3.py` contains the domain dataclasses; `pricing_service_v3.py` contains the business logic. When changing behavior, prefer small, well-tested pure functions.
   - Tests: backend tests are colocated under each app (e.g., `backend/pricing_v2/tests/`). Target tests at the app/function level to avoid long test runs.
   - Settings: `backend/rate_engine/settings.py` uses SQLite by default for quick local runs; CI and Compose use `DATABASE_URL` for Postgres. `AUTH_USER_MODEL = 'accounts.CustomUser'` is in use.
   - Auth: Token auth (`rest_framework.authentication.TokenAuthentication`). Include header: `Authorization: Token <token>`.

4. Integration points & external dependencies
   - Postgres via `docker-compose.yml` (service name: `postgres`). Use `make db-up`/`make db-down` or `./scripts/dev_db_up.ps1` for local DB.
   - FX provider: BSP scraper and environment fallbacks. Look at `README.md` section "FX Configuration & Troubleshooting" and the management command `fetch_fx` (used for local verification).
   - CI automation: `.github/workflows/fx-refresh.yml` calls `/api/fx/refresh`. Relevant secrets: `FX_REFRESH_URL`, `FX_REFRESH_TOKEN`.

5. Files and locations an agent should inspect first
   - `README.md` (project overview & make targets)
   - `backend/pricing_v2/pricing_service_v3.py` and `backend/pricing_v2/dataclasses_v3.py` (core logic)
   - `backend/quotes/views.py` (API wiring for quotes)
   - `backend/rate_engine/settings.py` (env-driven config, CORS, auth model)
   - `docker-compose.yml` and `Makefile` (local dev and compose targets)
   - `frontend/package.json` and `frontend/README.md` (frontend commands)

6. Quick debugging hints
   - For Django errors, run: `python manage.py runserver` and check logs; for migrations, run `python manage.py migrate --plan` then `migrate`.
   - To run a focused backend test: `python manage.py test pricing_v2.tests.test_pricing_service_v3` (adjust test path as needed).
   - To reproduce FX-related behavior locally: `python manage.py fetch_fx --pairs USD:PGK,PGK:USD` (see README examples).

7. Style & PR expectations
   - Backend: follow PEP-8 and keep small pure functions in `pricing_v2`. Use descriptive snake_case names.
   - Frontend: follow existing ESLint/TypeScript patterns; run `npm run lint`.
   - Commits: imperative, scope-prefixed (e.g., `feat(pricing): add tier lookup`). PR description should summarize intent, files changed, and tests run.

8. What *not* to change without human review
   - Core V3 flow structure in `pricing_v2` (normalization → buy → map_to_sell → tax_fx_round) — refactors are OK but preserve observable behavior and add tests.
   - `AUTH_USER_MODEL` changes or global settings affecting DB field types without migration planning.

If anything in these notes is unclear or you want more detail about a specific area (tests, FX, or the V3 pipeline), tell me which section to expand.  
