---
name: Feature request
about: Propose a new capability or improvement
title: "feat: <short summary>"
labels: enhancement
assignees: ""
---

## Problem & Motivation
What user need or business outcome does this address?

## Proposed Solution
High-level approach. Include affected areas:
- Backend: models/migrations, endpoints, pricing logic (`backend/rate_engine/engine.py`)
- Frontend: UI flows, components, API usage
- Docs/Scripts: updates to `docs/` or `scripts/`

## Scope
- In scope: ...
- Out of scope: ...

## API / Data Model
- New/changed endpoints and request/response shapes
- DB changes or `DATABASE_URL`/settings impacts

## UX & Acceptance Criteria
- User story(ies)
- Acceptance criteria (observable, testable)
- Screenshots/wireframes if available

## Risks & Rollout
- Backward compatibility, migrations, feature flag, rollback plan

## Testing Plan
- Backend tests (`cd backend && python manage.py test`)
- Frontend tests (`cd frontend && npm test`, if applicable)
- Manual QA steps

