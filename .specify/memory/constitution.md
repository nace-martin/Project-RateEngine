<!--
SYNC IMPACT REPORT
- Version: v2.1.1 → v3.0.0
- Modified Principles: Complete overhaul. Replaced 5 generic principles with 15 domain-specific principles.
- Added Sections: All sections are new.
- Removed Sections: All old sections removed.
- Templates Requiring Updates:
  - ✅ .specify/memory/constitution.md (this file)
  - ✅ .specify/templates/plan-template.md
- Follow-up TODOs:
  - TODO(RATIFICATION_DATE): The original adoption date for the constitution is unknown and needs to be set.
-->

# RateEngine v2 — Project Constitution

Governing principles for design, development, testing, UX, performance, and operations.

## 0) Purpose & Scope
Build a quoting engine that turns messy partner pricing (rate cards, spot emails) into clean, deterministic quotes. We do this with Source Adapters (“Universal Translator”) → Normalized BUY → Recipes, with zero crash tolerance and first-class observability.

## 1) Code Quality & Maintainability
- Deterministic over clever. Same inputs → same outputs. Prefer clear code to “magic.”
- Universal Translator is core. All external data comes through adapters. The core only talks to standardized internal models.
- Strongly typed data. Use dataclasses/enums over raw strings/dicts.
- Readable, auditable, boring (compliment). Small functions; explicit side effects.

## 2) Testing Standards
- Test-first. Write tests before implementation; broken tests block release.
- Business-real scenarios. Tests mirror real jobs (e.g., “A2D PREPAID 100 kg BNE→POM”).
- No feature without tests. Every bug fix adds/updates tests.

## 3) UX & Consistency
- Simplicity first. Clean, uncluttered screens; obvious next step.
- Workflow-aware. Fits how Sales actually works (email, PDFs, quick edits).
- Clarity over density. Users should instantly know price, currency, and what’s included.

## 4) Performance & Reliability
- Fail gracefully, never crash. Missing data returns a clear message (e.g., “Manual Rate Required”), not a 500.
- Fast by default. Quote calculations feel snappy; we set and enforce budgets (see §6).

## 5) Determinism & Selection (hard rules)
- Same inputs → same outputs.
- Selection priority: Contracted RateCard → Current RateCard → Pinned Spot → else incomplete.
- Tie-breakers: newer valid_from → lower base rate → carrier priority list.

## 6) Resilience & Performance Budgets (hard numbers)
- No 500s on data gaps. Return is_incomplete=true with one crisp reason.
- Timeouts: each adapter ≤ 2s; total compute ≤ 3s prod (≤ 5s dev).
- Retries: 1 retry with jitter; on persistent failure, circuit-break 5 min.
- Adapters never raise. On error, return zero offers; the service degrades gracefully.

## 7) Observability & Auditability (snapshot must include)
- calc_id, policy_key/version, adapter_versions.
- selection_rationale (which priority path won + tie-break).
- included_fees, skipped_fees_with_reasons[].
- phase_timings_ms = {normalize, build_menu, select, recipe, tax_fx}.
- If incomplete: single-line human-readable reasons[].

## 8) RBAC & Data Privacy
- Sales: sell lines only; no BUY/COGS or FX internals.
- Manager/Finance: full snapshot + BUY/FX.
- Provenance blobs (pasted emails) stored securely; redact PII in logs.

## 9) UX Consistency (what users always see)
- Fee-scope badge: “Destination-side only” (import) / “Origin-side only” (export).
- Currency chips: AUD / USD / PGK resolved by audience.
- Pre-flight toggles (A2D): Tail-lift, remote/after-hours, DG, DDP vs DAP (adds Disbursement).
- PDF staples: validity, scope note, GST/VAT line, CTO pass-through note.

## 10) Business Rules (hard guardrails)
- Chargeable weight (air): max(actual_kg, (L×W×H cm / 1e6) × 167).
- Import A2D:
  - PREPAID ⇒ AUD, COLLECT ⇒ PGK.
  - Destination-side fees only (clearance, CTO, cartage, fuel%, attendances, etc.).
- Export:
  - Overseas (AU lanes) ⇒ AUD, non-AU ⇒ USD, PNG shipper ⇒ PGK.
  - Origin-side fees only (AWB/doc, screening, terminal, pickup, DG, etc.).
- Percent-of fees apply only if their base exists; otherwise skip + reason.
- Disbursement only on DDP (5% with min/cap per card).
- Rounding: unit prices 4dp; extended totals 2dp.

## 11) Testing & Coverage (enforced)
- Must cover: A2D PREPAID/AUD, A2D COLLECT/PGK, Export (AU/AUD, non-AU/USD, PNG/PGK), Spot ingestion, Missing BUY → incomplete, Adapter timeout → incomplete, RBAC serializers.
- Coverage targets: ≥85% core; ≥90% adapters & recipes.
- Use xfail (with reason) for roadmap tests; don’t hide with skip.

## 12) Release & Flags
- Feature flags: QUOTER_V2_ENABLED, RATECARD_ADAPTER_ENABLED, SPOT_ADAPTER_ENABLED.
- SemVer release notes each version; canary by flag; fast rollback path.

## 13) Architecture Principles (recap)
- Adapter boundary: Adapters isolate chaos; they output BuyOffer/BuyMenu with Provenance.
- Recipes enforce policy: Audience → Currency → Fee Scope applied post-selection.
- Snapshots tell the story: Every compute explains itself.

## 14) Data & Schema Guidelines
- Tables: quotations, quote_versions, shipment_pieces, charges; optional ratecards/*.
- JSONB snapshot on versions stores full compute context.
- Enums over magic strings (basis, side, payment term, provenance type).
- Migrations: forward-only; index lane lookups.

## 15) Definition of Done (for any pricing feature)
- Tests pass & meet coverage gates.
- Flags present; fallback path behaves (no 500s).
- Snapshot includes selection rationale & timings.
- RBAC outputs verified (Sales vs Manager).
- Docs updated (spec/plan/tasks/README, release notes).
- UX copy reviewed; accessibility checks done.

## Governance
This constitution defines the non-negotiable rules for the project. Amendments require a documented proposal, review, and version bump according to SemVer. All development, reviews, and deployments must adhere to these principles.

**Version**: 3.0.0 | **Ratified**: TODO(RATIFICATION_DATE) | **Last Amended**: 2025-10-02
