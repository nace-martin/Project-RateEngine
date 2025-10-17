# Repository Guidelines

Keep this quick reference close when contributing; it captures how the RateEngine repository is organized and how we expect work to flow.

## Project Structure & Module Organization
- `backend/`: Django 5 project `rate_engine` with apps `accounts`, `core`, `pricing`, and `quotes`. Pricing logic concentrates in `backend/pricing/services/pricing_service.py`; entry URLs live in `backend/rate_engine/urls.py`.
- `frontend/`: Next.js (TypeScript + Tailwind) app. Public assets sit in `frontend/public/`; shared UI primitives belong under `frontend/src/components/`.
- `docs/` collects RFCs and design notes; `scripts/` holds local automation. Use these directories before adding new tooling.
- Tests reside beside their domain: each Django app has a `tests.py`; React components keep colocated test files when present.

## Build, Test, and Development Commands
- **Backend setup** (run inside `backend/`): `python -m venv .venv && . .venv/Scripts/activate` (Windows) or `source .venv/bin/activate` (Unix), then `pip install -r requirements.txt`.
- **Database config**: export `DATABASE_URL=postgres://...` before running migrations or server processes.
- **Run API**: `python manage.py migrate`, optional `python manage.py create_test_users`, then `python manage.py runserver`.
- **Smoke login**: `curl -X POST http://127.0.0.1:8000/api/auth/login/ ...` verifies auth wiring.
- **Frontend setup** (inside `frontend/`): `npm install`, then `npm run dev` (expects API at `http://127.0.0.1:8000`).

## Coding Style & Naming Conventions
- Follow PEP 8 with descriptive `snake_case` modules, class-based views, and `api/` URL namespaces; add comments sparingly for non-obvious logic.
- TypeScript uses ESLint via `frontend/eslint.config.mjs` and Prettier defaults; components use `PascalCase`, hooks/utilities `camelCase`, Tailwind utilities first.
- Keep files focused; extract shared logic to `core` services or `frontend/src/lib/`.

## Testing Guidelines
- Django tests inherit from `TestCase` or `APITestCase` in each app’s `tests.py`; run `python manage.py test` before submitting backend work.
- Frontend tests live beside components; prefer deterministic React Testing Library specs and mock network calls.
- Target fast, isolated coverage and document any meaningful gaps in the PR description.

## Commit & Pull Request Guidelines
- Commits use imperative, scope-prefixed messages (e.g., `feat(pricing): add tier lookup`). Avoid batching unrelated changes.
- PRs summarize intent, key changes, tests executed, migrations, and linked issues; add UI screenshots or recordings when frontend behavior shifts.
- Request review only after CI and linting pass; flag follow-up tasks explicitly if deferring work.

## Security & Configuration Tips
- Auth relies on DRF TokenAuth; restrict non-auth endpoints and send `Authorization: Token <token>` for protected routes.
- Keep `ALLOWED_HOSTS` tuned per environment and never commit secrets or real database URLs.
- Postgres is mandatory via `DATABASE_URL`; update `.env.example` if configuration changes are required.
