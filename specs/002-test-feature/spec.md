# Feature Specification: AIR · Import · A2D (Airport→Door) v2 rating policy — PREPAID & COLLECT

**Feature Branch**: `002-test-feature`  
**Created**: Monday 22 September 2025  
**Status**: Draft  
**Input**: User description: "Title: AIR · Import · A2D (Airport→Door) v2 rating policy — PREPAID & COLLECT Goal - Make currency + fee selection 100% deterministic for AIR imports on A2D lanes (e.g., AU→PG). - Remove ambiguity so quotes are consistent and auditable, regardless of rate-card coverage. Business Outcomes - Sales sees only the correct destination service menu for A2D imports. - Invoices land in the right currency: AUD for PREPAID importers, PGK for COLLECT importers. - No 500s or silent fallbacks; when data is missing, we return a clear, actionable reason. Scope (this spec only) - Mode: AIR - Direction: Import (origin outside destination country) - Scope: A2D (Airport→Door) - Payment Terms: PREPAID, COLLECT - Commodity: General Cargo (GCR) Rules (must-haves) 1) Audience & invoice currency - PREPAID (shipper pays): invoice currency = ORIGIN country currency (e.g., AU→PG → AUD). - COLLECT (consignee pays): invoice currency = DESTINATION country currency (e.g., AU→PG → PGK). - Audience is derived from payment term and direction; no UI toggle required. 2) Fee menu (A2D import) - Include only DESTINATION-side services: e.g., customs clearance, international terminal/handling, delivery/cartage, delivery fuel/x-ray where applicable. - Exclude ORIGIN-side services (pickup, export docs, origin x-ray, origin fuel) for A2D imports. - If a fee requires a base (e.g., “percent-of” another service) and the base isn’t present, skip that fee and record a warning in the snapshot. 3) Missing rate handling - If a BUY lane or required break is missing, mark the quote `is_incomplete = true` and add a “Manual Rate Required” line with a reason. - Still compute sell totals from any available policy-driven items; never crash. 4) Totals & reporting - Response includes `totals.invoice_ccy`. - Provide itemized sell lines with stable `code` identifiers and currencies aligned to the invoice currency. - Provide a machine-readable `snapshot` describing which policy/recipe decided the lines. Inputs (examples) - Example A (PREPAID): BNE → POM, A2D, pieces=[{weight_kg:81}] - Expected `totals.invoice_ccy = "AUD"` - Sell lines: dest-side menu only. - Example B (COLLECT): BNE → POM, A2D, pieces=[{weight_kg:81}] - Expected `totals.invoice_ccy = "PGK"` - Sell lines: dest-side menu only. Acceptance Criteria - Given PREPAID A2D import, engine returns invoice_ccy=origin currency and only dest-side services. - Given COLLECT A2D import, engine returns invoice_ccy=destination currency and only dest-side services. - When “percent-of” base is absent, the dependent line is skipped and snapshot records why. - When BUY data is missing, engine returns `is_incomplete=true` with a clear reason but no server error. - Golden tests cover both PREPAID and COLLECT for at least AU→PG lanes. Non-Goals (out of scope now) - Door pickup, export clearance, or other scopes (D2A, A2A, D2D). - Address book or email generation. - UI work beyond minimal fields required to call the endpoint. Why this matters - Locks core policy so sales quotes are correct by default. - Prevents regressions as we add more scopes, terms, and markets."

## Execution Flow (main)
```
1. Parse user description from Input
   → If empty: ERROR "No feature description provided"
2. Extract key concepts from description
   → Identify: actors, actions, data, constraints
3. For each unclear aspect:
   → Mark with [NEEDS CLARIFICATION: specific question]
4. Fill User Scenarios & Testing section
   → If no clear user flow: ERROR "Cannot determine user scenarios"
5. Generate Functional Requirements
   → Each requirement must be testable
   → Mark ambiguous requirements
6. Identify Key Entities (if data involved)
7. Run Review Checklist
   → If any [NEEDS CLARIFICATION]: WARN "Spec has uncertainties"
   → If implementation details found: ERROR "Remove tech details"
8. Return: SUCCESS (spec ready for planning)
```

---

## ⚡ Quick Guidelines
- ✅ Focus on WHAT users need and WHY
- ❌ Avoid HOW to implement (no tech stack, APIs, code structure)
- 👥 Written for business stakeholders, not developers

### Section Requirements
- **Mandatory sections**: Must be completed for every feature
- **Optional sections**: Include only when relevant to the feature
- When a section doesn't apply, remove it entirely (don't leave as "N/A")

