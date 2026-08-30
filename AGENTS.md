# RateEngine Agent Guide

## 1. Purpose & Authority

This file contains repository-wide guidance for AI agents working on RateEngine. Apply more specific nested `AGENTS.md` files when working in their directories.

Keep architecture, domain facts, operational procedures, and output templates in their existing canonical locations. Update an existing source rather than creating a competing one. Separate implemented behavior from plans and open questions.

## 2. Session Boot & Repository Navigation

At the start of repository work, run:

```bash
git status
git branch --show-current
```

Confirm the task belongs on the current branch and that existing changes are understood. Do not overwrite, discard, or absorb unrelated work. For a new concern, use a clean branch based on the intended base; do not stack on an unmerged change without explicit approval.

Then:

1. Understand the requested outcome and boundaries.
2. Inspect the relevant files and applicable nested `AGENTS.md`.
3. Consult canonical documentation for facts the change depends on.
4. Route the task to any matching verification skill in Section 6.
5. Choose the narrowest useful validation.
6. Proceed unless a hard boundary below is reached.

Technical uncertainty is a reason to investigate, trace, and test. It is not by itself a reason to stop.

Do not run Graphify, Fallow, Vulture, full builds, or full test suites as routine session boot. Use structural analysis for genuinely structural work such as module-boundary changes, major refactors, dead-code removal, or cross-domain restructuring. See `.codex/skills/structural-audit/SKILL.md`.

## 3. Repository Map

```text
RateEngine/
├── backend/
│   ├── accounts/       authentication and RBAC
│   ├── core/           shared domain and runtime services
│   ├── parties/        organizations, companies, contacts, hierarchy
│   ├── pricing_v4/     active deterministic pricing engine
│   ├── quotes/         quote lifecycle and SPE/SPOT workflows
│   ├── ratecards/      rate-card APIs
│   └── rate_engine/    Django project configuration
├── frontend/
│   ├── src/            Next.js application
│   ├── scripts/        focused executable tests
│   └── e2e/            Playwright workflows
├── docs/               architecture, operations, audits, and validation
├── scripts/            repository utilities
├── .codex/skills/      reusable task procedures
├── .github/workflows/  CI and deployment workflows
└── .github/pull_request_template.md
```

Backend tests are colocated within Django apps, typically in `tests.py` or `tests/` directories.

Start with source and documents closest to the change. Audit and roadmap documents may describe historical or proposed states; verify their status before treating them as current architecture.

## 4. Core Commercial Invariants

RateEngine is quote-first. Commercial correctness outranks apparent completeness: prefer incomplete-but-true over complete-but-wrong.

Do not invent or silently infer a rate, ProductCode, ChargeAlias, unit, currency, coverage rule, pricing rule, or inclusion decision. When authoritative evidence is insufficient:

1. preserve the evidence,
2. expose the unresolved gap,
3. avoid silent defaults or broad fallback matching,
4. stop only the affected commercial decision, and
5. report the missing decision or information.

Changes outside an explicitly approved commercial scope must not alter quote totals, tax, GST, FX, CAF, margin, grouping, inclusion, public quote output, or PDF output as a side effect.

SPOT freight uses a bucket-level override: it replaces matching standard freight, including Domestic, rather than stacking on top of it. A change to that path must prove that freight is not double-counted.

AI may extract, structure, and suggest SPOT intake data. It does not approve ProductCodes, invent commercial meaning, silently discard evidence, or finalize operator decisions.

## 5. Engineering Behaviour

- Make the smallest coherent change that solves the scoped problem.
- Inspect the active path and its callers before editing; fix root causes rather than masking symptoms with fallbacks.
- Preserve behavior outside scope and avoid drive-by refactors, formatting churn, or unrelated cleanup.
- Keep one branch/PR focused on one concern; do not mix pricing, SPOT, RBAC, CRM, data, deployment, or UI changes without explicit scope.
- Use current source and configuration as technical evidence. Do not promote stale audit snapshots or planned architecture to implemented fact.
- Update the existing appropriate document when behavior or architecture changes.
- Do not fabricate command output, tests, manual checks, or current repository facts.
- Do not stage, commit, push, merge, or modify PR state unless explicitly requested.

For hosting, storage, migrations, secrets, runtime behavior, static/media handling, or background jobs, inspect `docs/cloud_run_deployment.md`, `docs/github_actions_deployment.md`, and the active workflows before acting. Do not commit secrets or assume local production persistence.

## 6. Task Routing & Definition of Done

Before implementing or reviewing a change, classify its credible impact and load every matching task procedure. Routing is based on what the change **can affect**, not only the directory being edited.

```text
Rates / COGS / SELL / FX / CAF / margin / GST / inclusion / commercial totals
→ .codex/skills/pricing-change-verification/SKILL.md

SPE/SPOT intake / evidence / resolution / ProductCode requests / SPOT replacement
→ .codex/skills/spot-workflow-verification/SKILL.md

Quote creation / persistence / lifecycle / approval / public output / PDF / export
→ .codex/skills/quote-regression-check/SKILL.md

Seed / remediation / ProductCode / ChargeAlias / backfill / controlled data writes
→ .codex/skills/seed-data-change/SKILL.md

Module boundaries / large refactors / dead code / structural cleanup
→ .codex/skills/structural-audit/SKILL.md
```

