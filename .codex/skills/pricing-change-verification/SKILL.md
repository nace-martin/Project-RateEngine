---
name: pricing-change-verification
description: Verify RateEngine pricing changes that can affect rates, COGS, SELL, FX, CAF, margin, GST, charge grouping, inclusion, SPOT replacement, persisted quote lines, or customer-facing totals. Use after implementing or reviewing a pricing-impacting change; do not use for documentation-only or clearly non-commercial edits.
---

# Pricing Change Verification

## Purpose

Prove the commercial effect of a pricing change instead of relying on generic test success. Verification must show what changed, what did not change, and whether any unrelated quote component moved unexpectedly.

## Trigger

Use when work changes or could change:

- rate selection or matching;
- COGS or SELL values;
- currency or FX handling;
- CAF, margin, GST, tax, or rounding;
- ProductCode or ChargeAlias behavior that affects pricing;
- charge inclusion, exclusion, grouping, or ordering;
- SPOT freight replacement;
- adapter mapping or persisted quote lines; or
- customer-facing quote totals, PDFs, or public quote output.

Do not invoke for documentation-only edits, isolated styling changes, or code changes that cannot reasonably affect commercial output.

## Required Context

Before verification:

1. Read the root `AGENTS.md` and `backend/pricing_v4/AGENTS.md`.
2. Identify the exact pricing path changed and the affected quote scenario.
3. Inspect current selector, engine, adapter, persistence, and output code relevant to the change.
4. Identify the commercial baseline that should remain unchanged unless the task explicitly changes it.

Do not invent a missing rate, rule, ProductCode, ChargeAlias, currency assumption, or expected total in order to complete verification.

## Workflow

### 1. Define the commercial scenario

Record the smallest realistic scenario that exercises the change, including as applicable:

- origin and destination;
- import/export direction;
- mode and service;
- cargo/commodity;
- weight, volume, container, or other rating inputs;
- currency;
- standard versus SPOT pricing;
- relevant ProductCodes or charge buckets; and
- customer-facing output being checked.

Prefer an existing fixture or known test scenario over constructing artificial data.

### 2. Trace the full pricing path

Trace the affected value through:

```text
normalized quote input
→ selector criteria
→ selected COGS / SELL source
→ pricing engine calculation
→ FX / CAF / margin / GST / rounding
→ adapter mapping
→ persisted quote lines
→ public / PDF / customer-facing output
```

Skip stages that genuinely do not apply, but state that they were not applicable.

### 3. Verify rate selection

Where rate selection is involved, prove:

- the intended row is selected deterministically;
- no broader fallback was introduced;
- COGS and SELL remain sourced independently;
- missing coverage remains explicit rather than silently replaced; and
- commodity or ProductCode behavior comes from canonical definitions rather than name matching or guesswork.

### 4. Verify commercial arithmetic

Check affected values individually rather than validating only the final total. As applicable, capture before/after or expected/actual values for:

```text
COGS
SELL
FX
CAF
margin
GST / tax
rounding
charge inclusion
charge grouping
bucket subtotal
quote total
```

If an item is unchanged, say so explicitly when it is commercially relevant to the change.

### 5. Verify SPOT replacement when applicable

For hybrid/SPOT scenarios, prove that the matching standard freight bucket is replaced rather than stacked. Check both persisted quote lines and customer-facing totals. Domestic freight must not be double-counted when it is part of the replaced bucket.

### 6. Run targeted automated checks

Start with the narrowest relevant checks:

- targeted Ruff for changed Python files;
- affected pricing or quote tests;
- exact selector tests where selection changed;
- focused API or end-to-end quote tests when adapter/persistence/output changed.

Run broader suites only when the scope justifies them. Do not report unrun checks as passed.

### 7. Perform an end-to-end commercial check

When the change can reach a generated quote, execute one realistic end-to-end scenario through the affected path. Confirm the resulting quote lines and total, not merely the HTTP status or absence of an exception.

## Stop Conditions

Stop the affected commercial verification and report the gap when:

- no authoritative expected rate or rule exists;
- a required ProductCode or ChargeAlias decision is unresolved;
- mixed-currency behavior cannot be proven;
- a missing rate is being hidden by fallback behavior;
- the result depends on production-only data that cannot be safely inspected; or
- unrelated commercial totals move and the cause is not understood.

Do not change commercial rules merely to make a test pass.

## Output

Report a compact commercial verification record. Example:

```text
Scenario: CAN → POM, General Cargo, standard freight
Change exercised: deterministic SELL selector ordering

Commercial result
- COGS: unchanged
- SELL: unchanged
- FX: unchanged
- CAF: unchanged
- Margin: unchanged
- GST: unchanged
- Freight subtotal: unchanged
- Quote total delta: K0.00
- Unrelated buckets changed: none

Verification
- targeted Ruff: passed
- selector tests: passed
- affected pricing tests: passed
- end-to-end quote scenario: passed

Residual risk: none identified in the exercised path
```

If values intentionally changed, state the exact before/after values and why they changed. Avoid vague conclusions such as `pricing looks correct`, `smoke tested`, or `tests pass` without the commercial evidence above.
