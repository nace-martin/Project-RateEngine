# GitHub Copilot Instructions

Follow the repository-wide guidance in `AGENTS.md` and any nested `AGENTS.md` that applies to the edited path.

Before implementing or reviewing a change, use the task-routing table in `AGENTS.md` Section 6. When a matching `.codex/skills/*/SKILL.md` procedure exists, follow its verification contract as shared repository guidance rather than duplicating it in Copilot instructions.

Current navigation:

- `backend/pricing_v4/` is the active deterministic pricing engine.
- `backend/quotes/` owns quote lifecycle and SPE/SPOT workflows.
- `backend/accounts/` and `backend/parties/` own authentication, RBAC, customers, and hierarchy.
- `frontend/src/` is the Next.js application.
- `.github/workflows/ci.yml` is the CI command authority.

Prefer targeted tests and checks for the affected module, then expand according to the routed verification procedure and credible impact. Do not use removed pricing implementation paths. Consult current source and maintained documentation rather than copying architecture facts into this adapter.
