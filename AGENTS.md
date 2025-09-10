# Repository Guidelines

## Project Structure & Module Organization
- `backend/`: Django 5 project `rate_engine` with app `accounts`. Core pricing logic in `backend/rate_engine/engine.py`; URLs in `backend/rate_engine/urls.py`.
- `frontend/`: Next.js (TypeScript + Tailwind) UI. Static assets in `frontend/public/`.
- `docs/`: Design notes and RFCs. `scripts/`: local utility scripts.
- Tests: Backend tests live in each app’s `tests.py`; frontend tests are co‑located per component when present.

## Build, Test, and Development Commands
Backend (from `backend/`):
- Create venv: Windows `python -m venv .venv && . .venv/Scripts/activate`; Unix `python -m venv .venv && source .venv/bin/activate`.
- Install deps: `pip install -r requirements.txt`.
- Configure DB (required): set `DATABASE_URL` (Postgres). Windows `set DATABASE_URL=postgres://...`; Unix `export DATABASE_URL=postgres://...`.
- Migrate/seed: `python manage.py migrate`; optional `python manage.py create_test_users`.
- Run API: `python manage.py runserver`.
- Smoke login: `curl -X POST http://127.0.0.1:8000/api/auth/login/ -H "Content-Type: application/json" -d '{"username":"sales_user","password":"sales_password"}'`.

Frontend (from `frontend/`):
- Install: `npm install`. Dev server: `npm run dev` (expects backend at `http://127.0.0.1:8000`).

## Coding Style & Naming Conventions
- Python: PEP 8; files/modules use `snake_case`; explicit, descriptive names.
- Django: Views/serializers within app packages; endpoints under `api/` (no version prefix); descriptive URL patterns.
- TypeScript/React: Components `PascalCase`; hooks/utils `camelCase`; keep files small. ESLint config at `frontend/eslint.config.mjs`.

## Testing Guidelines
- Backend: Write `TestCase` classes in each app’s `tests.py`. Run with `python manage.py test`.
- Frontend: Add deterministic, co‑located tests per component when meaningful.

## Commit & Pull Request Guidelines
- Commits: Imperative, present tense with scope, e.g., `feat(accounts): add token login`.
- PRs: State intent, key changes, tests, migrations; link issues. Include screenshots for UI changes.

## Security & Configuration Tips
- Auth: DRF TokenAuth; only login/register are open. Use `Authorization: Token <token>` for protected endpoints.
- CORS: Allowed for `localhost:3000` by default; set `ALLOWED_HOSTS` appropriately outside dev.
- Database: Postgres via `DATABASE_URL` is required; do not commit secrets.
