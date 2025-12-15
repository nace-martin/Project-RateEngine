# Pydantic Implementation Context & Rules for RateEngine

> **Document Purpose:** Defines mandatory Pydantic usage patterns for protecting pricing engine integrity.

---

## 1. Purpose of Pydantic in RateEngine

Pydantic exists to **protect the pricing engine from bad data**.

RateEngine is:
- **Engine-first**
- **Deterministic**
- **Financially sensitive**

Therefore:
- Any data that could cause a wrong quote if incorrect **MUST** be validated with Pydantic
- Pydantic enforces contracts at **system boundaries**, not inside CRUD flows

---

## 2. Where Pydantic MUST Be Used (Non-Negotiable)

### A. AI-Assisted Rate Intake (Highest Priority)

AI output is **untrusted by default**.

Pydantic MUST:
- Validate all AI-parsed charge lines
- Enforce allowed buckets: `ORIGIN | FREIGHT | DESTINATION`
- Enforce unit logic: `PER_KG | PER_SHIPMENT | PERCENTAGE`
- Require `percent_applies_to` for percentage charges
- Prevent hallucinated currencies, negative values, or malformed structures

**Required Flow:**
```
AI → JSON → Pydantic → Preview UI → Human Accept → Persist
```

> [!CAUTION]
> AI must **never** bypass Pydantic.

### B. Pricing Engine Input Contracts

Before any pricing calculation runs:
- Inputs must be normalized into a Pydantic model
- Pricing logic must **only accept validated Pydantic objects**
- Raw request payloads or ORM models must **never** enter the engine directly

**Examples of enforced inputs:**
- Chargeable weight
- Currency context
- Incoterm / payment terms
- Location context (POM / LAE)
- GST applicability

### C. Pricing Engine Outputs

Pricing outputs feed:
- UI
- PDFs
- Audit logs
- Reporting

Pydantic MUST:
- Validate calculated charge lines
- Enforce non-negative values
- Ensure totals equal sum of components
- Prevent silent math errors

> [!IMPORTANT]
> If output fails validation → **fail loudly**.

### D. FX Validation Context

Pydantic MUST:
- Enforce valid currency pairs
- Ensure FX rates are positive
- Validate buy/sell rate presence
- Prevent missing or stale FX from slipping through

> [!WARNING]
> No silent FX fallback is allowed.

### E. Discount Engine Rules

Pydantic MUST:
- Validate discount type: `PERCENT | FLAT | RATE_OVERRIDE`
- Enforce required fields per discount type
- Prevent ambiguous or double-applied discounts
- Ensure discounts apply **only at SELL layer**

Discount logic must never rely on loosely structured data.

### F. API Request / Response Boundaries

At service boundaries (especially pricing & AI endpoints):
- Pydantic validates incoming data
- Pydantic shapes outgoing responses

This applies to:
- AI intake endpoints
- Pricing endpoints
- Quote calculation responses

---

## 3. Where Pydantic MUST NOT Be Used

Pydantic is explicitly **NOT allowed** for:

| ❌ Forbidden Usage |
|-------------------|
| Django ORM models |
| Database migrations |
| Simple CRUD forms |
| UI / frontend state |
| Permission or RBAC logic |
| Presentation formatting |

```
Pydantic ≠ database
Pydantic ≠ UI
Pydantic = business contract enforcement
```

---

## 4. Enforcement Rules

1. Pricing logic must **never accept raw dicts**
2. AI output must **never be trusted** without validation
3. If validation fails, **fail fast and visibly**
4. Do not add Pydantic "just because" — every model must protect a financial or logical boundary

---

## 5. The Test (One-Line Rule)

> **If incorrect data here could result in a wrong quote, Pydantic must guard it.**
>
> If not — do not use Pydantic.

---

## 6. Current Implementation Status

| Domain | File | Status |
|--------|------|--------|
| AI Intake | `quotes/ai_intake_schemas.py` | ✅ Implemented |
| FX Validation | `core/fx_schemas.py` | ✅ Implemented |
| API Responses | `quotes/response_schemas.py` | ✅ Implemented |
| Discount Engine | — | ❌ Not yet implemented |
| Pricing Engine Inputs | — | ⚠️ Needs verification |

---

## 7. Architectural Reminder

RateEngine is:
- **Deterministic**
- **Auditable**
- **Engine-first**
- **Human-in-the-loop for AI**
- **Text-based UI** (no icons unless explicitly approved)

> [!NOTE]
> If unsure whether Pydantic applies to a component, **ask before implementing**.

---

## 8. Expected Outcome

When implemented correctly:
- ✅ AI output is safe
- ✅ Pricing logic is trustworthy
- ✅ Bugs fail loudly
- ✅ UI and PDFs stay consistent
- ✅ Refactors are minimal

**This is intentional architecture, not over-engineering.**
