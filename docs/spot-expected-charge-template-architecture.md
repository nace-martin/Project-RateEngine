# Phase 10.3h — Expected Charge Template Framework for SPOT

## Executive Summary
This document proposes the architecture for an **Expected Charge Template Framework** in RateEngine's SPOT intake workflow. Building upon the semantic layer introduced by `CanonicalChargeType` (Phases 10.3d–10.3g), this framework establishes a mechanism to define what charges are commercially expected for a given shipment context (mode, route, service scope).

By comparing the actual normalized charge lines in a SPOT envelope against a matched context-specific template, the system can dynamically identify missing, unexpected, duplicated, or conditional charges. This provides clear, context-aware validation diagnostics to operators without affecting automated rating engines, ProductCode mappings, quote totals, or finalisation workflows.

---

## Current State & Problem Statement

### Current State
* **Seeded Taxonomy**: `CanonicalChargeType` defines 18 core conceptual charges.
* **Semantic Mapping**: SPOT charge lines (`SPEChargeLineDB`) populate their `canonical_charge_type` via matching aliases.
* **Line-Level Diagnostics**: Line-level anomalies write directly to `normalization_review_reason` (e.g., `canonical_type_missing`, `product_code_missing`, `ambiguous_product_mapping`).
* **Authoritative Legacy Resolution**: Legacy alias-to-ProductCode mapping remains the source of truth for downstream pricing.

### The Problem
While RateEngine can now flag individual line errors (e.g., "we don't know what this charge means"), it lacks **envelope-level structural awareness**. It cannot answer:
1. *Is the quote complete?* (e.g., Did the agent forget to include AWB documentation on an airfreight export?)
2. *Are there unexpected charges?* (e.g., Why is there a destination delivery charge in a Port-to-Port quote?)
3. *Are there duplicates?* (e.g., Why are there two separate base airfreight charge lines?)

Without an expected baseline, the system cannot catch structural quoting omissions or inclusions before the quote is finalized.

---

## Proposed Template Architecture

We propose introducing a context-matched template framework composed of two primary data models (`ExpectedChargeTemplate` and `ExpectedTemplateLine`) and an envelope-level validation engine (`ExpectedChargeValidationResult`).

```
+-----------------------------------+
|      SpotPricingEnvelopeDB        |
|     (Shipment Context JSON)       |
+-----------------------------------+
                 |
                 | (Context Match)
                 v
+-----------------------------------+
|     ExpectedChargeTemplate        |
|  (Mode, Scope, Route Constraints) |
+-----------------------------------+
                 |
                 | (1-to-Many)
                 v
+-----------------------------------+
|      ExpectedTemplateLine         |
|  (Canonical Type & Requirements)  |
+-----------------------------------+
                 |
                 | (Evaluated against actual lines)
                 v
+-----------------------------------+
| ExpectedChargeValidationResult    |
| (JSON Findings: Missing, Excluded)|
+-----------------------------------+
```

---

## Data Model Specifications

### 1. ExpectedChargeTemplate
Represents the structural baseline definition for a given shipment corridor and scope.

```python
class ExpectedChargeTemplate(models.Model):
    """
    Defines the context criteria under which a set of charge expectations is applicable.
    """
    name = models.CharField(max_length=150, help_text="e.g., Airfreight Export D2D Template")
    is_active = models.BooleanField(default=True, db_index=True)
    is_system = models.BooleanField(default=False, help_text="System-seeded templates protected from deletion")
    
    # Shipment Context Criteria
    mode = models.CharField(
        max_length=20,
        choices=[('IMPORT', 'Import'), ('EXPORT', 'Export'), ('DOMESTIC', 'Domestic')],
        db_index=True
    )
    transport_mode = models.CharField(
        max_length=20,
        choices=[('AIR', 'Air'), ('SEA', 'Sea'), ('ROAD', 'Road'), ('ANY', 'Any')],
        default='ANY',
        db_index=True
    )
    service_scope = models.CharField(
        max_length=20,
        choices=[('A2A', 'Airport-to-Airport'), ('D2D', 'Door-to-Door'), 
                 ('D2A', 'Door-to-Airport'), ('A2D', 'Airport-to-Door'),
                 ('P2P', 'Port-to-Port'), ('ANY', 'Any')],
        default='ANY',
        db_index=True
    )
    
    # Route Specificity (Hierarchical)
    origin_country = models.CharField(max_length=2, blank=True, null=True, help_text="ISO 2-letter code")
    origin_code = models.CharField(max_length=10, blank=True, null=True, help_text="Port/Airport Code (e.g., SIN)")
    destination_country = models.CharField(max_length=2, blank=True, null=True, help_text="ISO 2-letter code")
    destination_code = models.CharField(max_length=10, blank=True, null=True, help_text="Port/Airport Code (e.g., POM)")

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'expected_charge_templates'
        verbose_name = 'Expected Charge Template'
        verbose_name_plural = 'Expected Charge Templates'
```

