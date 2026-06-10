# Phase 10.3d — Canonical Charge Type Architecture for SPOT

## Executive Summary
This document proposes the architecture for a semantic middle layer—**Canonical Charge Type**—between raw agent labels/aliases and the final database `ProductCode` mapping within the RateEngine SPOT intake workflow. 

As confirmed in the SPOT Charge Mapping Discovery Audit (Phase 10.3) and Ambiguity Documentation Tests (Phase 10.3c), a direct 1-to-1 mapping from `ChargeAlias` to `ProductCode` is insufficient. The same raw agent label (e.g., `FSC` or `Handling`) can resolve to completely different commercial product codes depending on the quote context (bucket/section, service scope, calculation unit, and direction). 

By introducing `CanonicalChargeType` as a semantic middle layer, RateEngine can first classify **what the charge is** conceptually (e.g., "Airline Fuel Surcharge" vs. "Cartage Fuel Surcharge") and then deterministically resolve **which ledger account/product code it maps to** (e.g., `EXP-FSC-AIR` vs. `EXP-FSC-PICKUP`) based on shipment context.

```
Raw Agent Line 
  → Context Metadata (Bucket, Unit, Agent, Route)
  → CanonicalChargeType (Semantic Middle Layer)
  → ProductCode Mapping (Ledger Resolution)
  → Quote Line
```

---

## Current State & Problem Statement

### Current Normalization Flow
Currently, SPOT normalization matches raw agent charge labels directly to a `ProductCode` using the `ChargeAlias` registry:
1. Raw label is normalized (trimmed, lowercased).
2. Resolved against `ChargeAlias` filtered by mode and direction.
3. Maps directly to the associated `ProductCode`.

### Problem Statement
This alias-to-product mapping lacks context awareness:
- **FSC Ambiguity**: `FSC` (Fuel Surcharge) represents `EXP-FSC-AIR` (per-kg airline fuel) when placed in the airfreight section, but `EXP-FSC-PICKUP` (flat/percentage cartage fuel) when placed in the pickup section. Under the current schema, `FSC` can only map to one target product code unless multiple complex, duplicate aliases are registered.
- **Handling Ambiguity**: `Handling` in origin charges maps to `EXP-HANDLE-ORG`, while `Handling` in destination charges maps to `EXP-HANDLE-DST`.
- **Missing Product Codes vs. Unmapped Labels**: The system currently cannot distinguish between a label it has never seen (unmapped) and a label it understands conceptually but lacks a registered product code for in a specific corridor or direction.
- **Tax/GST Risk**: Incorrect product code resolution directly impacts GST application and general ledger revenue/cost booking.

---

## Proposed Canonical Architecture

The proposed architecture adds two new tables/models: `CanonicalChargeType` and `CanonicalToProductCodeMapping`, inserting them into the resolution path between `ChargeAlias` and `ProductCode`.

```
+------------------+         +--------------------------+         +---------------------+
|   ChargeAlias    | -------> |   CanonicalChargeType    | ------> |     ProductCode     |
| (Raw Text Match) |         |  (Semantic Abstraction)  |         | (GL Ledger Account) |
+------------------+         +--------------------------+         +---------------------+
                                          |
                                          v
                             +--------------------------+
                             | CanonicalToProductCode-  |
                             |         Mapping          |
                             |  (Context Evaluator)     |
                             +--------------------------+
```

---

## Data Model Options & Recommendations

We evaluated three data model approaches for representing `CanonicalChargeType`:

### Option A: Pure Enum (Code-Defined Only)
Define the canonical types as a standard Django Python class (e.g., `choices.TextChoices`).
- *Pros*: Zero database overhead, simple to reference in code.
- *Cons*: Cannot be updated, annotated, or extended by administrators without code releases.

### Option B: Pure Dynamic DB Table
Define canonical types entirely as database rows editable by admin users.
- *Pros*: Fully dynamic.
- *Cons*: High risk of rating engines breaking if a user deletes or renames a canonical code (e.g., `AIR_FREIGHT`) that calculations or backend logic depend on.

### Option C: Hybrid Model (Recommended MVP)
Define a `CanonicalChargeType` model where system-critical records are seeded via migrations and marked as `is_system_defined=True`. 
- **Fields**:
  - `code` (CharField, unique, db_index): Unique string identifier (e.g., `AIRLINE_FUEL_SURCHARGE`).
  - `name` (CharField): Human-readable name.
  - `category` (CharField): Grouping (e.g., `FUEL`, `DOCUMENTATION`, `FREIGHT`).
  - `is_active` (BooleanField): Toggles whether this canonical type is available for mapping.
  - `is_system_defined` (BooleanField): If `True`, prevents deletion via the admin panel.
  - `description` (TextField): Documentation explaining when this type should be applied.
