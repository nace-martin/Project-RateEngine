# RateEngine Architecture Principles

> **Document Status:** LOCKED - Changes require explicit approval
> **Last Updated:** 2026-04-19
> **Applies To:** All RateEngine development

---

## 1. Engine-First Trust Model

RateEngine is designed to be **trusted by default**. The pricing engine is the single source of truth for all quote calculations.

### Core Principles

| Principle | Description |
|-----------|-------------|
| **Deterministic** | Given the same inputs, the engine MUST produce the same outputs |
| **Auditable** | Every charge line must be traceable to its source |
| **No Manual Overrides in Engine** | Overrides are explicit inputs, not hidden exceptions |
| **Engine Never Guesses** | Missing data leads to missing-rate or incomplete coverage signals, never silent defaults |

### Implications

- The engine does NOT apply "reasonable defaults" for missing rates.
- The engine does NOT interpolate between rate cards.
- The engine does NOT make pricing decisions; it executes rules.
- Users should be able to trace quote outputs back to persisted inputs and source metadata.

---

## 2. Pydantic Usage Rules

Pydantic is used as a **business-contract and validation layer** at service boundaries.

### MUST Use Pydantic For

| Use Case | Why |
|----------|-----|
| AI-assisted Spot intake outputs | Prevent malformed or partially hallucinated structures from entering the Spot workflow |
| Quote calculation input contracts | Engine only accepts validated objects |
| Pricing engine outputs | Charge lines, totals, GST, audit metadata |
| FX validation contexts | Currency pairs, rates, staleness checks |
| Discount rule validation | Component-level commercial rules |
| API request/response schemas | Service boundary contracts |

### MUST NOT Use Pydantic For

| Use Case | Why |
|----------|-----|
| Django ORM models | Use Django's model layer |
| Database migrations | Use Django migrations |
| UI form state | Handled by frontend state/schema code |
| Simple CRUD pass-throughs | Unnecessary overhead |

### Rule of Thumb

> **If invalid data here could produce a wrong quote, use Pydantic.**

---

## 3. AI-Assisted Rate Intake

AI-assisted rate intake is a **Spot input acceleration capability**, not an autonomous pricing capability.

### Purpose

- Ingest unstructured agent or carrier quotes from pasted text or PDFs
- Convert them into structured, validated Spot charge candidates
- Reduce manual data entry in the Spot workflow
- Preserve reviewability before quote creation

### Non-Negotiable Principles

| Rule | Description |
|------|-------------|
| **AI never prices the quote** | AI extracts and normalizes intake data only; the deterministic pricing engine still calculates the quote |
| **AI output is schema-bound** | Each intake stage must pass Pydantic validation |
| **Human-in-the-loop persistence** | AI output may prefill an SPE draft, but users still review or edit before final quote creation |
| **AI is input accelerator** | AI supports human workflow; it does not replace pricing rules |

### AI Responsibilities

```
AI DOES:                         AI DOES NOT:
- Extraction                     - Apply FX rates
- Structuring                    - Apply margins
- Normalization                  - Calculate totals
- Ambiguity surfacing            - Make pricing decisions
- Warning generation             - Bypass SPE review/edit flow
```

### Live Pipeline

```
User (paste text or upload PDF)
        ->
PDF text extraction (if required)
        ->
Raw extraction stage
        ->
Normalized charge stage
        ->
Audit / critic stage
        ->
Quote input payload
        ->
Reply analysis + SPE source batch persistence
        ->
User review/edit in Spot workflow
        ->
PricingServiceV4Adapter hybrid quote calculation
```

### Pipeline Stages

The live backend flow in `backend/quotes/ai_intake_service.py` is:

1. **Raw**
   - `_extract_raw_charges(...)`
   - Produces raw extracted charge candidates from text.
2. **Normalized**
   - `_normalize_charges(...)`
   - Converts raw candidates into normalized charge structures with standardized buckets, units, and fields.
3. **Audit**
   - `_audit_extraction(...)`
   - Reviews the normalized result for gaps, ambiguity, contradictions, and warning conditions.
4. **Quote Input**
   - `_build_final_spot_charge_lines(...)`
   - Produces the final charge-line payload used to build `QuoteInputPayload` inside `AIRateIntakePipelineResult`.

`parse_rate_quote_text(...)` orchestrates the full `Raw -> Normalized -> Audit -> Quote Input` path.

For PDFs, `parse_pdf_rate_quote(...)` first calls `extract_rate_quote_text_from_pdf(...)`, then sends the extracted text through the same four-stage pipeline.

### PDF Handling

| Priority | Tool | Purpose |
|----------|------|---------|
| Primary | Deterministic extraction helpers | Extract text from machine-readable PDFs quickly |
| Fallback | Gemini-assisted extraction | Recover text when deterministic extraction is weak |
| Last resort | Warning-heavy low-confidence recovery | Keep the output reviewable instead of silently guessing |

PDF intake is allowed, but the quote flow still operates on extracted text and validated schemas rather than opaque document blobs.

### AI Model Configuration

- **Model family:** Gemini via backend integration
- **Execution location:** Backend only
- **Response requirement:** Structured output suitable for schema validation
- **Validation:** Strict Pydantic contracts at each intake boundary

---

## 4. Quote Immutability

Quotes follow a strict state machine with immutability guarantees.

### Quote States

```
DRAFT -> FINALIZED -> SENT
```

### State Definitions

| State | Editable? | Description |
|-------|-----------|-------------|
| `DRAFT` | Yes | Work in progress |
| `FINALIZED` | No | Locked and ready for customer delivery |
| `SENT` | No | Delivered to customer |

### Implications

- FINALIZED quotes cannot be edited; clone to create a new draft.
- Version history is preserved for audit.
- Spot quotes still become normal persisted quote versions after calculation.

---

## 5. UI Design Principles

### No Icons Unless Explicitly Approved

- Prefer text labels, spacing, and typography.
- Icons should only be used when they improve comprehension materially.

### Visual Hierarchy

- Use spacing and typography for hierarchy instead of border stacking.
- Keep workflows readable under high operational load.

### Spot Intake UI

- Support text paste and PDF upload.
- Keep the extracted Spot lines editable before quote creation.
- Surface source, warnings, and review state clearly.

---

## 6. Service Boundary Contracts

All service boundaries must have explicit contracts.

### Example: AI Rate Intake

```python
from pydantic import BaseModel
from typing import List, Optional

class AIRateIntakePipelineResult(BaseModel):
    success: bool
    quote_input: Optional["QuoteInputPayload"] = None
    raw_text_length: int = 0
    warnings: List[str] = []
    error: Optional[str] = None
    source_type: str = "TEXT"
    analysis_text: Optional[str] = None
    model_used: Optional[str] = None
```

### Validation Failure Handling

If validation fails:

1. Reject or downgrade the problematic AI output.
2. Return warnings and/or error details in `AIRateIntakePipelineResult`.
3. Keep the Spot workflow editable so the user can correct or replace the extracted lines before quote creation.

---

## 7. Summary

```
RateEngine is:
- Engine-first
- Deterministic
- Auditable
- Human-reviewed for AI-assisted intake
- Hybrid-capable through SPE + V4 overlay

RateEngine is NOT:
- AI-priced
- Default-driven when data is missing
- A quote-time black box
- A legacy quote-scoped Spot-rate CRUD system
```

---

## Document History

| Date | Change | Author |
|------|--------|--------|
| 2024-12-14 | Initial locked principles | System |
| 2026-04-19 | Updated AI intake and Spot architecture to SPE + V4 hybrid flow | Codex |
