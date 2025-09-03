# Repository Guidelines

## Project Structure & Module Organization
- `backend/`: Django 5 project `rate_engine` with apps `accounts` and `quotes`. Core pricing logic in `backend/rate_engine/engine.py`; URLs in `backend/rate_engine/urls.py`.
- `frontend/`: Next.js (TypeScript + Tailwind) app for UI flows.
- `docs/`: Design notes and RFCs. `scripts/`: utility scripts. Local DB: `db.sqlite3` (Postgres via `DATABASE_URL`).
- Tests: Backend tests live in each app’s `tests.py`; frontend tests co-located per component when present.

## Build, Test, and Development Commands
Backend (run from `backend/`):
- Create venv: Windows `python -m venv .venv && . .venv/Scripts/activate`; Unix `python -m venv .venv && source .venv/bin/activate`.
- Install deps: `pip install django djangorestframework django-cors-headers dj-database-url psycopg[binary]`.
- Migrate DB: `python manage.py migrate`. Seed users (optional): `python manage.py create_test_users`.
- Run server: `python manage.py runserver`.
- Quick auth test: `curl -X POST http://127.0.0.1:8000/api/auth/login/ -H "Content-Type: application/json" -d '{"username":"sales_user","password":"sales_password"}'`.

Frontend (run from `frontend/`):
- Install: `npm install`. Dev server: `npm run dev` (expects backend at `http://127.0.0.1:8000`).

## Coding Style & Naming Conventions
- Python: PEP 8; modules/files use `snake_case`; prefer explicit names.
- Django: Keep views/serializers within app packages; URLs under `api/` (versionless); endpoints descriptive.
- TypeScript/React: Components `PascalCase`; hooks/utilities `camelCase`; keep files small and focused.

## Testing Guidelines
- Backend: Use Django `TestCase` per app (`tests.py`). Run with `python manage.py test`.
- Frontend: Add deterministic, co-located tests per component when needed.

## Commit & Pull Request Guidelines
- Commits: Imperative, present tense with scope, e.g., `feat(quotes): add sell mapping rules`.
- PRs: Explain intent, key changes, test coverage, and any migration steps. Link issues; add screenshots for UI changes.

## Security & Configuration Tips
- Auth: DRF TokenAuth; only login/register are open. Send `Authorization: Token <token>` for protected endpoints.
- CORS: Allowed for `localhost:3000` by default. Set `ALLOWED_HOSTS` appropriately outside dev.
- Database: Configure via `DATABASE_URL` for Postgres; keep secrets out of VCS.
