---
name: spot-workflow-verification
description: Verify RateEngine SPE/SPOT workflow changes across intake, raw evidence, normalization, unresolved findings, operator resolution, ProductCode requests, finalization/reopen controls, V4 computation, quote creation, and granular SPOT replacement. Use after changing or reviewing SPOT workflow behavior; do not use for unrelated standard-quote work.
---

# SPOT Workflow Verification

## Purpose

Verify that a SPOT workflow change preserves evidence, operator control, auditability, state integrity, RBAC, and correct commercial calculation from intake through final quote output.

## Trigger

Use when work changes or could affect:

- supplier response intake or parsing;
- raw evidence persistence or retrieval;
- normalized SPOT charge lines;
- Draft Quote / Exception Workspace findings;
- mapping, ignore, edit, classify, request, resolve, finalize, or reopen actions;
- ProductCode request lifecycle;
- review locks or idempotency;
- SPE envelope persistence;
- V4 computation using `spot_envelope_id`;
- SPOT-to-standard pricing replacement; or
- quote creation/public output derived from SPOT.

Do not use for unrelated standard quote changes that do not touch SPE/SPOT behavior.

## Required Context

Before verification:

1. Read root `AGENTS.md` and `backend/quotes/AGENTS.md`.
2. Read the applicable maintained SPOT contracts, especially `docs/spot-draft-quote-contract.md` and `docs/spot-draft-quote-resolve-contract.md`.
3. Inspect the current source and tests for the exact workflow path being changed.
4. Identify the operator role(s), expected state transition, and intended commercial effect.
5. Confirm the branch is based on current `main` or explicitly account for branch age. Historical green CI on a stale branch is not sufficient evidence for merge.

Treat proposal/history documents as supporting context only unless current source confirms the behavior.

## Workflow

### 1. Define the exercised SPOT scenario

Describe one realistic scenario, including as applicable:

- supplier/source input;
- quote lane/mode/direction;
- relevant raw charge text;
- normalized charge values;
- unresolved findings;
- operator role;
- expected resolution action;
- expected final state; and
- trusted pricing identity expected to be replaced.

Prefer existing fixtures and known workflow tests.

### 2. Verify evidence preservation

Confirm that:

- original supplier/source evidence remains available and unchanged;
- normalization does not rewrite raw evidence;
- parser uncertainty remains visible rather than being silently cleaned up;
- mapping, currency, unit, rate, and coverage uncertainty is surfaced to the operator; and
- ignored or rejected information remains auditable where the workflow contract requires it.

### 3. Verify model and fallback assumptions

For changed lookup or fallback paths, confirm every referenced relationship/field exists on the active model before relying on it. Exercise the fallback order with the exact missing-data condition that triggers it; do not assume an earlier fallback is harmless merely because a later fallback is valid.

### 4. Verify AI versus operator authority

Confirm AI is limited to extraction, structuring, and suggestion. Prove that unresolved commercial decisions are not silently:

- auto-mapped;
- auto-approved;
- auto-ignored;
- auto-resolved; or
- auto-finalized.

Where ProductCode requests are involved, verify that request creation is not treated as approval and that pending/rejected requests remain unresolved mappings.

### 5. Verify state transitions

Exercise the affected transition and assert exact before/after state. Depending on scope, check:

```text
intake
→ normalized
→ unresolved/reviewable
→ operator decision
→ resolved
→ finalized
→ reopened (if authorized)
```

Verify finalized-review mutation locks and idempotent retries where applicable. Reopen behavior must remain manager/admin controlled according to the active contract.

### 6. Verify RBAC and object scope

For changed mutation or read paths, test the relevant permitted and denied roles. Record exact request/action and result. Do not treat frontend button visibility as authorization evidence.

### 7. Verify SPE persistence

Confirm the intended active persistence path is used and deprecated quote-scoped SPOT CRUD is not revived. Where applicable verify the correct envelope, source batch, charge line, acknowledgement, audit, journey leg, ProductCode resolution, or operator decision records are linked to the workflow.

### 8. Verify V4 computation

Confirm quote calculation uses the intended SPE envelope through `PricingServiceV4Adapter` and `spot_envelope_id`. Check that resolved operator decisions are represented correctly in the calculation input.

### 9. Prove granular SPOT replacement

For every SPOT charge that can replace standard pricing, identify and record the complete trusted commercial identity:

```text
journey_revision
leg_key
product_code
commercial_position
component
currency
```

Then prove that:

- the journey revision and leg key belong to the current trusted journey;
- the resolved ProductCode domain is compatible with that leg;
- the SPOT line replaces only the standard line with the exact compatible identity;
- unrelated standard lines remain, including lines in the same legacy bucket;
- an unresolved or stale identity cannot displace a standard line;
- duplicate SPOT identities block review rather than silently choosing one;
- no duplicate standard + SPOT charge survives for the same trusted identity; and
- customer-facing totals do not contain both standard and SPOT pricing for that same identity.

Exercise domestic on-forwarding/pre-carriage separately from the international leg when the journey contains both. A domestic SPOT charge must not replace the international freight component merely because both are historically grouped under a freight or destination bucket.

### 10. Verify quote creation and output

When the workflow reaches quote creation, inspect the resulting quote lines and customer-facing/public output. Verify the commercial result, not just HTTP success or a non-403 response.

### 11. Run targeted checks

Use the narrowest relevant quote/SPOT tests first, then expand only when required by scope. Include exact status/error assertions and state transition assertions rather than generic smoke tests. Before merge, rely on CI from the current branch head rather than historical results from an older base.

## Stop Conditions

Stop the affected verification and report the unresolved issue when:

- raw evidence has been lost or mutated;
- a commercial decision lacks operator authority;
- unresolved information is being silently accepted;
- ProductCode approval state is ambiguous;
- finalized mutation controls or RBAC cannot be proven;
- the workflow uses a deprecated SPOT persistence/API path;
- the envelope used for calculation cannot be identified;
- a fallback path dereferences a model field/relationship that is not part of the active model;
- a SPOT line lacks a trusted pricing identity but is allowed to replace standard pricing;
- duplicate pricing identities are silently accepted; or
- standard and SPOT pricing stack for the same trusted identity.

Do not weaken safety or audit controls merely to complete the scenario.

## Output

Report the verification as a workflow record. Example:

```text
Scenario: supplier air-freight reply → SPOT Draft Quote → operator resolution → final quote
Operator role: Commercial Manager

Evidence
- raw source preserved: yes
- parser uncertainty surfaced: yes
- unresolved mapping auto-resolved: no

State
- initial: REVIEW_REQUIRED
- action: operator mapped charge + finalized review
- final: FINALIZED
- retry idempotent: yes

Authority
- permitted role: exact action returned expected success
- denied role: exact action returned expected denial

Pricing
- SPE envelope used by V4: yes
- trusted identity: revision + leg + ProductCode + position + component + currency
- exact standard line replaced: yes
- unrelated same-bucket lines retained: yes
- duplicate pricing identities: none
- duplicate standard + SPOT identity: none
- unrelated quote totals changed: none

Checks
- focused SPOT tests: passed
- exact endpoint/state assertions: passed
- end-to-end quote output: passed
- branch freshness/current-head CI: passed

Residual risk: none identified in the exercised path
```

Never summarize SPOT verification only as `endpoint works`, `not 403`, `smoke test passed`, or `quote generated`.
