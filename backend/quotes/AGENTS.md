# Quote and SPOT Agent Guide

These instructions apply within `backend/quotes/` in addition to the repository root guide.

## Active Boundaries

Quote lifecycle and SPE/SPOT workflows live here. The active design uses the SPE envelope and V4 adapter. Do not revive `QuoteSpotRate`, `QuoteSpotCharge`, quote-scoped SPOT-rate CRUD, or `/api/v3/quotes/<quote_id>/ai-intake/`.

Use these maintained contracts as the starting point:

- `docs/spot-draft-quote-contract.md`;
- `docs/spot-draft-quote-resolve-contract.md`; and
- current `spot_models.py`, `spot_views.py`, services, schemas, URLs, and tests.

`docs/spot-canonical-charge-architecture.md` mixes proposals, history, and implemented phases. Verify each relied-on section against current source.

## Evidence and Authority

- Preserve raw supplier/source evidence as ingested. Normalization and review must not rewrite evidence to make parsing easier.
- Surface parser, mapping, currency, rate, unit, and coverage uncertainty in the Draft Quote/Exception Workspace.
- AI extracts and suggests. Operators accept, map, request, ignore, edit, classify, finalize, or reopen through authorized actions.
- ProductCode request creation is not approval. Pending and rejected requests are not resolved mappings; decisions remain auditable.
- Do not auto-resolve, auto-map, auto-approve, auto-ignore, or auto-finalize unresolved commercial information.
- Respect backend RBAC and object scope for list, detail, resolve, finalize, reopen, compute, and create-quote paths. UI affordances are not authorization.
- Preserve review locks and idempotency. A finalized review must reject prohibited new mutations through the documented contract; reopening remains manager/admin controlled.

Changes to parsing, resolution, ProductCode requests, charge-line mutation, finalization, audit persistence, inclusion, or totals require explicit commercial scope. Keep read paths, suggestion generation, operator decisions, and pricing calculation visibly separated.

## Verification

Use focused quote/SPOT tests and exact status/error assertions. Cover the affected realistic flow, including as applicable:

- source ingestion and evidence returned unchanged;
- unresolved findings remaining visible;
- permitted and denied RBAC/object-scope actions;
- mapping/request/rejection/finalization/reopen transitions;
- idempotent retries and finalized-review mutation locks;
- V4 computation using the intended envelope; and
- SPOT replacement without freight duplication or unintended public-total changes.

Do not report only that an endpoint was “not 403” or that a smoke test passed. State the exact request, role, status, state transition, and commercial result.