### 2. ExpectedTemplateLine
Defines the expected presence, requirement level, and attributes of a specific canonical type within its parent template.

```python
class ExpectedTemplateLine(models.Model):
    """
    A specific canonical charge requirement associated with an ExpectedChargeTemplate.
    """
    class RequirementLevel(models.TextChoices):
        REQUIRED = 'REQUIRED', 'Expected / Must be accounted for'
        OPTIONAL = 'OPTIONAL', 'Optional (Can be billed, ignore if absent)'
        CONDITIONAL = 'CONDITIONAL', 'Conditional (Storage, Demurrage, etc.)'
        EXCLUDED = 'EXCLUDED', 'Excluded (Must not be billed under this scope)'

    template = models.ForeignKey(
        ExpectedChargeTemplate, 
        on_delete=models.CASCADE, 
        related_name='lines'
    )
    canonical_charge_type = models.ForeignKey(
        'pricing_v4.CanonicalChargeType', 
        on_delete=models.PROTECT
    )
    requirement_level = models.CharField(
        max_length=20, 
        choices=RequirementLevel.choices, 
        default=RequirementLevel.REQUIRED
    )
    expected_basis = models.CharField(
        max_length=20, 
        choices=[('per_kg', 'Per Kilogram'), ('flat', 'Flat Charge'), 
                 ('percentage', 'Percentage Basis'), ('any', 'Any')], 
        default='any',
        help_text="Expected calculation unit basis if deterministic"
    )
    
    notes = models.TextField(blank=True, null=True, help_text="Explanation/Context rules")
    sort_order = models.IntegerField(default=10)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'expected_template_lines'
        # unique_together is acceptable for MVP but may need relaxing later if the same canonical 
        # type can appear more than once by leg, basis, or service component.
        unique_together = ('template', 'canonical_charge_type')
        ordering = ['sort_order']
```
*Note: `REQUIRED` does not mean RateEngine must automatically insert or bill the charge. It simply indicates that the charge should appear in the quote lines, be included/absorbed within another charge line, or be manually acknowledged/waived by the operator.*

---

## Context Matching Strategy

When validating a SPOT envelope, the engine must resolve the most applicable `ExpectedChargeTemplate`. The resolution follows a **specificity-first hierarchy**:

1. **Step 1: Specific Corridor Matching**
   Match templates matching the exact `origin_code` and `destination_code` (e.g. SIN -> POM) + exact `mode`, `transport_mode`, and `service_scope`.
2. **Step 2: Country-to-Country Corridor Matching**
   Match templates containing the exact `origin_country` and `destination_country` + exact shipment parameters.
3. **Step 3: Region-level or Country-level Fallbacks**
   Match templates targeting only `origin_country` or `destination_country` with other route fields set to `null/ANY`.
4. **Step 4: Global Parameter Matching**
   Fall back to templates matched purely on `mode`, `transport_mode`, and `service_scope` (e.g. Global Export Air D2D Template).

If multiple templates match at the same specificity level, the matching engine chooses the one with the highest count of populated matching attributes. If no template is matched, the validation registers a `template_not_found` warning but does not block workflow progression.

---

## Expected-vs-Actual Validation Engine

Once a template is matched, the validation engine compares the template lines against the active charge lines populated in the envelope.

### Validation Algorithm
1. Retrieve all `SPEChargeLineDB` rows for the target envelope.
2. Filter out charge lines marked as deleted (and those excluded by user override, though this depends on existing database fields and should be deferred if no such override representation exists).
3. Group the actual charge lines by their `canonical_charge_type_id`.
4. Iterate over the matched `ExpectedTemplateLine` requirements:
   * **Required Charge Missing**: A `REQUIRED` template line's canonical type is absent from the actual list.
   * **Unexpected Charge Present**: An `EXCLUDED` template line's canonical type is present in the actual list.
   * **Conditional Charge Present**: A `CONDITIONAL` template line's canonical type is present (raises warning for operator confirmation).
   * **Basis Mismatch**: The unit basis of the actual charge (e.g. `flat`) does not align with the template's `expected_basis` (e.g. `per_kg`).
5. **Duplicate Checking**: Check if any `canonical_charge_type` appears more than once. If a canonical type is duplicated (and not explicitly flagged as repeatable), record `duplicate_charge_family`.

---

## Validation Diagnostic States

The validation engine registers envelope-level findings, generating the following specific diagnostic codes:

| Diagnostic Code | Severity | Description |
| :--- | :--- | :--- |
| `expected_charge_missing` | Warning | A required canonical charge was completely omitted. |
| `unexpected_charge_present` | Warning | An excluded charge (e.g., delivery on a Port-to-Port quote) was included. |
| `duplicate_charge_family` | Review | Multiple lines resolved to the same canonical type when only one was expected. |
| `expected_basis_mismatch` | Review | A charge line is calculated on a basis different from the template definition. |
| `conditional_charge_present`| Review | A conditional charge (e.g. Storage) is present and requires confirmation. |
| `template_not_found` | Review | No applicable expectation template could be resolved for this context. |
| `template_not_applicable` | Review | A template exists but was skipped due to validation rules. |

