# Repository Guidelines

## Project Structure & Module Organization
- `backend/`: Django 5.x project `rate_engine` with apps `accounts`, `quotes`. Core pricing logic lives in `backend/rate_engine/engine.py` and URLs in `backend/rate_engine/urls.py`.
- `frontend/`: Next.js (TypeScript + Tailwind) app for UI flows.
- `docs/`: Design notes and RFCs.
- `scripts/`: Utility scripts.
- `db.sqlite3`: Local dev DB (Postgres supported via `DATABASE_URL`).

## Build, Test, and Development Commands
Backend (from `backend/`):
- Create venv: `python -m venv .venv && . .venv/Scripts/activate` (Windows) or `source .venv/bin/activate` (Unix)
- Install deps: `pip install django djangorestframework django-cors-headers dj-database-url psycopg[binary]`
- Migrate DB: `python manage.py migrate`
- Seed users (optional): `python manage.py create_test_users`
- Run server: `python manage.py runserver`
- Call auth: `curl -X POST http://127.0.0.1:8000/api/auth/login/ -H "Content-Type: application/json" -d '{"username":"sales_user","password":"sales_password"}'`
- Quote compute: `curl -X POST http://127.0.0.1:8000/quote/compute -H "Authorization: Token <token>" -H "Content-Type: application/json" -d '{"origin_iata":"BNE","dest_iata":"POM","direction":"EXPORT","scope":"INTERNATIONAL","audience":"PGK_LOCAL","sell_currency":"PGK","pieces":[{"weight_kg":"120"}]}'`

Frontend (from `frontend/`):
- Install: `npm install`
- Dev server: `npm run dev` (expects backend at `http://127.0.0.1:8000`)

## Coding Style & Naming Conventions
- Python: Follow PEP 8; modules and files use `snake_case`. Prefer explicit names over abbreviations.
- Django: Views/serializers in app packages; URLs under `api/` are versionless for now. Keep endpoints descriptive.
- TypeScript/React: Components use `PascalCase`; hooks/utilities use `camelCase`. Keep files small and focused.

## Testing Guidelines
- Backend: Use Django `TestCase` in each app’s `tests.py`. Run with `python manage.py test`.
- Frontend: Add tests co-located per component when needed. Aim for clear, deterministic tests.

## Commit & Pull Request Guidelines
- Commits: Imperative, present tense. Scope briefly: `feat(quotes): add sell mapping rules`.
- PRs: Describe intent, key changes, test coverage, and any migration steps. Link issues and add screenshots for UI.

## Security & Configuration Tips
- Auth: DRF TokenAuth enabled; only login/register are open. Send `Authorization: Token <token>` for protected endpoints.
- CORS: Allowed for `localhost:3000` by default.
- Database: Override via `DATABASE_URL` (e.g., Postgres). Keep secrets out of VCS.
- Hosts: Set `ALLOWED_HOSTS` in non-dev environments.
