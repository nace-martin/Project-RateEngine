# SPOT Template Validation Operations Runbook

This runbook outlines standard operating procedures for managing, inspecting, and testing the expected charge templates and validation finding reviews in RateEngine.

## 1. Django Admin Operations

Expected charge templates and user reviews are exposed in the Django admin panel under the **Quotes** application.

### Expected Charge Templates
* **Model**: `ExpectedChargeTemplate`
* Use this interface to define the expected baseline charges for different shipment contexts.
* **Fields**: name, mode, transport mode, service scope, origin/destination countries, and active status.
* **Inline Line Items**: Modify, add, or remove template lines inline using the `ExpectedTemplateLineInline` interface. You can set the requirement level (REQUIRED, OPTIONAL, CONDITIONAL, EXCLUDED) and the expected calculation basis.

### Template Validation Reviews
* **Model**: `SpotTemplateValidationReview`
* Use this interface to inspect reviewed validation findings submitted by users on the SPOT review interface.
* **Fields**: envelope ID, finding code, canonical type, template line ID, charge line ID, fingerprint, comment, reviewer, and review time.
* **Inspection Only**: This admin dashboard is configured to be **read-only** to preserve the audit trail of operator decisions.

---

## 2. Key Operational Boundaries & Rules

When configuring validation rules or inspecting findings, keep the following architectural guardrails in mind:

1. **Validation is purely diagnostic & non-blocking**: 
   Template validation findings (missing charges, unexpected charges, etc.) act as a reference guideline for operator visibility. They do **not** block quote calculations, envelope finalisation, or quote generation.
2. **ProductCode remains authoritative**: 
   The legacy alias-to-ProductCode mapping remains the sole source of truth for downstream pricing. Validation findings are decoupled from the core pricing engine.
3. **Expectation-only impact**: 
   Edits to Expected Charge Templates and Expected Template Lines affect the validation rules/expectations only. They **never** affect quote totals, pricing, or finalisation logic.

---

## 3. QA and Development Seeding

To seed a predictable local/dev environment with stable QA fixtures representing all template validation states, run the following command:

```bash
python manage.py seed_spot_template_validation_fixtures
```

This management command creates idempotent test templates and draft SPOT envelopes covering the following states:
* **Passed**: An envelope with correct required charges.
* **Warnings**: An envelope containing warnings (missing required charges, unexpected present charges).
* **Review**: An envelope containing reviews (basis mismatches, duplicate charge families, conditional charges).
* **Template Not Found**: An envelope matching no criteria to verify the template fallback status.
