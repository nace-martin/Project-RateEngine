# AGENTS.md

## Master Constitution

This file is the canonical governance source for Codex, Gemini CLI, and any other AI agent working in the RateEngine repository.

Agent-specific files such as `CODEX.md`, `GEMINI.md`, or tool-specific local instructions may add execution details, but they must not contradict, duplicate, or weaken this constitution.

If another agent instruction file conflicts with this file, this file wins.

If both `AGENT.md` and `AGENTS.md` exist, `AGENTS.md` is canonical. `AGENT.md` should either be removed or reduced to a short pointer back to `AGENTS.md`.

---

## Operating Order

After reading this file, and before inspecting further repository files or generating an implementation plan, agents must follow this order:

1. Run the mandatory Git pre-flight commands.
2. Confirm the current branch and working tree state.
3. Read the Graphify report/wiki before source-code exploration.
4. Run Fallow/Ruff/Vulture baselines only when required by the Fallow Baseline Rule.
5. Inspect source files.
6. Produce the implementation plan.
7. Wait for explicit user approval before modifying files, unless the user already gave clear implementation instructions.

Do not skip this order because the requested task looks small. Most agent-caused damage in this project has come from dirty branches, stale context, stacked PRs, and silent scope expansion.

---

## Source of Truth

**LEGACY SPOT-RATE CRUD IS DEPRECATED. ALL NEW WORK MUST USE THE SPE ENVELOPE AND V4 ADAPTER.**

Do not create duplicate sources of truth.

If governance, architecture, workflow, or review guidance already exists, update the existing file in place. Do not create parallel files, duplicate PR templates, overlapping architecture documents, or competing implementation plans.

Before creating a new document, check whether an existing document should be updated instead.

---

## Mandatory Git Pre-Flight

Before reading repository source files or preparing an implementation plan, agents must run and report the output of:

```bash
git status
git branch --show-current
git log --oneline -5
```

If the working tree is dirty, the branch is unexpected, or the recent commit history suggests stacked work, stop and report the situation before continuing.

Do not assume the current branch is correct.

Do not start new work from a dirty or ambiguous branch.

---

## PR Discipline

One PR must map to one isolated concern.

Agents must not:

* hide scope expansion inside a small request
* perform drive-by refactors
* perform unrelated styling churn
* perform opportunistic cleanup
* mix unrelated backend, frontend, UI, refactor, cleanup, data, and documentation changes in one PR
* combine database migrations with unrelated frontend changes
* combine parser changes with unrelated ProductCode changes
* combine RBAC cleanup with pricing, ProductCode, or quote-calculation behavior

Every PR must clearly list:

* every changed file
* why each file changed
* what was intentionally left unmodified
* verification commands run
* manual verification performed
* residual risks

If behavior is ambiguous, stop and report the ambiguity instead of guessing.

---

## Stacked PR Protocol

Do not build a new phase on top of an unmerged PR unless the user explicitly approves stacked work.

Before starting a new phase, confirm:

```text
current branch
base branch
open PR dependency, if any
whether the new branch is cleanly based on main
whether the working tree is clean
```

If a PR is accidentally stacked, stop and report it.

Do not continue adding commits to a stacked branch unless the user explicitly approves.

---

## Stop Conditions

Stop and report instead of implementing when:

* source-of-truth documents conflict
* hierarchy assumptions conflict
* deployment assumptions conflict
* pricing behavior is ambiguous
* ProductCode mapping is ambiguous
* ChargeAlias mapping is ambiguous
* parser output lacks enough source evidence
* the task requires mutating legacy SPOT models
* the required workflow cannot be tested
* the change would mix unrelated concerns
* the current branch is dirty
* the current branch is unexpectedly stacked
* the requested implementation would alter quote totals as a side effect
* the change requires guessing business rules
* the change would silently hide missing rates, missing coverage, or unmapped charges

When in doubt, stop and ask for a decision.

---

## Root-Cause Discipline

Always identify the root cause before implementing a fix.

Agents must not:

* patch symptoms while leaving the broken path active
* add fallback logic to hide a defect
* revive deleted, deprecated, or legacy code paths unless explicitly instructed
* add broad matching logic just to make one test pass
* silently change customer-facing behavior while fixing an internal bug

Prefer deleting dead code over patching around it.

Any removed legacy behavior must be called out in the PR.

---

## Current Highest-Risk Workflows

The current highest-risk workflows are:

