# GEMINI.md

## Gemini CLI Operating Rules

Gemini CLI must follow `AGENTS.md`. This file is Gemini-specific operating guidance only and must not duplicate the full constitution.

## Project Context

- Backend: Django 5.x + Django REST Framework.
- Frontend: Next.js 14+ + TypeScript + Tailwind.
- Development DB: SQLite.
- Production DB: Cloud SQL PostgreSQL.
- Deployment: Google Cloud Run (Stateless Containers).
- Migrations: Cloud Run Jobs (Separate from Web Service).
- Storage: Google Cloud Storage (Media) + WhiteNoise (Static).
- Secrets: Google Secret Manager (Transitioning).
- Main backend area: `backend/`.
- Main frontend area: `frontend/`.
- API is versioned and served through DRF.

## Deployment Guardrails

- Follow AGENTS.md as the authoritative source for deployment rules.
- Production target is Google Cloud Run using stateless containers.
- Web containers must not run database migrations on startup.
- Services must bind to the dynamic `$PORT`.
- Do not copy `.env` files or secrets into images.
- Containers should run as non-root where practical.
- Docker build/run verification is required for deployment-related PRs.
- Cloud SQL, Secret Manager, and GCS are the intended production services.

## Common Commands

Backend setup and run:

```bash
cd backend
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Frontend install and run:

```bash
cd frontend
npm install
npm run dev
```

Backend tests:

```bash
cd backend
python manage.py test
```

Frontend lint and typecheck:

```bash
cd frontend
npm run lint
npm run typecheck
```

## Scope Control

- Do not perform broad rewrites unless explicitly requested.
- Do not refactor unrelated files.
- Do not hide backend, frontend, UI, cleanup, or formatting changes inside an unrelated task.
- Keep one PR focused on one concern.

## Investigation Before Fixing

- Explain the root cause before implementing a fix.
- Do not revive deprecated, deleted, or legacy logic.
- Do not reuse legacy Spot CRUD paths.
- Stop and report ambiguity instead of guessing.

## Delivery Report

Every Gemini CLI handoff must include:

- Files changed and why.
- Tests run and results.
- Manual workflow checks run and results, or why they were not applicable.
- Any intentionally unchanged areas.

## RateEngine-Specific Reminders

- Quote workflows are critical.
- Pricing must be deterministic.
- DOC vs CRG commodity behavior matters.
- Legacy Spot CRUD is deprecated; use the SPE envelope + V4 adapter.
- Refer to `AGENTS.md` for the authoritative rules.