---

## Interactions & Integrations

### 1. Separation from Line-Level `normalization_review_reason`
Line-level normalization is **deterministic and format-based** (e.g. missing product code mapping, unrecognized aliases). Template validation is **semantic and structural**.
* To prevent data corruption, **do not overload** the line-level `normalization_review_reason` field with template status.
* Store template validation results in a separate table: `ExpectedChargeValidationResult`.

### 2. Validation Persistence: `ExpectedChargeValidationResult`
This stores the structured outcome of the template comparison.

```python
class ExpectedChargeValidationResult(models.Model):
    """
    Stores the envelope-level outcome of Expected Charge Template comparison.
    """
    envelope = models.OneToOneField(
        'quotes.SpotPricingEnvelopeDB', 
        on_delete=models.CASCADE, 
        related_name='template_validation'
    )
    template = models.ForeignKey(
        ExpectedChargeTemplate, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True
    )
    
    status = models.CharField(
        max_length=20,
        choices=[('PASSED', 'Passed'), ('WARNINGS', 'Contains Warnings'), ('UNCHECKED', 'Unchecked')],
        default='UNCHECKED'
    )
    
    # JSON containing structured array of findings:
    # [{"code": "expected_charge_missing", "canonical_type": "AWB_DOCUMENTATION", "message": "..."}]
    findings_json = models.JSONField(default=list, blank=True)
    
    validated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'expected_charge_validation_results'
```

---

## MVP Scope vs. Deferred Features

### Recommended MVP Scope
1. **Design Documentation** (This document).
2. **Model Groundwork**: Introduce `ExpectedChargeTemplate`, `ExpectedTemplateLine`, and `ExpectedChargeValidationResult` tables.
3. **Template Registry Seeding**: Seed a single global default template for export air D2D shipments to test the framework.
4. **Validation Logic (Non-blocking)**: Implement the template-matching and evaluation logic. Generate findings in the database but **do not block quote finalisation or change pricing logic**.

### Explicitly Deferred Scope
* **Auto-Creation of Charges**: The engine must **never** automatically insert a missing charge into a quote.
* **Finalisation Blocking**: Rejecting finalisation if warnings exist (operator review only).
* **Self-Learning Templates**: Automatically adjusting templates based on past quotes (must be manually adjusted or seeded).
* **AI Template Classification**: Using LLMs to construct template logic.
* **Agent-Level Custom Templates**: Templates customized per-agent (MVP will be route/mode/scope specific only).
* **Frontend Surfacing**: Surfacing alerts in the dashboard UI.

---

## Test Plan

To validate the framework during Phase 10.3i/10.3j, the following tests are required:

1. **Context Resolution Tests**:
   * Assert correct template selection for an airfreight export quote SIN -> POM.
   * Assert fallback to global export templates when specific corridor templates are absent.
2. **Validation Logic Tests**:
   * Assert `expected_charge_missing` when `AIRLINE_FUEL` is missing from an airfreight quote.
   * Assert `unexpected_charge_present` when a delivery charge is found on a Port-to-Port template.
   * Assert `duplicate_charge_family` when multiple base freight rows exist.
   * Assert `expected_basis_mismatch` when actual unit (`flat`) differs from template expectation (`per_kg`).
3. **Safety & Stability Tests**:
   * Verify quote totals and finalisation workflows remain unblocked when validation results contain `expected_charge_missing` warnings.
   * Verify database integrity constraints prevent duplicate template lines for the same canonical type.

---

## Risks and Mitigations

| Risk | Impact | Mitigation Strategy |
| :--- | :--- | :--- |
| **False Positive Noise** | Medium | Keep templates minimal. Flag non-essential local charges as `OPTIONAL` rather than `REQUIRED` to avoid warning fatigue. |
| **Ambiguity in Service Scope** | High | Default scope to `ANY` if context parsing cannot determine service terms (e.g. missing `D2D` vs `A2A` tags). |
| **Template Overfitting** | Medium | Utilize country-level fallback templates before regional ones, ensuring local tax/regulatory variances are respected without requiring a template for every airport corridor. |
| **Operator Blind Trust** | Low | Label all template diagnostics explicitly as warnings, keeping finalisation controls manual and self-guided. |

---

## Implementation Roadmap

* **Phase 10.3h (Current)**: Expected Charge Template Framework Architecture Design.
* **Phase 10.3i**: Database groundwork models (`ExpectedChargeTemplate`, `ExpectedTemplateLine`, and `ExpectedChargeValidationResult`).
* **Phase 10.3j**: Expected-vs-Actual comparison execution engine.
* **Phase 10.3k**: Non-blocking warning display in admin panel and API serialization.
* **Phase 10.3l**: Fine-tuning parameters, additional seeded templates, and corridor verification.
* **Phase 10.4**: Begin canonical-to-ProductCode mapping deployment.
