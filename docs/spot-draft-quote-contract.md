# Draft Quote Assistant - Data Contract

## Purpose
This document defines the backend-to-frontend Draft Quote data contract for SPOT intake in RateEngine. The Draft Quote Assistant acts as a bridge between raw, unstructured document data (such as emails, PDF quotes) and structured, validated inputs needed for the deterministic RateEngine V4 calculation. It assists human operators to quickly construct error-free customer quotes while ensuring that no commercially relevant data is silently invented or silently discarded.

## Principles
1. **No Silent Invention/Discard**: Every suggestion must be backed by explicit evidence extracted from the document. Any ambiguous or commercial-looking item must be categorized or highlighted for review.
2. **Deterministic Validation**: Final quote pricing and calculation remains the job of the deterministic V4 pricing engine, while the Draft Quote represents the structured intake state.
3. **Traceability**: All values, product codes, and terms suggested must link back to their textual source evidence.
4. **Correction Integrity**: Human operators are the final authority; the schema must facilitate tracking user overrides and corrections.

## Non-Goals
* Re-implementing parsing algorithms or AI extraction logic.
* Building the user interface.
* Implementing user profile customization.
* Database migrations (this contract defines the communication payload and schemas only).

## Root JSON Structure
The draft quote payload consists of the following key attributes at the root:

* `contract_version`: SemVer string matching the API schema version (e.g., `"1.0.0"`).
* `quote_summary`: Brief human-readable description of the draft quote context.
* `shipment_context`: Basic shipment parameters (e.g., origin, destination, weight, volume, pieces).
* `supplier_context`: Details about the carrier or agent providing the quote.
* `freight`: Main freight details (mode, service level, etc.).
* `suggested_charges`: List of identified charges and surcharges.
* `commercial_terms`: Extracted terms (e.g., validity dates, subject-to clauses, exclusions).
* `warnings`: Top-level validation warnings (e.g., missing data, overall math mismatch).
* `unclassified_items`: Text blocks or lines that look commercial but could not be parsed into a charge or term.
* `ignored_items`: Lines/text blocks explicitly ignored with reasons (e.g., boilerplate disclosures).
* `totals_validation`: Mathematical comparison of extracted totals vs. the sum of individual suggested charges.
* `review_queue`: Aggregated items requiring manual human intervention (e.g., conflicts, unclassified items).
* `correction_actions`: Standardized action codes that the user can take to remediate issues.
* `metadata`: Contextual tracking details (timestamps, document source, sender-based memory placeholders).

---

## Field Definitions

### Suggested Charge
Each item in `suggested_charges` supports:
* `id`: Unique identifier (UUID or stable hash).
* `status`: Current workflow state (see Status Taxonomy).
* `display_label`: User-friendly label for display.
* `raw_label`: Raw textual description from the document.
* `suggested_product_code`: Inferred ERP product code (or `null`).
* `product_code_conflict`: Boolean flag indicating if multiple codes match or if a code is ambiguous.
* `bucket`: Inbound categorization bucket (`airfreight`, `origin_charges`, `destination_charges`, or `unclassified`).
* `currency`: 3-letter currency code (e.g., `USD`, `PGK`).
* `amount`: Numeric value of the charge.
* `rate`: Unit rate (or `null` if flat or percentage).
* `unit`: Charge unit type (e.g., `per_kg`, `flat`, `per_awb`, `per_shipment`, `percentage`).
* `calculation_basis`: Inferred calculation basis (e.g., chargeable weight, actual weight).
* `minimum_charge`: Inferred minimum charge (or `null`).
* `percentage_base`: Description of what a percentage charge applies to (e.g., `ocean_freight`).
* `quantity`: Quantity multiplier (or `null`).
* `include_in_totals`: Boolean indicating if this charge should be added to the calculated total.
* `conditions`: String descriptions of applicability conditions.
* `warnings`: Validation warnings specific to this charge.
* `review_reason`: Descriptive string explaining why this charge requires review.
* `evidence`: Pointer to source text (see Evidence Model).
* `similarity_group_id`: Stable identifier grouping identical charges across similar documents or segments for bulk-editing.
* `correction_actions`: Action options offered to the user (e.g., select correct product code, accept currency warning).

