---
name: quote-regression-check
description: Run a focused RateEngine regression check when a change may affect quote creation, calculation, lifecycle, persisted charge lines, approvals, public quote rendering, PDFs, exports, or adjacent quote workflows. Use after implementing or reviewing quote-impacting changes; do not use for isolated documentation or unrelated infrastructure work.
---

# Quote Regression Check

## Purpose

Catch quote workflow regressions that targeted unit tests can miss. Verify the smallest set of realistic quote scenarios needed to prove the changed path works without disturbing adjacent commercial behavior.

## Trigger

Use when work changes or could affect:

- quote creation or edit flows;
- calculation inputs or outputs;
- quote lifecycle states;
- pricing adapters or persisted charge lines;
- customer/party selection required for quoting;
- approvals, finalization, reopen, or review behavior;
- public quote rendering;
- quote PDFs or exports;
- standard versus SPOT quote integration; or
- frontend workflow steps that can alter quote data or completion.

Do not invoke for documentation-only edits or changes with no credible path to quote behavior.

## Required Context

Before regression checking:

1. Read root `AGENTS.md` and any nested guide for the affected domain.
2. Identify the exact user workflow changed.
3. Identify one primary scenario that must work and adjacent scenarios most likely to regress.
4. Inspect existing tests, fixtures, scripts, and Playwright flows before inventing new verification steps.
5. Record whether the requested change is supposed to alter commercial outputs.
6. Identify any lifecycle decision that depends on aggregate/summary fields and the underlying persisted records that should agree with them.

## Workflow

### 1. Define the regression surface

Classify the change by affected layer:

```text
input / UI
API / serializer / schema
quote lifecycle
pricing calculation
persistence
approval / authorization
public rendering
PDF / export
```

Select only the scenarios needed to cover the changed layer and its immediate downstream effects.

### 2. Establish a primary scenario

Use a realistic quote path with concrete inputs. Record as applicable:

- customer/party;
- origin/destination;
- direction;
- mode/service;
- cargo/commodity;
- rating inputs;
- standard or SPOT pricing;
- expected quote state; and
- expected commercial output.

Prefer repository fixtures or known working scenarios.

### 3. Verify quote creation and persistence

Confirm the quote can be created through the affected path and that key inputs persist correctly. Inspect resulting quote/charge data rather than relying only on a successful response.

Where the change does not affect creation, verify the nearest relevant lifecycle entry point instead.

### 4. Verify calculation behavior

If pricing can be affected, invoke the `pricing-change-verification` skill and use its commercial evidence rather than duplicating its workflow here.

At minimum confirm that unrelated quote buckets do not change unexpectedly.

### 5. Verify lifecycle behavior

Exercise the states touched by the change. Depending on scope, verify transitions such as:

```text
draft
→ calculated/reviewable
→ approved/finalized
→ public/customer-visible
```

Include reopen, rejection, expiry, or other states only when the change touches them.

For safety-critical lifecycle gates, do not trust only a denormalized summary flag. Cross-check the underlying latest-version records that represent the same truth. Examples include missing-rate totals versus persisted `QuoteLine.is_rate_missing` values. A stale aggregate must not permit a transition that the underlying records should block.

When the same lifecycle rule can be reached through multiple entry points, prefer enforcing the invariant in the shared state/service layer and keep API/UI checks as additional guardrails rather than the sole protection.

### 6. Verify permissions when applicable

For changes involving approvals, mutations, customer visibility, or object scope, test at least the relevant allowed and denied roles. Record the exact action and outcome.

### 7. Verify customer-facing output

When the path can reach customer output, inspect the actual rendered result:

- charge descriptions;
- quantities/units;
- currencies;
- subtotals/totals;
- inclusion/exclusion behavior;
- public quote page;
- PDF/export content when affected.

Do not assume persistence correctness guarantees rendering correctness.

### 8. Verify adjacent scenarios

Choose a small number of high-risk neighbors based on the change. Examples:

- import versus export;
- standard versus SPOT;
- missing-rate versus fully rated;
- stale aggregate versus consistent persisted records;
- General Cargo versus affected special cargo;
- permitted versus denied role;
- quote with versus without optional charge/service.

Do not turn every regression check into the full product test matrix.

### 9. Run targeted automation

Use existing focused tests/scripts first. Depending on scope, run:

- targeted backend tests;
- relevant frontend lint/typecheck;
- focused workflow script;
- focused Playwright flow;
- exact API request verification.

Run broader suites only when the changed surface is broad enough to justify them. Before merge, treat CI from the current branch head as the authoritative broad regression result.

### 10. Compare intended versus unintended change

Finish by separating:

```text
INTENDED
behavior or commercial outputs deliberately changed by this task

UNCHANGED
important adjacent behavior explicitly verified as stable

UNVERIFIED
anything material that could not be exercised
```

## Stop Conditions

Stop and report the affected regression check when:

- the expected commercial result is not authoritative;
- required fixture/test data is misleading or conflicts with active rules;
- quote creation succeeds but persisted/commercial output is inconsistent;
- a lifecycle summary flag conflicts with the underlying persisted records and the safe interpretation is unclear;
- unrelated quote totals change without explanation;
- permission behavior conflicts with the active RBAC contract; or
- customer-facing output differs from persisted quote data and the reason is unknown.

Do not rewrite expected values just to match new output unless the task explicitly authorizes the commercial change.

## Output

Report a concise regression matrix. Example:

```text
Primary scenario
- POM import standard quote: passed
- quote created and inputs persisted: passed
- calculation: passed
- finalization: passed
- public quote output: passed

Lifecycle consistency
- aggregate completeness flag: consistent
- persisted missing-rate lines: none
- shared finalization invariant: enforced

Adjacent checks
- SPOT quote path: unchanged / passed
- missing-rate behavior: unchanged / passed
- denied approval role: correctly blocked

Commercial impact
- intended total changes: none
- unexpected total changes: none

Automation
- targeted backend tests: passed
- focused frontend workflow: passed
- current-head CI: passed

Unverified
- PDF export not affected by changed path; not run

Residual risk
- none identified in exercised workflows
```

Avoid conclusions such as `all good`, `basic regression passed`, or `tests green` without naming the workflows and commercial effects actually checked.
