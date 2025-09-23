# Feature Specification: AIR · Import · A2D — Deterministic currency & destination-fee policy (PREPAID & COLLECT)

**Feature Branch**: `003-jsonpath-c-users`
**Created**: 2025-09-22
**Status**: Draft
**Input**: User description: "Title: AIR · Import · A2D — Deterministic currency & destination-fee policy (PREPAID & COLLECT) Goal Make quotes boringly correct. Currency and fee selection for AIR imports on A2D lanes must be 100% deterministic so sales sees only the right destination charges and invoices land in the right currency every time. Business outcomes - Quotes show only destination-side services for A2D imports. - PREPAID importers get invoices in the origin country currency (e.g., AU→PG → AUD). - COLLECT importers get invoices in the destination country currency (e.g., AU→PG → PGK). - Missing BUY data never throws a 500; we return a clean, actionable reason. Scope (this feature only) - Mode: AIR - Direction: Import - Service scope: A2D (Airport→Door) - Payment terms: PREPAID, COLLECT - Commodity: General (GCR) - Destination market example: AU→PG (BNE/SYD → POM) Non-goals (out of scope for now) - Other scopes (A2A, D2A, D2D) - Address book, email generation, or UI polish beyond needed fields - New DB models (policy is configuration/logic only) Core rules (must-haves) R1. Invoice currency • PREPAID (shipper pays): invoice currency = ORIGIN country currency (e.g., AUD for AU→PG). • COLLECT (consignee pays): invoice currency = DESTINATION country currency (e.g., PGK for AU→PG). • Audience derives from payment term + direction; no separate UI toggle. R2. Fee menu (A2D import) • Include only DESTINATION-side services: customs clearance, terminal/handling, cartage/delivery, delivery fuel/x-ray where applicable. • Exclude ORIGIN-side services (pickup, export docs, origin x-ray/fuel). • If a fee depends on a base line that isn’t present (percent-of, etc.), skip it and record a warning in a machine-readable snapshot. R3. Missing BUY handling • If a BUY lane or required break is missing, mark `is_incomplete = true`, add a “Manual Rate Required” line with the reason, and continue. • Never crash, never silently invent numbers. R4. Totals & reporting • Response includes `totals.invoice_ccy` and itemized sell lines with stable `code`s, all aligned to the invoice currency. • Include a snapshot that explains which policy/recipe decided each line and any skips/warnings. Primary user story As a salesperson, when I quote an AIR import A2D shipment, I want the engine to pick the correct destination fee menu and the correct invoice currency based on payment term so I can send a consistent, auditable quote without fiddling with settings. Acceptance criteria AC1. Given PREPAID A2D import AU→PG (e.g., BNE→POM, 81kg), then `invoice_ccy = "AUD"` and only destination-side services appear. AC2. Given COLLECT A2D import AU→PG (same input), then `invoice_ccy = "PGK"` and only destination-side services appear. AC3. If a dependent fee’s base is missing, that fee is skipped and the snapshot records why. AC4. If BUY lane/break is missing, `is_incomplete = true` with a clear “Manual Rate Required” reason; no 500s. AC5. Golden tests cover both PREPAID and COLLECT for AU→PG. Edge cases to honor - Zero/very low weight (MIN vs stepped breaks) — still destination fees only. - Multi-piece inputs that change chargeable weight but not policy. - Fees priced per AWB vs per KG — align currency to `invoice_ccy`. Success metrics - 0 server errors across test scenarios. - 100% of A2D import quotes show only destination-side fees. - 100% currency routing accuracy: PREPAID→AUD, COLLECT→PGK. - Snapshot present on every response with at least policy and reasons arrays. Deliverables - Spec document (this). - Plan with test-first approach and recipes/policies outlined. - Tasks list ordered as: tests → dataclasses → recipes → service → endpoint, plus seeds/quickstart. - Quickstart showing POST examples for PREPAID and COLLECT and expected `invoice_ccy`. Notes - Keep the language business-level; implementation details belong in /plan and /tasks. - When data is missing, prefer an explicit `is_incomplete` reason over fallback magic."

---

## User Scenarios & Testing *(mandatory)*

### Primary User Story
As a salesperson, when I quote an AIR import A2D shipment, I want the engine to pick the correct destination fee menu and the correct invoice currency based on payment term so I can send a consistent, auditable quote without fiddling with settings.

### Acceptance Scenarios
1. **Given** a PREPAID A2D import from AU to PG (e.g., BNE to POM, 81kg), **When** a quote is requested, **Then** the `invoice_ccy` MUST be "AUD" and the quote MUST only include destination-side services.
2. **Given** a COLLECT A2D import from AU to PG (e.g., BNE to POM, 81kg), **When** a quote is requested, **Then** the `invoice_ccy` MUST be "PGK" and the quote MUST only include destination-side services.
3. **Given** a required BUY lane or rate break is missing for an A2D import, **When** a quote is requested, **Then** the response MUST have `is_incomplete = true` and include a "Manual Rate Required" line item with a clear reason.
4. **Given** a fee is configured to be a percentage of a base fee that is not present in the quote, **When** a quote is requested, **Then** that fee MUST be skipped and a warning MUST be recorded in the machine-readable snapshot.

### Edge Cases
- What happens when zero/very low weight (MIN vs stepped breaks)? The system should still apply destination fees only.
- How does the system handle multi-piece inputs that change chargeable weight? The policy should not change.
- How does the system handle fees priced per AWB vs per KG? All fees must be aligned to the `invoice_ccy`.

## Requirements *(mandatory)*

### Functional Requirements
- **FR-001**: System MUST determine the invoice currency based on the payment term and direction.
- **FR-002**: For PREPAID A2D imports, the invoice currency MUST be the currency of the origin country.
- **FR-003**: For COLLECT A2D imports, the invoice currency MUST be the currency of the destination country.
- **FR-004**: For A2D imports, the system MUST only include destination-side services in the quote.
- **FR-005**: System MUST exclude origin-side services from A2D import quotes.
- **FR-006**: If a required BUY lane or rate break is missing, the system MUST mark the quote as incomplete and provide a reason.
- **FR-007**: System MUST NOT crash or return a 500 error if BUY data is missing.
- **FR-008**: System MUST include a machine-readable snapshot in the response explaining the policy decisions.
- **FR-009**: The response MUST include `totals.invoice_ccy`.
- **FR-010**: All itemized sell lines MUST be aligned to the invoice currency.

### Key Entities *(include if feature involves data)*
- **Policy**: A set of rules that determines the currency and fee menu for a quote.
- **Recipe**: A component of a policy that defines a specific calculation or rule.
- **Snapshot**: A machine-readable record of the policy decisions made during the quoting process.
