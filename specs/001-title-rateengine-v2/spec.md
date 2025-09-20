# Feature Specification: RateEngine v2 — Simple Rating Core

**Feature Branch**: `001-title-rateengine-v2`  
**Created**: 2025-09-21  
**Status**: Draft  
**Input**: User description: "Title: RateEngine v2 — Simple Rating Core (normalize → rate_buy → map_to_sell → tax_fx_round) Problem Current compute_quote is hard to reason about (incoterms/payment/scope branches everywhere). We need a deterministic, auditable core with minimal branching that new devs can read in one sitting. Goals (What & Why) - Replace monolith with 4 pure functions: normalize, rate_buy, map_to_sell, tax_fx_round. - Drive 60% of decisions from two tiny tables (AUDIENCE, INVOICE_CCY) and a SellRecipe per (scope,audience). - Keep Incoterms as a clamp (who pays which segment), never a price mutator. - Emit a rich snapshot with {policy_key, policy_version} (code policy v1 for now). - Preserve current math: piecewise chargeable (ceil), cheapest break w/ MIN, CAF+FX direction, GST on a single segment, final SELL rounding. In Scope (MVP) - AIR only. Scopes: A2A, A2D, D2A, D2D. PNG routing via POM + domestic bridge. - Payment terms: PREPAID, COLLECT ⇒ audience & invoice ccy via tiny tables. - BUY: lanes+breaks+fees (existing models), pick cheapest after FX normalize. - SELL: recipe executor supporting pass_through, cost_plus_pct, cost_plus_abs, fixed. - Snapshot includes golden inputs & chosen breaks/fees, CAF/FX pairs, rounding notes. Out of Scope (MVP) - New DB policy models (we’ll add versioned policies next phase). - Email sending; contact resolution (exists elsewhere). Acceptance - Given representative fixtures, v2 matches v1 totals on happy paths and is clearer to reason about. - Manual paths: if any leg missing or SPECIAL commodity/urgent → single manual result with crisp reasons (no partial pricing). - Unit tests: 10 golden cases covering imports/exports/domestic, MIN vs break, CAF direction, GST, rounding, bridge/no-bridge."

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
As a user of the Rate Engine, I want to compute a quote and have it be deterministic, auditable, and easy to understand, so that I can trust the pricing and new developers can easily maintain the system.

### Acceptance Scenarios
1. **Given** a set of representative fixtures, **When** the v2 rating core is run, **Then** the calculated totals must match the v1 totals on happy paths.
2. **Given** a quote request where any leg is missing, **When** the rating core is run, **Then** a single manual result with a clear reason is returned.
3. **Given** a quote request with a SPECIAL commodity or marked as urgent, **When** the rating core is run, **Then** a single manual result with a clear reason is returned.
4. **Given** a quote request, **When** the rating core is run, **Then** a rich snapshot is emitted with `policy_key`, `policy_version`, golden inputs, chosen breaks/fees, CAF/FX pairs, and rounding notes.

### Edge Cases
- What happens when a leg is missing from a quote request?
- What happens when a quote request is for a SPECIAL commodity?
- What happens when a quote request is marked as urgent?

## Requirements *(mandatory)*

### Functional Requirements
- **FR-001**: The system MUST replace the monolithic `compute_quote` function with four pure functions: `normalize`, `rate_buy`, `map_to_sell`, and `tax_fx_round`.
- **FR-002**: The system MUST drive decisions from `AUDIENCE` and `INVOICE_CCY` tables and a `SellRecipe` per (scope, audience).
- **FR-003**: The system MUST use Incoterms as a clamp to determine who pays for which segment, not as a price mutator.
- **FR-004**: The system MUST emit a rich snapshot with `{policy_key, policy_version}`.
- **FR-005**: The system MUST preserve the current math for piecewise chargeable weight (ceiling), cheapest break with MIN, CAF+FX direction, GST on a single segment, and final SELL rounding.
- **FR-006**: The system MUST support AIR only for the MVP.
- **FR-007**: The system MUST support scopes: A2A, A2D, D2A, D2D.
- **FR-008**: The system MUST support PNG routing via POM + domestic bridge.
- **FR-009**: The system MUST determine audience and invoice currency from payment terms (PREPAID, COLLECT) via tables.
- **FR-010**: The BUY logic MUST use existing models for lanes, breaks, and fees, and pick the cheapest after FX normalization.
- **FR-011**: The SELL logic MUST be a recipe executor supporting `pass_through`, `cost_plus_pct`, `cost_plus_abs`, and `fixed`.
- **FR-012**: The system MUST produce a single manual result with clear reasons if any leg is missing or the commodity is SPECIAL or urgent.
- **FR-013**: The system MUST have unit tests for 10 golden cases covering imports/exports/domestic, MIN vs break, CAF direction, GST, rounding, and bridge/no-bridge.

### Key Entities *(include if feature involves data)*
- **AUDIENCE**: [Represents the party being quoted, e.g., Shipper, Consignee]
- **INVOICE_CCY**: [Represents the currency of the invoice]
- **SellRecipe**: [Represents the rules for calculating the sell price based on scope and audience]
- **Snapshot**: [Represents the detailed output of a rating calculation]

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
