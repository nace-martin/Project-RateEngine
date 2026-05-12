# AGENTS.md

## Source of Truth

LEGACY SPOT-RATE CRUD IS DEPRECATED. ALL NEW WORK MUST USE THE SPE ENVELOPE AND V4 ADAPTER.

### Spot Workflow Rules

- Use `SpotPricingEnvelopeDB`, `SPESourceBatchDB`, `SPEChargeLineDB`, and `SPEAcknowledgementDB` as the active Spot persistence model.
- Use `PricingServiceV4Adapter` with `spot_envelope_id` for hybrid quote calculation.
- Treat `/api/v3/spot/analyze-reply/` and `/api/v3/spot/envelopes/*` as the active Spot API surface.
- Do not reintroduce `QuoteSpotRate`, `QuoteSpotCharge`, or quote-scoped Spot-rate CRUD flows.
- Do not add new code against the removed `/api/v3/quotes/<quote_id>/ai-intake/` path.

### Pricing Engine Rules

- DOMESTIC FREIGHT MUST emit `is_rate_missing=True` if no COGS/Sell row is found. Deterministic selection (ordering by latest `valid_from` date) is mandatory across all engines.
- All rate lookups must be deterministic: `.order_by('-valid_from', '-updated_at', '-id').first()`.
- Commodity code (`DOC` vs `CRG`) distinction must be respected: `DOC` = Documents (no commercial value, flat rates), `CRG` = Full cargo audit required.

### Spot Overlay Rules

- SPOT OVERLAY RULE: Spot freight charges MUST replace standard freight charges for the same leg/route, never append. This applies to ALL shipment types including Domestic.
- Bucket-level override is the canonical merge strategy. Domestic no longer uses append.

### AI Intake Rules

- The live AI intake pipeline is `Raw -> Normalized -> Audit -> Quote Input`.
- AI extraction supports Spot intake, but final quote pricing still belongs to the deterministic V4 engine.

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- ALWAYS read graphify-out/GRAPH_REPORT.md before reading any source files, running grep/glob searches, or answering codebase questions. The graph is your primary map of the codebase.
- IF graphify-out/wiki/index.md EXISTS, navigate it instead of reading raw files
- For cross-module "how does X relate to Y" questions, prefer `graphify query "<question>"`, `graphify path "<A>" "<B>"`, or `graphify explain "<concept>"` over grep — these traverse the graph's EXTRACTED + INFERRED edges instead of scanning files
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
