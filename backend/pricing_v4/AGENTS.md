# Pricing V4 Agent Guide

These instructions apply within `backend/pricing_v4/` in addition to the repository root guide.

## Active Engine and Sources

V4 is the active deterministic pricing engine. Start with:

- `docs/pricing_v4_overview.md` for the repository-level overview;
- `backend/pricing_v4/docs/pricing_runtime_selection_rules.md` for maintained selector rules;
- `backend/pricing_v4/docs/quote_selector_input_requirements.md` for required inputs;
- `backend/pricing_v4/docs/charge_alias_operations.md` for ChargeAlias operations; and
- current engine, adapter, selector, and tests as implementation evidence.

Documents named as plans or audits may describe proposed or historical state. Verify them against current source.

## Pricing Boundaries

- Use `PricingServiceV4Adapter`; hybrid SPOT calculation supplies `spot_envelope_id`.
- Reuse the selector abstraction in `services/rate_selector.py`. Do not scatter independent ORM ordering logic or introduce nondeterministic `.first()` lookups.
- Keep COGS and SELL sources separate. Do not derive a missing sell rate from local cost or a missing cost from sell.
- Missing commercial coverage must remain visible. Domestic pricing emits `is_rate_missing=True` when no valid COGS or SELL match exists; preserve equivalent explicit signals in other engines.
- Use the canonical commodity definitions in `backend/core/commodity.py`. Do not infer commodity behavior from ProductCode names or substrings. When commodity pricing changes, verify default `GCR` behavior and each affected special-cargo code independently.
- Informational, conditional, and supplemental metadata is excluded from primary totals unless an explicitly approved commercial change says otherwise.
- SPOT freight replaces matching standard freight buckets, including Domestic; it never adds a second freight charge for the same bucket.

Before changing a calculation, trace input normalization, selector criteria, engine output, adapter mapping, persisted quote lines, and customer-facing output. Do not broaden matching or add a fallback merely to satisfy one fixture.

## Verification

Use targeted Ruff and affected pricing tests first. Depending on scope, verify:

- deterministic choice when multiple valid rows exist;
- missing-rate output when COGS or SELL is absent;
- COGS/SELL, currency, FX, CAF, GST, margin, inclusion, and grouping behavior;
- standard-only and hybrid SPOT quotes; and
- no freight double-counting in persisted and public output.

State exactly which commercial outputs changed. If none changed, say so explicitly.
