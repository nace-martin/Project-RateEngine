# Summary

-

## Root Cause / Rationale

-

## Scope of Change

-

## Changed Files

- `path`: reason

## What Was Intentionally Not Changed

-

## Verification Routing

Mark every verification skill whose trigger matches the credible impact of this PR. Multiple skills may apply.

- [ ] `pricing-change-verification`
- [ ] `spot-workflow-verification`
- [ ] `quote-regression-check`
- [ ] `seed-data-change`
- [ ] `structural-audit`
- [ ] No verification skill triggered — explain why:

Routing rationale:

-

## Verification

Automated:

- Command/check and exact result

Workflow / commercial evidence:

- Scenario exercised and exact observed result, or `Not applicable`
- Important adjacent behavior explicitly verified unchanged

Manual:

- Action and observed result, or why manual verification was not possible

Final-head evidence:

- Final head SHA:
- Required CI gates on that SHA:

## Intended / Unchanged / Unverified

**INTENDED**

-

**UNCHANGED**

-

**UNVERIFIED**

-

## Risk

- Known risks and residual uncertainty

## Rollback

- Safe revert or recovery approach

## Screenshots / Recordings

Required when the UI changed; otherwise write `Not applicable`.

-

## Conditional Impact

Complete these when the PR affects the corresponding area; otherwise write `Not applicable`.

### Commercial Impact

- Effect on totals, tax/GST, FX/CAF, margin, ProductCode mapping, inclusion, grouping, public output, or operator decisions

### Data Impact

- Data created, updated, deleted, migrated, seeded, or backfilled; include dry-run/apply controls

### Audit Impact

- Effect on who/what/when/why evidence and review history

## Documentation Consolidation Check

- [ ] Existing authority was updated instead of duplicated.
- [ ] Implemented behavior, planned work, and open questions remain distinct.
- [ ] Governance, architecture, commands, and links reference current files.

## Definition of Done

- [ ] Intended behavior is proven, not merely implemented.
- [ ] High-risk adjacent behavior is protected by evidence.
- [ ] Applicable commercial/safety invariants were checked at the correct layer.
- [ ] Required CI gates are green on the final head SHA.
- [ ] No unresolved review findings or unexplained blockers remain.
- [ ] Scope, residual risk, and rollback are accurately recorded.

## Reviewer Checklist

- [ ] This PR addresses one isolated concern.
- [ ] It does not revive deprecated paths or hide unresolved commercial gaps.
- [ ] Relevant automated checks and real user workflows were verified.
- [ ] Rollback and residual risk are clear.
