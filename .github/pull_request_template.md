# Pull Request Title

Short, imperative summary (e.g., "feat(quotes): add sell mapping rules").

## Overview
- Why: brief intent and problem statement.
- Scope: what this PR includes/excludes.

## Changes
- Backend: models/migrations, endpoints, settings, pricing logic (e.g., `backend/rate_engine/engine.py`).
- Frontend: UI flows, routes, state, API contracts.
- Docs/Scripts: updates in `docs/` or `scripts/`.

## Testing
- Automated: how to run tests
  - Backend: `cd backend && python manage.py test`
  - Frontend: `cd frontend && npm test` (if applicable)
- Manual QA steps:
  1. Start backend: `cd backend && python manage.py runserver`
  2. Start frontend: `cd frontend && npm run dev`
  3. Verify feature: include exact steps, inputs, and expected results.

## Screenshots / Recordings
- Before/After images or short clips for UI changes.

## Security & Config
- Auth/permissions touched? DRF TokenAuth usage?
- Config/env changes (e.g., `DATABASE_URL`, CORS, `ALLOWED_HOSTS`).

## Performance & Compatibility
- Notable perf impact, queries, or payload sizes.
- Browser/device or API compatibility considerations.

## Deployment Notes
- Migrations, data backfills, feature flags, rollback plan.

## Linked Items
- Closes #123
- RFC/Docs: link to relevant notes in `docs/`.

## Checklist
- [ ] Clear title using conventional commits (scope optional)
- [ ] Tests added/updated or rationale provided
- [ ] Docs updated (README/AGENTS/docs) if needed
- [ ] No secrets committed; env/config documented
- [ ] Screenshots/recordings for UI changes
- [ ] Backward compatibility considered or migration steps noted