### Evidence Model
Provides traceability:
* `source_text`: Exact matched text from the source document.
* `page`: Page number (1-based, nullable).
* `section`: Section identifier/header (nullable).
* `row_index`: Zero-based row number within a table structure (nullable).
* `table_index`: Zero-based table sequence number (nullable).
* `document_reference`: ID or filename of the source document (nullable).
* `bounding_box`: Coordinate box coordinates `[x_min, y_min, x_max, y_max]` for highlighting in PDFs (nullable).
* `extraction_note`: Qualitative note from the extraction system (nullable).

### Commercial Terms Model
Extracts terms and conditions:
* `type`: Categorization of the term (e.g., `validity`, `density_ratio`, `carrier_acceptance`, `exclusion`).
* `text`: Raw text of the term.
* `normalized_value`: Inferred value mapping (e.g., `"2026-07-31"` for validity date).
* `status`: Workflow status.
* `evidence`: Evidence block.
* `review_reason`: Explain why this term requires user confirmation.

### Totals Validation Model
* `math_balances`: Boolean indicating if `extracted_total = calculated_total` (within tolerance).
* `currency_consistent`: Boolean indicating if all charges have consistent currency.
* `extracted_total`: The total explicitly stated in the document (or `null`).
* `calculated_total`: The sum of all active suggested charges.
* `difference`: Numeric difference between calculated and extracted totals.
* `tolerance`: Tolerable variance allowance.
* `warnings`: Specific totals-related warnings.

---

## Status Taxonomy
The workflow status of any extracted charge or term must strictly belong to one of these states:
1. `suggested`: Autoparsed with high confidence, waiting for final user review/acceptance.
2. `needs_review`: Highlighted because of conflicts, warnings, or low confidence.
3. `unclassified`: Extracted text snippet containing commercial-looking patterns but not successfully parsed.
4. `ignored`: Explicitly skipped during processing, with an ignored reason.
5. `accepted_by_user`: Explicitly reviewed and confirmed by the user.

> [!WARNING]
> Do NOT use `verified` as a system-generated state. User confirmation sets the state to `accepted_by_user`.

---

## Similarity and Bulk-Edit Support
* **`similarity_group_id`**: Assigned to charges sharing identical raw labels, unit profiles, or product codes. This enables frontends to present bulk-override options (e.g. updating the product code of a charge updates all matching charges in the group).

---

## Sender-Based Memory Placeholders
The metadata section contains placeholders for historical mapping memory:
* `sender_domain`: Domain of the email sender.
* `historical_override_rules`: Inferred product code rules learned from previous user edits of the same sender's quotes. (No logic is implemented in this phase).

---

## Frontend Requirements Unlocked by this Contract

This contract unlocks specific features in the exception-handling frontend workspace:
1. **Display Draft Quote Summary**: Renders header metadata, route, origin/destination, and shipment metrics.
2. **Show Suggested Charges**: Tabular list of suggested charges grouped by bucket (freight, origin, destination).
3. **Show Source Evidence**: Highlighting the raw source text when hovering over any field, or drawing a bounding box over the source PDF.
4. **Show Needs-Review Queue**: Highlighting charges/terms with status `needs_review` or `unclassified` in a specialized correction list.
5. **Allow Inline Correction**: Providing dropdowns to change product codes, checkboxes to toggle inclusion in totals, and text inputs to adjust values.
6. **Allow Bulk Correction**: Using `similarity_group_id` to let users correct matching charges at once.
7. **Show Commercial Terms**: Separate section for validity dates, subject-to clauses, and density ratios.
8. **Show Totals/Currency Warnings**: Clear validation flags if totals mismatch or if multiple currencies are mixed.
9. **Accept All / Accept Selected Actions**: Quick action buttons to accept all clean suggestions or commit manually adjusted lines.
10. **Preserve Audit Trail of User Corrections**: Keeping a history of modified fields for future intake learning.