- **Why Chosen**: Guarantees code-safety for hardcoded engine rules while allowing admins to customize descriptions, deactivate unused types, and map custom product codes.

---

## Initial Taxonomy Proposal
To keep the taxonomy manageable and maintainable, RateEngine will launch with **18 initial canonical charge types** grouped by category:

| Category | Canonical Code | Human-Readable Name | Description |
| :--- | :--- | :--- | :--- |
| **Air Freight** | `AIR_FREIGHT` | Air Freight Surcharge | Base airport-to-airport freight carriage cost. |
| **Origin Charges** | `ORIGIN_HANDLING` | Origin Handling Fee | Cargo handling, terminal fees at origin airport. |
| | `ORIGIN_CARTAGE` | Origin Cartage / Pickup | Land transport cargo pickup fee at origin. |
| **Destination Charges**| `DEST_HANDLING` | Destination Handling Fee | Cargo handling, terminal fees at destination. |
| | `DEST_DELIVERY` | Destination Delivery | Land transport cargo delivery fee at destination. |
| **Customs** | `CUSTOMS_CLEARANCE` | Customs Clearance Fee | Filing customs entry with regulatory authorities. |
| | `QUARANTINE_INSP` | Quarantine Inspection | Bio-security processing and physical inspection fees. |
| **Documentation** | `AWB_DOCUMENTATION` | Air Waybill Fee | Fee for issuing/processing the primary AWB. |
| | `ORIGIN_DOCS` | Origin Documentation | Local origin certificates, permits, or documentation. |
| | `DEST_DOCS` | Destination Documentation | Delivery orders, local terminal documentation fees. |
| **Security** | `SECURITY_SCREENING` | Security Screening Fee | X-Ray, physical screening, or security surcharges. |
| **Fuel / Surcharges** | `AIRLINE_FUEL` | Airline Fuel Surcharge | Fuel surcharge applied by air carrier (per kg). |
| | `CARTAGE_FUEL` | Cartage Fuel Surcharge | Fuel surcharge applied on cartage legs (flat/percent). |
| | `WAR_RISK` | War Risk Surcharge | Emergency risk or carrier safety surcharges. |
| **Admin** | `ADMIN_COMMUNICATION` | Agency & Admin Fee | General communication, file fees, or agency commissions. |
| **Conditional / Misc** | `UNKNOWN_CHARGE` | Unknown Charge Line | Unrecognized charge requiring classification. |
| | `CONDITIONAL_STORAGE` | Conditional Storage | Warehouse storage fees (conditional/accrual basis). |
| | `CONDITIONAL_DEMURRAGE`| Conditional Demurrage | Container/terminal detention fees (conditional). |

---

## Resolution Pipeline (Before vs. After)

### Before (Alias-Only)
```
[Raw Label]
    |
    v
[Normalized Label] 
    |
    v
[ChargeAlias Registry] ----(Direct Lookup)----> [ProductCode Resolved]
```

### After (Canonical Architecture)
```
[Raw Label]
    |
    v
[Normalized Label]
    |
    v
[ChargeAlias Registry] ----(Resolves Alias)----> [CanonicalChargeType]
                                                          |
                                                          v
                                            [Context Metadata Evaluator]
                                            - Mode Scope (e.g. AIR)
                                            - Direction (e.g. ORIGIN)
                                            - Unit Type (e.g. per_kg)
                                                          |
                                                          v
                                            [CanonicalToProductCodeMapping]
                                                          |
                                            +-------------+-------------+
                                            |                           |
                                     (Mapping Found)             (Mapping Missing)
                                            |                           |
                                            v                           v
                                   [ProductCode Resolved]     [Review State Triggered]
                                                              - product_code_missing
```

---

## Backward Compatibility Strategy

To ensure zero downtime, no calculation regressions, and minimal data migration risks:
1. **Coexistence of Fields**: The `ChargeAlias` model will retain its existing nullable `product_code` field while gaining a nullable `canonical_charge_type` foreign key.
2. **Resolution Fallback**:
   - If a `ChargeAlias` matches and has `canonical_charge_type` populated, the pipeline resolves the canonical type and maps it to a `ProductCode` using the new context mapping table.
   - If the matched `ChargeAlias` has `canonical_charge_type = NULL`, the system falls back to the legacy direct `product_code` reference.
3. **Data Seeding**: Seeding the 18 initial `CanonicalChargeType` records and the matching `CanonicalToProductCodeMapping` rows will occur prior to activating context-aware resolution. Existing alias mappings can be updated incrementally.

---

## ProductCode Mapping Strategy

