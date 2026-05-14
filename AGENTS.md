# AGENTS.md

## Master Constitution

This file is the master governance source for Codex, Gemini CLI, and any other AI agent working in RateEngine. Agent-specific files such as `CODEX.md` and `GEMINI.md` may add tool-specific operating rules, but they must not contradict or duplicate this constitution.

## Source of Truth

LEGACY SPOT-RATE CRUD IS DEPRECATED. ALL NEW WORK MUST USE THE SPE ENVELOPE AND V4 ADAPTER.

Do not create duplicate sources of truth. If governance, architecture, workflow, or review guidance already exists, update the existing file in place. Do not create parallel files, duplicate PR templates, or overlapping architecture docs.

## PR Discipline

- One PR = one concern.
- Do not hide scope expansion inside a small request.
- Do not perform drive-by refactors, unrelated formatting churn, or opportunistic cleanup.
- Do not mix unrelated backend, frontend, UI, refactor, cleanup, data, and documentation changes in one PR.
- List every changed file and why it changed.
- State what was intentionally not changed.
- If behavior is ambiguous, stop and report the ambiguity instead of guessing.

## Root-Cause Discipline

- Always identify the root cause before implementing a fix.
- Do not patch symptoms while leaving the broken path active.
- Prefer deleting dead code over patching around it.
- Do not revive deleted, deprecated, or legacy code paths unless the user explicitly instructs it.
- Any removed legacy behavior must be called out in the PR.

## Quote-First Product Rule

RateEngine is quote-first. Quote creation, quote calculation, quote finalization, pricing breakdowns, public quote rendering, and quote-derived CRM logging are workflow-critical.

- UI changes must preserve quote workflow integrity.
- CRM changes must stay within CRM unless explicitly requested.
- Do not introduce global CRM navigation, buttons, banners, or shortcuts unless explicitly requested.
- Before changing quote creation, SPOT, pricing, FX, CAF, GST, margin, charge grouping, public quote rendering, or CRM quote logging, inspect the full workflow end-to-end.

## Verification Rule

Tests passing is not enough.

- Run relevant automated checks for the change.
- Manually verify the affected user workflow when the change touches workflow-critical areas.
- Document manual verification steps and results in the PR.
- If a workflow cannot be manually verified, explain why and list the residual risk.

## Spot Workflow Rules

- Use `SpotPricingEnvelopeDB`, `SPESourceBatchDB`, `SPEChargeLineDB`, and `SPEAcknowledgementDB` as the active Spot persistence model.
- Use `PricingServiceV4Adapter` with `spot_envelope_id` for hybrid quote calculation.
- Treat `/api/v3/spot/analyze-reply/` and `/api/v3/spot/envelopes/*` as the active Spot API surface.
- Do not reintroduce `QuoteSpotRate`, `QuoteSpotCharge`, or quote-scoped Spot-rate CRUD flows.
- Do not add new code against the removed `/api/v3/quotes/<quote_id>/ai-intake/` path.

## Pricing Engine Rules

- DOMESTIC FREIGHT MUST emit `is_rate_missing=True` if no COGS/Sell row is found. Deterministic selection by latest `valid_from` date is mandatory across all engines.
- All rate lookups must be deterministic: `.order_by('-valid_from', '-updated_at', '-id').first()`.
- Commodity code (`DOC` vs `CRG`) distinction must be respected: `DOC` = Documents with no commercial value and flat rates; `CRG` = cargo requiring full audit.
- If pricing behavior is ambiguous or source data is incomplete, fail clearly through missing-rate or incomplete-coverage signals instead of guessing.

## Spot Overlay Rules

- SPOT OVERLAY RULE: Spot freight charges MUST replace standard freight charges for the same leg/route, never append. This applies to ALL shipment types including Domestic.
- Bucket-level override is the canonical merge strategy. Domestic no longer uses append.

## AI Intake Rules

- The live AI intake pipeline is `Raw -> Normalized -> Audit -> Quote Input`.
- AI extraction supports Spot intake, but final quote pricing still belongs to the deterministic V4 engine.

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- ALWAYS read graphify-out/GRAPH_REPORT.md before reading any source files, running grep/glob searches, or answering codebase questions. The graph is your primary map of the codebase.
- IF graphify-out/wiki/index.md EXISTS, navigate it instead of reading raw files
- For cross-module "how does X relate to Y" questions, prefer `graphify query "<question>"`, `graphify path "<A>" "<B>"`, or `graphify explain "<concept>"` over grep — these traverse the graph's EXTRACTED + INFERRED edges instead of scanning files
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