1. SPOT Intake / Draft Quote / Exception Workspace / ProductCode governance
2. ProductCode / ChargeAlias / seed-data mapping
3. V4 pricing adapter and quote calculation
4. Public quote rendering and customer-facing quote output
5. Quote-derived CRM logging

Changes in these areas require:

* explicit scope confirmation
* contract-first design where applicable
* read/write separation
* targeted regression tests
* manual workflow verification
* no drive-by cleanup
* no broad fallback logic
* no hidden quote-total changes

---

## Quote-First Product Rule

RateEngine is quote-first.

The following workflows are commercially critical:

```text
quote creation
quote calculation
quote finalization
pricing breakdowns
SPOT overlays
public quote rendering
quote-derived CRM logging
```

Rules:

* UI changes must preserve quote workflow integrity.
* CRM changes must stay within CRM unless explicitly requested.
* Do not introduce global CRM navigation, buttons, banners, or shortcuts unless explicitly requested.
* Before changing quote creation, SPOT, pricing, FX, CAF, GST, margin, charge grouping, public quote rendering, or CRM quote logging, inspect the full workflow end-to-end.
* Do not change quote behavior as a side effect of parser, RBAC, cleanup, styling, seed-data, or documentation work.

---

## Quote Totals Integrity

Quote totals are sacred.

Any change that affects the following is commercially critical:

```text
quote totals
tax
currency
FX
CAF
GST
margin
charge grouping
SPOT overlay
included/excluded line status
public quote rendering
customer-facing PDF output
```

Agents must:

* identify the exact calculation path before changing code
* add or update regression tests
* verify at least one end-to-end quote scenario
* document before/after behavior
* confirm whether customer-facing totals changed

Never change customer-facing totals as a side effect of parser, UI, RBAC, cleanup, or seed-data work.

---

## No Broadening Fixes

Do not fix a failing case by broadening matching logic unless the broader behavior is explicitly intended, reviewed, and tested.

Forbidden broadening examples:

* wildcard ChargeAlias matching
* fallback ProductCode guesses
* defaulting missing rates to local SELL
* treating unknown units as `per shipment`
* grouping charges by display label instead of canonical ProductCode
* accepting mixed currencies without warning
* treating `DOC` and `CRG` as interchangeable
* auto-mapping unknown supplier labels because they look similar
* suppressing warnings because they are inconvenient

Unknown is better than wrong.

Visible incomplete coverage is better than hidden false completeness.

---

## RBAC Organization Hierarchy

The final ERP hierarchy is:

```text
Organization
└── OperatingEntity
    └── Branch
        └── Department
```

Canonical hierarchy:

* Organization: `Express Freight Management` only
* OperatingEntity: `EFM PNG`, `EFM Australia`, `EFM Fiji`, `EFM Solomon Islands`
* Branch: `Port Moresby`, `Lae`, `Brisbane`, `Suva`, `Honiara`
* Department: `Air Freight`, `Sea Freight`, `Customs`, `Transport`

Rules:

* `EFM PNG`, `EFM Australia`, `EFM Fiji`, and `EFM Solomon Islands` are not canonical Organization rows.
* `EAC` / `EFM Express Air Cargo` is legacy Air Freight wording only.
* Historical Quote/SPOT rows that still reference legacy hierarchy records are `DEV_TEST_LEGACY`.
* Do not build historical Quote/SPOT backfill tooling as part of RBAC hierarchy cleanup.
* Do not mutate pricing, ProductCode, rating, or quote calculation behavior as part of RBAC hierarchy cleanup.
* RBAC work must not become pricing work.
* Pricing work must not become RBAC work.

---

## Verification Rule

Tests passing is not enough.

Agents must run relevant automated checks for the change and manually verify affected workflow-critical paths.

Manual verification must include concrete user-path steps.

Good examples:

```text
Created a SPOT envelope from fixture X.
Opened the Exception Workspace.
Confirmed pending ProductCode appears.
Confirmed approved ProductCode status appears.
Confirmed ignored item remains auditable.
Confirmed quote totals did not change unexpectedly.
Confirmed public quote rendering still groups charges correctly.
```

Bad examples:

```text
Manually checked UI.
Verified workflow.
Looks good.
Smoke tested.
```

If a workflow cannot be manually verified, explain why and list the residual risk.

---

## Fallow Baseline Rule