A single `CanonicalChargeType` (e.g., `AIRLINE_FUEL`) maps to different target `ProductCode` rows based on:
- **Direction**: `ORIGIN` vs. `MAIN` (Freight Leg) vs. `DESTINATION`.
- **Shipment Mode**: `AIR` vs. `SEA` vs. `ROAD`.
- **GST / Tax Applicability**: Different product codes represent tax-exempt international transport vs. taxable domestic cartage.

### Mapping Schema Design: `CanonicalToProductCodeMapping`
- `canonical_charge_type` (ForeignKey, `CanonicalChargeType`): Target semantic type.
- `mode_scope` (CharField): Choices: `AIR`, `SEA`, `ROAD`, `ANY`.
- `direction_scope` (CharField): Choices: `ORIGIN`, `MAIN`, `DESTINATION`, `ANY`.
- `product_code` (ForeignKey, `ProductCode`): Target general ledger product code.
- `is_gst_applicable` (BooleanField): Tax override defaults for this context.

If the evaluator looks up a canonical type but no context row matches, it flags `product_code_missing` and routes the charge line to manual operator review.

---

## Review and Missing Mapping States

Introducing canonical types allows the system to identify exactly **why** a charge line cannot be normalized, storing the result in `normalization_review_reason` and `normalization_status`:

1. `canonical_type_missing`: The label matched an alias, but the alias does not point to a canonical type.
2. `product_code_missing`: The label resolved to a canonical type, but no context-aware mapping exists for the current mode/direction to a final `ProductCode`.
3. `ambiguous_canonical_type`: The label matched multiple conflicting alias records.
4. `ambiguous_product_mapping`: Multiple conflicting product code mappings matched the context.
5. `excluded_by_scope`: The canonical type is valid, but excluded based on quote scope (e.g., delivery charge in a Port-to-Port quote).
6. `conditional_charge`: The canonical type is conditional (e.g., quarantine inspection or storage) and requires keep/remove confirmation from the user.
7. `manual_review_required`: Unmapped raw label (completely unrecognized alias).

---

## Test Plan

To validate the canonical architecture during and after implementation, the following tests are required:

1. **Legacy Alias Resolution Validation**:
   - Assert that existing `ChargeAlias` records with a null `canonical_charge_type` still resolve successfully to their direct `product_code` without errors.
2. **Context-Aware Mapping Validation**:
   - Assert that `FSC` under the `airfreight` bucket resolves to `AIRLINE_FUEL` -> `EXP-FSC-AIR`.
   - Assert that `FSC` under the `origin_charges` bucket resolves to `CARTAGE_FUEL` -> `EXP-FSC-PICKUP`.
3. **Manual Resolution Safeguards**:
   - Assert that if an operator manually maps an ambiguous line (e.g. mapping `FSC` to `EXP-FSC-PICKUP`), subsequent reconciliation cycles preserve the manual choice and do not overwrite it.
4. **Missing Mappings Scenarios**:
   - Assert that resolving a canonical type without context rows records a `product_code_missing` status and triggers the manual review workflow.

---

## Risks and Mitigations

| Risk | Impact | Mitigation Strategy |
| :--- | :--- | :--- |
| **Tax/GST Misclassification** | High | Tax status must inherit directly from the final mapped `ProductCode`, not the `CanonicalChargeType`. Keep the tax logic bound to the ledger code. |
| **Mapping Engine Performance Overhead** | Medium | Cache mappings (`CanonicalToProductCodeMapping` and `CanonicalChargeType`) on application startup. Avoid repeated queries per charge line. |
| **Accidental System Code Mutation** | High | Protect seeded canonical rows with `is_system_defined=True` and block delete operations via Django model clean overrides. |
| **Override Overwriting** | Medium | Maintain the strict separation between deterministic normalization fields and manual resolution fields in `SPEChargeLineDB`. |

---

## Explicitly Deferred Scope
To keep the groundwork slice safe, the following features are **explicitly deferred**:
- **Compound Mapping Rule Engine**: Complex mathematical rule matching (defer to Phase 10.3h).
- **Self-Learning Automation**: Reusing historical learning events to automatically update mappings without human confirmation (defer to Phase 10.3i).
- **Vector / Embedding Search**: Using pgvector or semantic distance to match raw labels (out of scope).
- **Auto-Product-Code Creation**: Automatically creating new `ProductCode` records on the fly (all product codes must be pre-configured).

---

## Recommended Implementation Roadmap

1. **Phase 10.3d (Current)**: Architecture Design Proposal & Review.
2. **Phase 10.3e**: Database groundwork (models creation, initial taxonomy seed, and field migration).
3. **Phase 10.3f**: Normalization engine diagnostic logging (record canonical mappings side-by-side with legacy resolution).
4. **Phase 10.3g**: Enable context-aware lookup and deprecate legacy direct-alias mappings.
5. **Phase 10.3h**: Compound mapping rules integration.
