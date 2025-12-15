# RateEngine Architecture Principles

> **Document Status:** LOCKED — Changes require explicit approval  
> **Last Updated:** 2024-12-14  
> **Applies To:** All RateEngine development

---

## 1. Engine-First Trust Model

RateEngine is designed to be **trusted by default**. The pricing engine is the single source of truth for all quote calculations.

### Core Principles

| Principle | Description |
|-----------|-------------|
| **Deterministic** | Given the same inputs, the engine MUST produce the same outputs |
| **Auditable** | Every charge line must be traceable to its source (rate card, spot rate, rule) |
| **No Manual Overrides in Engine** | Overrides are inputs, not exceptions to logic |
| **Engine Never Guesses** | Missing data → Missing rate flag, never default values |

### Implications

- The engine does NOT apply "reasonable defaults" for missing rates
- The engine does NOT interpolate between rate cards
- The engine does NOT make pricing decisions — it executes rules
- Users see what the engine sees (transparency)

---

## 2. Pydantic Usage Rules

Pydantic is used as a **business-contract and validation layer** at service boundaries.

### MUST Use Pydantic For

| Use Case | Why |
|----------|-----|
| AI-Assisted Rate Intake outputs | Prevent hallucinated/malformed data |
| Quote calculation input contracts | Engine only accepts validated objects |
| Pricing engine outputs | Charge lines, totals, GST |
| FX validation contexts | Currency pairs, rates, staleness checks |
| Discount rule validation | Component-level discounts only |
| API request/response schemas | Service boundary contracts |

### MUST NOT Use Pydantic For

| Use Case | Why |
|----------|-----|
| Django ORM models | Use Django's model layer |
| Database migrations | Use Django migrations |
| UI form state | Handled by frontend |
| Simple CRUD pass-throughs | Unnecessary overhead |

### Rule of Thumb

> **If invalid data here could produce a wrong quote → use Pydantic.**

---

## 3. AI-Assisted Rate Intake

AI-Assisted Rate Intake is a **first-class MVP capability** of RateEngine.

### Purpose

- Ingest unstructured agent/carrier quotes (email text, PDF documents)
- Convert to structured, validated charge lines
- Reduce manual data entry
- Speed up quoting while maintaining accuracy

### Non-Negotiable Principles

| Rule | Description |
|------|-------------|
| **AI never writes to database** | All AI output must pass validation and require human acceptance |
| **Human-in-the-loop** | AI output → Pydantic validation → Preview → User accepts → Persist |
| **AI is input accelerator** | AI supports humans — it does not replace rules |

### AI Responsibilities

```
AI DOES:                         AI DOES NOT:
├── Extraction                   ├── Apply FX rates
├── Structuring                  ├── Apply margins
├── Normalisation                ├── Calculate totals
└── Currency detection           └── Make pricing decisions
```

### Architecture Flow

```
User (Paste Text or Upload PDF)
        ↓
Backend (PDF → Text extraction if required)
        ↓
AI Model (Gemini 2.0 Flash)
        ↓
Strict JSON output
        ↓
Pydantic validation (SpotChargeLine[])
        ↓
Editable Preview UI
        ↓
User Accepts
        ↓
Persist structured charge lines to quote
```

### PDF Handling

| Priority | Tool | Purpose |
|----------|------|---------|
| Primary | `pdfplumber` | Text extraction from digital PDFs |
| Fallback | `pymupdf` | Alternative extraction |
| Last resort | OCR | Scanned documents (warn user on low confidence) |

**AI must never receive raw PDFs** — only extracted text.

### AI Model Configuration

- **Model:** Google Gemini 2.0 Flash
- **Integration:** Backend-only via official SDK
- **Response format:** JSON only
- **Validation:** Strict Pydantic schemas

---

## 4. Quote Immutability

Quotes follow a strict state machine with immutability guarantees.

### Quote States (MVP)

```
DRAFT → FINALIZED → SENT
```

### State Definitions

| State | Editable? | Description |
|-------|-----------|-------------|
| `DRAFT` | Yes | Work in progress — spot rates, cargo, routing can be modified |
| `FINALIZED` | Never | Locked and immutable — ready for customer delivery |
| `SENT` | Never | Delivered to customer — audit complete |

### MVP Simplifications

- **No approval workflow** — quotes go directly from DRAFT to FINALIZED
- **No PENDING or REJECTED states** — these are post-MVP
- **Changes require cloning** — to modify a FINALIZED quote, clone it as a new DRAFT

### Implications

- FINALIZED quotes cannot be edited — clone to create a new quote
- Version history is preserved for audit
- Price changes require a new quote (cloned from original)

---

## 5. UI Design Principles

### No Icons Unless Explicitly Approved

- Prefer text labels, spacing, typography
- Icons add visual noise without adding information
- Exception: Only when explicitly approved for specific use cases

### Visual Hierarchy

- Use spacing and padding for hierarchy, not borders
- Reduce stacked/nested borders
- Keep sections "breathable"

### AI Intake UI

- Text-based options: "Paste agent rates", "Upload PDF"
- Preview table must be editable before acceptance
- Clear indication of AI-parsed vs user-entered data

---

## 6. Service Boundary Contracts

All service boundaries must have explicit Pydantic contracts.

### Example: AI Rate Intake

```python
from pydantic import BaseModel, Field
from decimal import Decimal
from typing import Literal, Optional, List

class SpotChargeLine(BaseModel):
    """Single charge line parsed from agent/carrier quote."""
    bucket: Literal["ORIGIN", "FREIGHT", "DESTINATION"]
    description: str = Field(..., min_length=1, max_length=200)
    amount: Optional[Decimal] = Field(None, ge=0)
    currency: Optional[str] = Field(None, pattern=r"^[A-Z]{3}$")
    unit_basis: Literal["PER_KG", "PER_SHIPMENT", "PERCENTAGE"]
    percentage: Optional[Decimal] = Field(None, ge=0, le=100)
    minimum: Optional[Decimal] = Field(None, ge=0)
    maximum: Optional[Decimal] = Field(None, ge=0)
    percent_applies_to: Optional[str] = None
    notes: Optional[str] = None

class AIRateIntakeResponse(BaseModel):
    """Validated response from AI rate extraction."""
    success: bool
    lines: List[SpotChargeLine] = []
    warnings: List[str] = []
    raw_text_length: int
    extraction_confidence: float = Field(..., ge=0, le=1)
```

### Validation Failure Handling

If validation fails:
1. Reject AI response
2. Retry AI call (up to 2 retries)
3. Surface error to user with option to manually enter

---

## 7. Summary: What RateEngine Is

```
RateEngine is:
├── Engine-first
├── Deterministic
├── Trusted by design
├── Human-in-the-loop for AI
└── Auditable at every step

RateEngine is NOT:
├── AI-powered pricing
├── Approximate or "smart" defaults
├── Opinionated about business rules
└── A black box
```

---

## Document History

| Date | Change | Author |
|------|--------|--------|
| 2024-12-14 | Initial version — locked principles | System |