Skills may compose. A SPOT pricing change can require SPOT, pricing, and quote regression verification. Do not skip a matching skill because another skill already ran; reuse its evidence instead of duplicating work.

For a non-matching task, explicitly record `No verification skill triggered` rather than forcing an irrelevant procedure.

Historical green CI on an old branch is not current verification. Verify the final change against a branch based on current intended `main`/base and use the final head SHA as the evidence boundary.

A task is **done** only when all applicable items are true:

1. the intended behavior is implemented and proven with concrete evidence;
2. high-risk adjacent behavior is explicitly verified unchanged;
3. commercial values are checked at the correct layer when applicable;
4. safety-critical summaries/flags are cross-checked against their underlying persisted truth where applicable;
5. targeted checks pass, and required broader CI gates are green on the final head;
6. unresolved review findings and known blockers are cleared or explicitly accepted by the user;
7. the PR accurately records scope, verification, residual risk, and rollback; and
8. when the user requested end-to-end completion, the approved change is merged to the intended base.

The `PR Readiness` workflow enforces the PR evidence contract on every PR to `main` or `develop`. It checks that verification routing is selected, the recorded final-head SHA matches the actual PR head, required-CI evidence is concrete, template placeholders are cleared, and every Definition of Done item is checked. Treat a failing readiness gate as incomplete evidence, not as permission to weaken the contract.

Do not call work done merely because code was written, one test passed, or a PR was opened.

## 7. Validation & Verification

Default to the narrowest validation that can catch a regression, then expand according to the routed skill and change surface:

```text
Backend file           → targeted Ruff check + affected Django/pytest tests
Frontend component     → relevant ESLint/typecheck + focused script or Playwright test
API behavior           → affected backend tests + exact request/path verification
Pricing/quote behavior → affected pricing/quote tests + end-to-end quote scenario
Documentation only     → path, command, link, consistency, and diff checks
```

Common verified commands include:

```bash
ruff check backend/path/to/file.py
python backend/manage.py test app.tests.TestCase.test_name
cd backend && python -m pytest path/to/test_file.py
npm --prefix frontend run lint
npm --prefix frontend run typecheck
npm --prefix frontend run test:e2e
```

Use scripts declared in `frontend/package.json` for focused frontend workflow tests. CI uses `pytest -v --tb=short`, frontend lint, TypeScript checking, and a production build; run those broader checks only when the scope justifies them.

Verification reports must say exactly what was done and what happened.

```text
GOOD
Created a standard freight quote, applied the SPOT override, and confirmed the
matching standard bucket was replaced without changing unrelated totals.

BAD
Smoke tested. Looks good. Manual testing passed.
```

If manual verification is not possible, state why, what was verified instead, and the residual risk. Use `.github/pull_request_template.md` for PR reporting.

## 8. Hard Boundaries

Require an explicit decision before proceeding when the work would:

- invent or choose an unsupported commercial rule;
- conceal a missing rate, mapping, coverage gap, mixed-currency issue, or unresolved charge;
- change quote totals or customer-facing commercial output outside approved scope;
- bypass operator review, ProductCode approval, RBAC, or audit controls;
- mutate production data or move from dry-run to write mode;
- revive deprecated quote-scoped SPOT CRUD;
- perform a destructive or difficult-to-reverse operation; or
- mix unrelated work or overwrite changes whose ownership is unclear.

For ProductCode, ChargeAlias, remediation, backfill, or comparable data writes, follow `.codex/skills/seed-data-change/SKILL.md`. Dry-run approval does not authorize apply mode.

## 9. Deeper Instructions

- `backend/pricing_v4/AGENTS.md`: pricing selection, missing rates, commodity handling, and pricing verification.
- `backend/quotes/AGENTS.md`: quote lifecycle, SPE/SPOT intake, evidence, operator control, and deprecated paths.
- `docs/ARCHITECTURE_PRINCIPLES.md`: locked architecture principles; it contains some legacy duplicated guidance and is not a replacement for this file.
- `docs/pricing_v4_overview.md` and `backend/pricing_v4/docs/`: V4 architecture and maintained module rules.
- `docs/spot-draft-quote-contract.md` and `docs/spot-draft-quote-resolve-contract.md`: Draft Quote contracts.
- `docs/spot-canonical-charge-architecture.md`: mixed proposal/history document; verify implementation in current source before relying on a section.
- `docs/tenant-model-beta.md` and current `backend/parties/` / `backend/accounts/` source: tenant and hierarchy behavior.
- `.github/workflows/ci.yml`: CI command authority.
- `.github/workflows/pr-readiness.yml`: automated PR evidence/Definition-of-Done gate.
