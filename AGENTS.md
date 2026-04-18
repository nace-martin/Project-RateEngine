# AGENTS.md

## Source of Truth

LEGACY SPOT-RATE CRUD IS DEPRECATED. ALL NEW WORK MUST USE THE SPE ENVELOPE AND V4 ADAPTER.

### Spot Workflow Rules

- Use `SpotPricingEnvelopeDB`, `SPESourceBatchDB`, `SPEChargeLineDB`, and `SPEAcknowledgementDB` as the active Spot persistence model.
- Use `PricingServiceV4Adapter` with `spot_envelope_id` for hybrid quote calculation.
- Treat `/api/v3/spot/analyze-reply/` and `/api/v3/spot/envelopes/*` as the active Spot API surface.
- Do not reintroduce `QuoteSpotRate`, `QuoteSpotCharge`, or quote-scoped Spot-rate CRUD flows.
- Do not add new code against the removed `/api/v3/quotes/<quote_id>/ai-intake/` path.

### AI Intake Rules

- The live AI intake pipeline is `Raw -> Normalized -> Audit -> Quote Input`.
- AI extraction supports Spot intake, but final quote pricing still belongs to the deterministic V4 engine.