Fallow, Ruff, and Vulture baselines are used as pre-flight audit evidence. They are not automatic permission to change code.

Run the Fallow baseline before:

* audit work
* cleanup work
* refactor work
* structural feature work
* multi-domain changes
* dead-code removal
* duplicate-code reduction

For a narrow one-file bugfix, small copy edit, test-only correction, or minor syntax fix, do not run the full baseline unless the user asks or the change touches structural boundaries.

When required, run from the project root:

```bash
npx fallow --format json
npx fallow dead-code --format json
npx fallow dupes --format json
npx fallow health --format json
```

Rules:

* Run this baseline only during the pre-flight planning phase.
* Do not re-run Fallow during iterative code-writing turns, minor syntax tweaks, or active debugging loops within the same branch.
* Re-run the baseline only if the target operational module changes, files across different domains are altered, or core structural boundaries are modified.
* Treat all Fallow output strictly as audit evidence.
* Do not delete or alter code automatically based on Fallow findings.
* If Fallow is not installed or fails, stop and report the failure.
* Do not continue with cleanup, refactor, or feature work until the baseline issue is resolved or explicitly waived by the user.
* Report analysis findings before changing files.
* Flag dead code, unused exports, duplicate logic, complexity hotspots, dependency/import issues, and legacy quote/SPOT/`INCOMPLETE` status code before proposing structural changes.
* Run backend checks separately with Ruff and Vulture where relevant, because Fallow is primarily optimized for JavaScript and TypeScript.

Backend examples:

```bash
ruff check backend
vulture backend
```

Do not stage, commit, or push files unless explicitly instructed.

---

## SPOT Intake & Exception Workspace Bounded Rules

The SPOT intake pipeline is a Draft Quote Assistant.

It is not an autonomous decision engine.

Supplier quotes are inconsistent and may arrive as:

```text
emails
PDFs
Excel tables
merged cells
awkward spacing
mixed currencies
unclear charge labels
conditional notes
rate validity clauses
density ratios
agent-specific formats
```

The parser is expected to be imperfect.

The system must therefore preserve uncertainty and route it to the operator.

Rules:

* Provide draft suggestions only.
* Do not auto-resolve parsing ambiguities.
* Do not infer missing structural elements without evidence.
* Do not hide parser, mapping, rate, or coverage gaps through fallback logic.
* Preserve the gap visibly and route it to operator review.
* Preserve raw source evidence exactly as ingested.
* Do not alter raw input payloads during normalization, audit, or review phases.
* Surface data uncertainties clearly in the Exception Workspace.
* Never automate acceptance, rejection, mapping, or ignoring of charge anomalies without explicit user action.
* If a coverage component is missing, preserve that gap visibly to trigger manual rate sourcing.
* Do not auto-fill missing components with local SELL rates.

The core principle:

```text
Never silently invent or silently discard commercially relevant information.
```

---

## SPOT Change Classification

Allowed without additional approval:

* read-only diagnostics
* contract validation
* UI display of existing backend state
* tests for existing documented behavior
* adapter fixes that preserve existing contract semantics
* documentation updates that clarify existing approved behavior

Requires explicit approval:

* parser behavior changes
* ProductCode request creation changes
* ChargeAlias mapping changes
* resolve/sync behavior changes
* SPEChargeLineDB mutation behavior
* quote finalization rules
* changes that affect totals, inclusion/exclusion, or customer-facing quote output
* changes to ProductCode approval/rejection flows
* changes to audit persistence

Forbidden unless explicitly requested:

* autonomous learning
* silent fallback mappings
* broad wildcard ChargeAlias creation
* legacy `QuoteSpotRate` / `QuoteSpotCharge` revival
* auto-accepting unresolved charges
* auto-ignoring unresolved charges
* auto-mapping unresolved charges
* bypassing ProductCode admin review
* mutating raw intake evidence to make downstream parsing easier

---

## Active SPOT Persistence & API Surface

Use the following as the active SPOT persistence models:

```text
SpotPricingEnvelopeDB
SPESourceBatchDB
SPEChargeLineDB
SPEAcknowledgementDB
DraftQuoteDecisionDB
```

Use the following as the active SPOT API surface:

```text
/api/v3/spot/analyze-reply/
/api/v3/spot/envelopes/*
```

Use `PricingServiceV4Adapter` with `spot_envelope_id` for hybrid quote calculation.

Do not reintroduce:

```text
QuoteSpotRate
QuoteSpotCharge
quote-scoped SPOT-rate CRUD flows
/api/v3/quotes/<quote_id>/ai-intake/
```

Legacy SPOT CRUD is dead. Do not bring it back wearing a fake moustache.

---

## ProductCode, ChargeAlias, & Seed-Data Governance

Data operations affecting ProductCode and ChargeAlias mappings must follow defensive programming boundaries.

This is especially important within the Air Freight domain.

Rules:

* Use a strict two-phase execution loop.
* Phase 1 must be a dry-run validation check.
* Phase 2 may commit writes only after explicit human review of dry-run output.
* Do not invent ProductCode fields.
* Do not overwrite existing base rates.
* Do not mutate active `SpotPricingEnvelopeDB` rows during seed-data cleanup.
* Do not mutate general quote calculation behavior during data seeding.
* Do not create broad wildcard mappings.
* Do not collapse commercially distinct charge labels into one ProductCode without evidence.
* Do not create duplicate ProductCode requests if an active matching request already exists.

If an incoming charge label maps to multiple ambiguous ProductCodes or ChargeAliases, fail gracefully and flag the line as an unmapped exception.

Do not guess.

---

## ProductCode Request Lifecycle

ProductCode request creation is not ProductCode approval.

Preserve this separation:

```text
Operator Request
↓
Admin Review
↓
Approve / Reject
↓
Operator Resume / Apply Approved ProductCode
↓
Quote Finalization
```

Rules:

* Do not create ProductCodes directly from operator resolve actions unless the scoped task explicitly says so.
* Do not bypass admin review.
* Do not treat pending ProductCode requests as approved mappings.
* Do not treat rejected ProductCode requests as resolved.
* Approved ProductCodes may be surfaced to the operator for acceptance or mapping.
* Rejected ProductCode requests must provide a clear path to retry, map to existing ProductCode, or classify appropriately.
* ProductCode decisions must remain auditable.

---

## V4 Pricing Adapter & Calculation Boundaries

The V4 engine execution path is commercially critical and must remain deterministic.

Rules:

* Domestic freight must emit `is_rate_missing=True` if no valid COGS or SELL row matches the parameters.
* All rate lookups must be deterministic:

```python
.order_by("-valid_from", "-updated_at", "-id").first()
```

* Maintain strict separation between `DOC` and `CRG` commodity codes.
* `DOC` means documents with no commercial value and flat-rate evaluation.
* `CRG` means cargo requiring the full audit matrix.
* Informational, conditional, or supplemental charges must live outside core quote calculation logic.
* Serialize informational or conditional elements as metadata only unless the scoped task explicitly changes inclusion behavior.
* Do not aggregate informational metadata into primary cumulative quote totals.
* If pricing behavior is ambiguous or source data is incomplete, fail clearly through missing-rate or incomplete-coverage signals instead of guessing.

---

## SPOT Overlay Rules

SPOT freight charges must replace standard freight charges for the same leg/route.

They must never append on top of standard freight for the same bucket.

This applies to all shipment types, including Domestic.

The canonical merge strategy is:

```text
bucket-level override
```

Domestic no longer uses append.

If a change touches SPOT overlay behavior, agents must verify:

* standard freight is replaced, not duplicated
* domestic behavior follows bucket-level override
* quote totals do not double-count freight
* public quote output remains commercially correct

---

## AI Intake Rules

The live AI intake pipeline is:

```text
Raw
↓
Normalized
↓
Audit
↓
Quote Input
```

Rules:

* AI extraction supports SPOT intake.
* Final quote pricing belongs to the deterministic V4 engine.
* AI must not approve ProductCodes.
* AI must not finalize quotes.
* AI must not silently ignore commercial evidence.
* AI must not invent commercial data.
* AI must not autonomously learn from corrections without an explicitly approved controlled-learning workstream.
* Future learning must be auditable, reviewable, and human-approved.

---

## Deployment Rules

Deployment target must be confirmed from the current deployment documentation before changing hosting, storage, migrations, environment variables, secrets, or runtime behavior.

Do not assume any specific platform unless the active deployment documentation confirms it.

Do not assume:

```text
Google Cloud Run
Supabase
Vercel
Render
Railway
Fly.io
AWS
Azure
local filesystem persistence
```

without checking current deployment docs.

If deployment documentation conflicts with this file, stop and report the conflict before implementing.

General deployment rules:

* Do not commit secrets.
* Do not bake production secrets into images.
* Do not assume local persistent file storage in production.
* Do not run database migrations from a production web-service entrypoint unless the active deployment design explicitly requires it.
* Migration execution must be deliberate, documented, and environment-aware.
* Production security settings must be reviewed before launch.
* Environment variables must be documented.
* Storage, static files, media files, and background jobs must match the confirmed deployment target.

---

## Graphify

This project has a knowledge graph at `graphify-out/` with god nodes, community structure, and cross-file relationships.

Rules:

* Always read `graphify-out/GRAPH_REPORT.md` before reading source files, running grep/glob searches, or answering codebase questions.
* If `graphify-out/wiki/index.md` exists, navigate it before reading raw files.
* For cross-module relationship questions, prefer Graphify commands over grep.

Examples:

```bash
graphify query "<question>"
graphify path "<A>" "<B>"
graphify explain "<concept>"
```

Graphify traverses extracted and inferred relationships instead of merely scanning text.

After modifying code, run:

```bash
graphify update .
```

This keeps the graph current.

---

## Documentation Rules

Important decisions must be documented in the existing appropriate location.

Preferred documentation locations:

```text
AGENTS.md
docs/
Graphify
architecture docs
audit plans
integration plans
handover docs
PR descriptions
```

Rules:

* Do not create duplicate docs when an existing doc should be updated.
* Do not create competing architecture documents.
* Do not create a new PR template unless explicitly requested.
* Do not document speculative future behavior as if it is implemented.
* Clearly distinguish between implemented behavior, planned behavior, and open questions.
* If a decision affects agents, update `AGENTS.md`.
* If a decision affects architecture, update the relevant architecture or integration document.
* If a decision affects handover continuity, update the relevant handover document.

---

## Manual Verification Examples

When workflow-critical behavior changes, include concrete manual verification in the PR.

Examples for SPOT / Exception Workspace:

```text
Created SPOT envelope from fixture.
Opened Exception Workspace.
Confirmed suggested charges displayed.
Confirmed Needs Attention queue displayed unresolved items.
Mapped one charge to existing ProductCode.
Requested ProductCode for unmapped charge.
Confirmed pending ProductCode remained visible.
Confirmed ignored item remained auditable.
Confirmed Finish Review remained disabled while blocking issue existed.
```

Examples for pricing:

```text
Created quote with standard freight only.
Created quote with SPOT freight overlay.
Confirmed SPOT freight replaced standard freight for same bucket.
Confirmed totals did not double-count freight.
Confirmed missing domestic rate emitted is_rate_missing=True.
```

Examples for public quote rendering:

```text
Generated public quote.
Confirmed grouped ProductCode lines displayed correctly.
Confirmed informational lines were not included in totals.
Confirmed mixed currencies were not incorrectly grouped.
Confirmed customer-facing labels were clean.
```

Avoid vague statements.

Do not write:

```text
Manual test passed.
UI looks good.
Checked locally.
```

Say exactly what was checked.

---

## PR Report Minimum Template

Every PR summary must include:

```md
## Scope

What this PR changes.

## Changed Files

- `path/to/file`: why it changed

## What Was Intentionally Not Changed

- Item 1
- Item 2

## Verification

Automated:
- command
- result

Manual:
- step
- result

## Risk

Known risks and residual uncertainty.

## Rollback

How to safely revert if needed.
```

For high-risk workflows, also include:

```md
## Commercial Impact

Does this affect quote totals, ProductCode mapping, public quote output, or operator decisions?

## Data Impact

Does this create, update, delete, or backfill data?

## Audit Impact

Does this preserve who/what/when/why?
```

---

## Agent Handoff Rule

At the end of a major phase, agents must provide a concise handoff summary containing:

* what was implemented
* what was learned
* what decisions were made
* what remains open
* what risks remain
* what should happen next
* branch name
* PR number
* verification performed
* files changed
* any known local workspace issues

Do not leave the next agent guessing.

---

## Final Principle

RateEngine is now past the loose experimentation phase.

The risky areas involve:

```text
pricing
ProductCodes
SPOT intake
operator decisions
quote totals
public quote output
RBAC scope
deployment
```

Agent creativity is welcome in planning and design.

Agent creativity is not welcome in silent pricing assumptions, fallback mappings, quote-total changes, or production data mutations.

When uncertain:

```text
preserve evidence
surface the gap
stop and report
ask for a decision
```
