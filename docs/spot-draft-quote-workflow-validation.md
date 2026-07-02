# Draft Quote Workflow Validation Analysis

This document validates whether the Draft Quote Contract defined in Phase 8C.6 (via `DraftQuoteSchema`) is sufficient to support the future Exception Workspace UI using the realistic messy supplier scenario from `hard_case_air_import.json`.

---

## Messy Supplier Scenario User Workflow

Based on the [hard_case_air_import.json](file:///c:/Users/commercial.manager/dev/Project-RateEngine/backend/quotes/tests/fixtures/draft_quote_contract/hard_case_air_import.json) fixture (SIN to POM air import quote), the exception handling workspace behaves as follows:

### 1. What the User Sees First
* **Header Context**: Singapore (SIN) to Port Moresby (POM) standard air freight quote from Qantas Air Cargo, with a chargeable weight of 200.0 kg.
* **Totals Comparison Summary Banner**: A clear alert showing a totals mismatch:
  - Calculated Total: **USD 1,145.00**
  - Extracted Total: **USD 1,100.00**
  - Mismatch: **USD 45.00** difference.
* **Review Queue Panel**: A summary side panel listing 3 unresolved items requiring operator intervention before quote submission.

### 2. Items Requiring Action (Review Queue)
* **Fuel Surcharge (`chg-002`)**: Highlighted in red/amber. The system flags this charge as `needs_review` because of an ambiguous ProductCode mapping (it matches both `FSC-AIR` and `SUR-FUEL` in the catalog rules).
* **Security Charge (`chg-003`)**: Highlighted in amber. The system flags this as `needs_review` with an "Inherited currency warning" because the currency USD was not explicitly found in the row text, but was inferred from the parent freight block.
* **Unclassified Item (`unclass-001`)**: Highlighted in yellow. The text snippet `"Possible cartage / transfer charge: SGD 120.00..."` was flagged as commercial-looking but could not be parsed into a structured charge.

### 3. Items to Accept in Bulk
* **Surcharges Group (`sim-surcharges`)**: The Fuel Surcharge (`chg-002`) and Security Surcharge (`chg-003`) both share `similarity_group_id: "sim-surcharges"`. If the user updates the product code mapping or currency of one, the UI can offer to apply this correction to the other matching surcharge in the group.

### 4. Items Requiring Inline Correction
* **Product Code Selection**: The Fuel Surcharge (`chg-002`) requires the user to select the correct product code from a dropdown populated with the `correction_actions` options (`FSC-AIR` or `SUR-FUEL`).
* **Currency Confirmation**: The Security Charge (`chg-003`) requires the user to confirm the inherited currency (USD) or type in another.
* **Exclusion Toggle**: The user can toggle a checkbox to ignore or exclude a charge (e.g. toggling `include_in_totals` or updating its status to `ignored` with a reason).

### 5. Commercial Terms Review
The user sees a list of extracted terms to verify:
* **Validity**: End date is verified as `2026-07-31` (mapped from raw text).
* **Exclusion**: The text explicitly excludes customs clearance, duties, and local delivery in POM. The user verifies that these matching components are correctly excluded from the quote template.

### 6. Source Evidence Display
* When the user hovers over the Fuel Surcharge rate, a tooltip or sidebar displays the exact source text: `"FSC rate: USD 0.85 per kg"` on Page 1, Section `"Freight surcharges"`, along with the document reference `"QAN-QUOTE-9912.pdf"`.
* If a PDF viewer is loaded in the workspace, the system draws a highlight rectangle over the bounding box coordinates `[10.0, 75.0, 200.0, 95.0]`.

### 7. Final User Acceptance
* Clicking "Accept and Sync" changes the status of all resolved charges to `accepted_by_user`.
* The corrected values (e.g. confirmed currency, selected product codes) are packaged and sent to the V4 Pricing Engine for final deterministic calculations.

---

## Required UI Action Mapping

This table maps the required Exception Workspace UI actions to the `DraftQuoteSchema` fields:

| UI Action | Contract Field | Sufficiency | Notes |
| :--- | :--- | :--- | :--- |
| **Accept all suggestions** | `suggested_charges[].status` | **Fully Supported** | UI filters for status `suggested`, allowing the user to bulk approve all cleanly suggestion lines. |
| **Accept selected suggestions** | `suggested_charges[].status` | **Fully Supported** | Individual check-boxes update selected line statuses to `accepted_by_user`. |
| **Edit a charge** | `suggested_charges[].amount`, `rate`, `quantity` | **Fully Supported** | Direct mapping to fields. |
| **Change ProductCode** | `suggested_charges[].suggested_product_code` | **Fully Supported** | Editable field; UI shows dropdown options from `correction_actions` or standard master data. |
| **Change bucket** | `suggested_charges[].bucket` | **Fully Supported** | Editable string (`airfreight`, `origin_charges`, `destination_charges`). |
| **Change currency** | `suggested_charges[].currency` | **Fully Supported** | Editable string. |
| **Change unit/calculation basis** | `suggested_charges[].unit`, `calculation_basis` | **Fully Supported** | Editable fields. |
| **Apply correction to similar items** | `suggested_charges[].similarity_group_id` | **Fully Supported** | UI groups rows with matching IDs to propose bulk corrections. |
| **Mark charge ignored/excluded** | `ignored_items` / `suggested_charges[].status` | **Fully Supported** | Change status to `ignored` and append to `ignored_items` with an `ignored_reason`. |
| **Review commercial term** | `commercial_terms` | **Fully Supported** | Terms have `status`, `type`, `normalized_value`, and `evidence` fields. |
| **Resolve unclassified item** | `unclassified_items[]` | **Fully Supported** | Unclassified items have IDs and `correction_actions` options (e.g., `ADD_AS_CHARGE`, `IGNORE_ITEM`). |
| **Preserve audit history** | `metadata.audit_trail` (or top-level) | **Partially Supported** | Currently there is no explicit `audit_trail` list inside the contract schema. A placeholder exists inside `metadata`, but we should formalize it. |

---

## Contract Gap Table

| Status | Gap Identified | Recommended Contract Change |
| :--- | :--- | :--- |
| **Supported Now** | Bounding box coordinates for visual PDF highlights | None. Supported via `bounding_box` in `EvidenceSchema`. |
| **Supported Now** | Actions list driving the resolution dropdowns | None. Supported via `correction_actions` list. |
| **Partially Supported** | Historical user edits audit trail preservation | Add an optional `user_audit_log` field to `metadata` or as a top-level property to track exact changes (e.g. `{"field": "currency", "old": "USD", "new": "SGD", "user": "testuser"}`). |
| **Missing** | Original file metadata (e.g., size, content type, processing time) | Add a `document_metadata` dictionary under `metadata` containing file size, file hash, processing duration, and parser logs. |

---

## Recommended Contract Enhancements

To make the PR #228 contract bulletproof for the frontend team, we recommend adding an optional `user_audit_log` field inside `metadata` to standardize tracking of operator corrections. No logic is required in this phase; standardizing the typed placeholder is enough to unlock frontend implementation.

```python
# Proposed format for metadata.user_audit_log:
# [
#   {
#     "timestamp": "2026-07-02T19:15:00Z",
#     "user": "operator_john",
#     "target_id": "chg-002",
#     "field": "suggested_product_code",
#     "original_value": null,
#     "corrected_value": "FSC-AIR"
#   }
# ]
```