### For AI Generation
When creating this spec from a user prompt:
1. **Mark all ambiguities**: Use [NEEDS CLARIFICATION: specific question] for any assumption you'd need to make
2. **Don't guess**: If the prompt doesn't specify something (e.g., "login system" without auth method), mark it
3. **Think like a tester**: Every vague requirement should fail the "testable and unambiguous" checklist item
4. **Common underspecified areas**:
   - User types and permissions
   - Data retention/deletion policies  
   - Performance targets and scale
   - Error handling behaviors
   - Integration requirements
   - Security/compliance needs

---

## User Scenarios & Testing *(mandatory)*

### Primary User Story
As a user of the Rate Engine, I want currency and fee selection to be 100% deterministic for AIR imports on A2D lanes, so that quotes are consistent, auditable, and accurate regardless of rate-card coverage.

### Acceptance Scenarios
1. **Given** PREPAID A2D import, **When** the engine processes the quote, **Then** it returns `invoice_ccy=origin currency` and only destination-side services.
2. **Given** COLLECT A2D import, **When** the engine processes the quote, **Then** it returns `invoice_ccy=destination currency` and only destination-side services.
3. **Given** a fee requires a base and the base is absent, **When** the engine processes the quote, **Then** the dependent line is skipped and the snapshot records why.
4. **Given** BUY data is missing, **When** the engine processes the quote, **Then** it returns `is_incomplete=true` with a clear reason but no server error.
5. **Given** golden tests, **When** they are run, **Then** they cover both PREPAID and COLLECT for at least AU→PG lanes.

### Edge Cases
- What happens when a fee requires a base and the base isn't present?
- What happens when BUY data (lane or required break) is missing?

## Requirements *(mandatory)*

### Functional Requirements
- **FR-001**: The system MUST ensure that for PREPAID (shipper pays) AIR Import A2D quotes, the invoice currency is the ORIGIN country currency (e.g., AU→PG → AUD).
- **FR-002**: The system MUST ensure that for COLLECT (consignee pays) AIR Import A2D quotes, the invoice currency is the DESTINATION country currency (e.g., AU→PG → PGK).
- **FR-003**: The system MUST derive the Audience from the payment term and direction, without requiring a UI toggle.
- **FR-004**: The system MUST include only DESTINATION-side services (e.g., customs clearance, international terminal/handling, delivery/cartage, delivery fuel/x-ray where applicable) in the fee menu for A2D imports.
- **FR-005**: The system MUST exclude ORIGIN-side services (pickup, export docs, origin x-ray, origin fuel) from the fee menu for A2D imports.
- **FR-006**: If a fee requires a base (e.g., "percent-of" another service) and the base isn't present, the system MUST skip that fee and record a warning in the snapshot.
- **FR-007**: If a BUY lane or required break is missing, the system MUST mark the quote `is_incomplete = true` and add a "Manual Rate Required" line with a reason.
- **FR-008**: The system MUST still compute sell totals from any available policy-driven items, even if BUY data is missing, and never crash.
- **FR-009**: The response MUST include `totals.invoice_ccy`.
- **FR-010**: The system MUST provide itemized sell lines with stable `code` identifiers and currencies aligned to the invoice currency.
- **FR-011**: The system MUST provide a machine-readable `snapshot` describing which policy/recipe decided the lines.

### Key Entities *(include if feature involves data)*
- **Quote**: Represents the overall quote request and its computed results.
- **Snapshot**: Detailed output of a rating calculation, including policy/recipe decisions.
- **Fee**: Represents a service charge, potentially with dependencies on other services.

---

## Review & Acceptance Checklist
*GATE: Automated checks run during main() execution*

### Content Quality
- [ ] No implementation details (languages, frameworks, APIs)
- [ ] Focused on user value and business needs
- [ ] Written for non-technical stakeholders
- [ ] All mandatory sections completed

### Requirement Completeness
- [ ] No [NEEDS CLARIFICATION] markers remain
- [ ] Requirements are testable and unambiguous  
- [ ] Success criteria are measurable
- [ ] Scope is clearly bounded
- [ ] Dependencies and assumptions identified

---

## Execution Status
*Updated by main() during processing*

- [ ] User description parsed
- [ ] Key concepts extracted
- [ ] Ambiguities marked
- [ ] User scenarios defined
- [ ] Requirements generated
- [ ] Entities identified
- [ ] Review checklist passed

---
