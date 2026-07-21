# RateEngine Phase 16C — International Air Journey and Leg-Aware ProductCode Architecture

**Document ID:** RE-ARCH-16C-AIR-001  
**Version:** 1.1  
**Architecture date:** 21 July 2026  
**Status:** Authoritative design baseline  
**Source rules:** `docs/business-rules/phase-16a-air-freight-journey-productcode-rules.md` version 1.1  
**Source requirements:** `docs/business-rules/phase-16b-air-freight-requirements-gap-assessment.md` version 1.0  
**Applies to:** Phase 16D–16I implementation, automated tests, UAT and route enablement

## 1. Purpose

This document fixes the architecture for:

- POM-only international air routing;
- domestic pre-carriage and on-forwarding;
- ordered journey and leg construction;
- charge-to-leg context;
- leg-aware ProductCode assignment;
- domestic-rate provenance and missing-BUY controls;
- multi-engine quote orchestration;
- granular SPOT integration;
- line, leg, journey and customer-output reconciliation.

It is a design document only. It does not alter pricing, ProductCodes, rates, GST, FX, margins, SPOT decisions or production behaviour.

## 2. Architecture decisions

1. **A deterministic planner enforces POM as the only PNG international air gateway.**
2. **Journey direction and ProductCode domain are separate concepts.**
   - the overall journey is `IMPORT` or `EXPORT`;
   - each leg determines whether its charge uses an `IMPORT`, `EXPORT` or `DOMESTIC` ProductCode.
3. **Every Phase 16 charge included in totals belongs to one explicit leg.**
4. **Raw-label normalization and ProductCode selection remain separate.**
   - aliases identify a canonical charge type;
   - context rules select the valid ProductCode.
5. **Existing import, export and domestic engines remain leaf calculators.**
   - a new orchestrator composes them;
   - child engines do not plan the journey.
6. **Typed contracts define business meaning independently of Django ORM.**
7. **Journey revisions and leg snapshots are persisted for audit, reopen and recalculation.**
8. **Domestic BUY coverage is mandatory independently of SELL coverage.**
9. **SPOT replacement is granular by leg and commercial identity.**
10. **Route automation policies fail closed and are independently controlled.**
11. **Totals reconcile at line, leg, journey and customer-output boundaries.**
12. **Historical quotes remain readable without guessed leg backfills.**
13. **A quote or SPOT envelope may have multiple journey revisions.**
    - parent links are foreign keys, not one-to-one links;
    - uniqueness is enforced by parent plus revision number.

## 3. Target flow

```text
Trusted quote/SPOT shipment context
        ↓
AirJourneyPlanner
        ↓
JourneyPlan + ordered JourneyLegs
        ↓
RouteAutomationPolicy check
        ↓
ChargeContextResolver
        ↓
Canonical charge type + leg-aware context
        ↓
LegAwareProductCodeResolver
        ↓
ProductCode assignment or blocker
        ↓
JourneyPricingOrchestrator
        ├─ ImportPricingEngine
        ├─ ExportPricingEngine
        ├─ DomesticPricingEngine
        └─ governed local/cartage path
        ↓
Granular SPOT merge
        ↓
JourneyReconciliationService
        ↓
Finalisation guard
        ↓
Customer output
```

## 4. Core contracts

Contracts should be Pydantic models or frozen dataclasses in a neutral contract/service module. ORM models persist snapshots but do not define the business contract by themselves.

### 4.1 Canonical enums

```text
JourneyDirection
- IMPORT
- EXPORT

JourneyPattern
- IMP_POM
- IMP_LAE
- IMP_HGU
- EXP_POM
- EXP_LAE
- EXP_HGU

LegRole
- INTERNATIONAL_IMPORT
- INTERNATIONAL_EXPORT
- DOMESTIC_ON_FORWARDING
- DOMESTIC_PRE_CARRIAGE
- FINAL_PICKUP
- FINAL_DELIVERY

TransportMode
- INTERNATIONAL_AIR
- DOMESTIC_AIR
- LOCAL_ROAD

CommercialPosition
- ORIGIN
- FREIGHT
- DESTINATION

ProductCodeDomain
- IMPORT
- EXPORT
- DOMESTIC

JourneyStatus
- PLANNED
- NEEDS_REVIEW
- PRICED
- FINALIZED
- SUPERSEDED
```

### 4.2 JourneyRequest

Required trusted inputs:

```text
origin_country
destination_country
customer_origin_code
customer_destination_code
service_domain
service_scope
quote_date
pieces
actual_weight_kg
volumetric_weight_kg
chargeable_weight_kg
commodity_code
pickup_requested
delivery_requested
```

Rules:

- countries and location codes are normalized before planning;
- supplier text cannot change the trusted route;
- missing or contradictory route evidence produces a blocker, not a partial plan.

### 4.3 JourneyPlan

```text
journey_id
revision
direction
pattern
gateway_code = POM
customer_origin_code
customer_destination_code
legs[]
route_policy_key
rule_version
input_fingerprint
status
blockers[]
```

`input_fingerprint` is generated from trusted route and service dimensions. It detects stale legs and stale charge assignments.

### 4.4 JourneyLeg

```text
leg_id
leg_key
sequence
role
transport_mode
origin_code
destination_code
product_code_domain
commercial_owner_branch
required
service_scope
chargeable_weight_kg
status
rate_coverage_status
blockers[]
```

`leg_key` is deterministic and readable, for example:

```text
01:INTERNATIONAL_IMPORT:SIN:POM
02:DOMESTIC_ON_FORWARDING:POM:LAE
```

### 4.5 ChargeContext

```text
journey_id
journey_revision
leg_id
leg_key
journey_direction
journey_pattern
leg_role
leg_sequence
product_code_domain
commercial_position
operational_location
transport_mode
canonical_charge_type
charge_family
calculation_basis
service_scope
currency
tax_treatment
effective_date
source_evidence
context_fingerprint
```

A ProductCode cannot be assigned until the mandatory fields for that charge family are complete.

### 4.6 ProductCodeResolutionResult

```text
status
- ASSIGNED
- NEEDS_CLARIFICATION
- NOT_FOUND
- CONTEXT_INCOMPLETE
- REJECTED

selected_product_code
candidate_product_codes[]
resolved_context
clarification_question
review_reason
rule_version
audit_evidence
```

Automatic assignment requires exactly one valid candidate after contextual filtering.

### 4.7 RateProvenance

```text
rate_side
- BUY
- SELL

source_type
- CUSTOMER_CONTRACT
- ROUTE_CONTRACT
- CARRIER_TARIFF
- INTERNAL_RATE_CARD
- SUPPLIER_SPOT
- MANUAL_SOURCE

source_model
source_record_id
source_reference
supplier_or_carrier
rate_owner
approval_status
approved_by
approved_at
valid_from
valid_until
currency
calculation_basis
minimum_charge
match_dimensions
evidence_reference
```

A required leg is incomplete unless its required BUY components have valid provenance or an explicit manual-sourcing blocker.

### 4.8 JourneyChargeLine

```text
line_id
journey_id
journey_revision
leg_id
leg_key
product_code
product_code_domain
component
commercial_position
description
cost_amount
sell_amount
currency
gst_amount
margin_amount
include_in_totals
rate_provenance
source_evidence
review_status
blockers[]
```

### 4.9 JourneyPricingResult

```text
journey
legs[]
lines[]
leg_totals[]
journey_totals
tax_breakdown
fx_breakdown
audit_metadata
blockers[]
is_complete
```

`is_complete` is false when a required BUY cost, leg, ProductCode, FX treatment, tax treatment or reconciliation check is unresolved.

## 5. Journey planning

### 5.1 AirJourneyPlanner

`AirJourneyPlanner` is a pure deterministic service. It does not query rates, ProductCodes or AI.

It produces these patterns:

```text
IMPORT to POM
Overseas → POM

IMPORT to LAE
Overseas → POM
POM → LAE

IMPORT to HGU
Overseas → POM
POM → HGU

EXPORT from POM
POM → Overseas

EXPORT from LAE
LAE → POM
POM → Overseas

EXPORT from HGU
HGU → POM
POM → Overseas
```

`EXP_HGU` may be planned for visibility but remains disabled by route policy until HGU→POM BUY and SELL readiness is verified.

### 5.2 Planner blockers

Stable codes:

```text
JOURNEY_COUNTRY_MISSING
JOURNEY_DIRECTION_UNSUPPORTED
JOURNEY_GATEWAY_INVALID
JOURNEY_PATTERN_UNSUPPORTED
JOURNEY_MULTI_STOP_UNSUPPORTED
ROUTE_AUTOMATION_DISABLED
ROUTE_RATE_GATE_UNMET
```

A planning blocker prevents automatic pricing. A reviewable draft may still be created to preserve commercial evidence.

## 6. Persistence design

### 6.1 ShipmentJourneyDB

Recommended location: `quotes` app.

```text
id UUID
quote nullable FK
spot_envelope nullable FK
revision integer
direction
pattern
gateway_code
customer_origin_code
customer_destination_code
route_policy_key
rule_version
input_fingerprint
status
blockers_json
supersedes nullable self-FK
created_at
created_by
finalized_at
```

Rules and constraints:

- at least one of `quote` or `spot_envelope` is present;
- a journey revision may link to both when an SPE becomes a quote;
- unique `(quote, revision)` when `quote` is not null;
- unique `(spot_envelope, revision)` when `spot_envelope` is not null;
- the current revision is selected explicitly by status/latest revision, never by one-to-one relationship;
- finalized revisions are immutable;
- a material route change creates a new revision and supersedes the old one;
- concurrent revision creation must lock the parent quote/SPE or otherwise serialize revision allocation.

### 6.2 ShipmentLegDB

```text
id UUID
journey FK
leg_key
sequence
role
transport_mode
origin_code
destination_code
product_code_domain
required
service_scope
chargeable_weight_kg
status
rate_coverage_status
blockers_json
```

Constraints:

- unique `(journey, sequence)`;
- unique `(journey, leg_key)`;
- sequence begins at 1 and is contiguous, validated by the planner/service;
- international import ends at POM;
- international export starts at POM;
- domestic on-forwarding starts at POM;
- domestic pre-carriage ends at POM.

### 6.3 Charge-line links

Add nullable `journey_leg` links to:

- standard `QuoteLine`;
- `SPEChargeLineDB`.

Historical records may remain null. For Phase 16-generated lines:

- a valid `journey_leg` is mandatory before totals inclusion;
- `charge_context_json` stores the complete context and fingerprint;
- ProductCode-resolution audit remains attached to the line or existing decision records.

No historical backfill may guess journey legs.

### 6.4 RouteAutomationPolicyDB

```text
route_pattern
enabled
disabled_reason
effective_from
effective_until
required_rate_gate_json
updated_by
updated_at
```

Rules:

- a missing policy means disabled;
- initial policies are seeded disabled;
- each route is enabled only after tests and route-specific UAT;
- `EXP_HGU` remains disabled until HGU→POM coverage is verified;
- changes are manager/admin controlled and audited.

## 7. ProductCode architecture

### 7.1 Separation of responsibilities

```text
Raw supplier label
        ↓
ChargeAlias
        ↓
CanonicalChargeType
        ↓
ChargeContextResolver
        ↓
ProductCodeContextRuleDB
        ↓
ProductCode
```

A Phase 16 raw alias must not directly decide the final ProductCode without validating the complete leg context.

### 7.2 ProductCodeContextRuleDB

```text
canonical_charge_type FK
product_code FK
product_code_domain
leg_role
commercial_position
transport_mode
operational_location optional
calculation_basis optional
service_scope optional
priority
is_active
review_status
source
created_by
updated_by
created_at
updated_at
```

The resolver filters by:

1. active and approved rule;
2. active ProductCode;
3. leg-derived domain;
4. canonical charge type;
5. leg role;
6. commercial position;
7. transport mode;
8. applicable location, basis and scope.

Results:

- one highest-specificity candidate → assign;
- multiple equal-specificity candidates → `NEEDS_CLARIFICATION` or configuration ambiguity;
- no candidate → `NOT_FOUND` and ProductCode request option;
- incomplete context → `CONTEXT_INCOMPLETE`;
- incompatible user selection → `REJECTED`.

### 7.3 ProductCode lifecycle

Phase 16D should add explicit lifecycle controls if the current catalogue lacks them:

```text
is_active
retired_at
replacement_product_code optional
```

A retired or inactive ProductCode is never selected for a new assignment.

### 7.4 Audit

Every automatic or assisted assignment records:

- journey and leg identifiers;
- complete resolved context;
- canonical charge type;
- candidate set;
- selected ProductCode;
- rule ID/version;
- source evidence;
- resolution status/reason;
- user and timestamp when assisted;
- previous and replacement values for overrides.

## 8. Pricing orchestration

### 8.1 JourneyPricingOrchestrator

The orchestrator receives a validated `JourneyPlan` and dispatches each leg:

- international import → existing `ImportPricingEngine` using overseas → POM;
- international export → existing `ExportPricingEngine` using POM → overseas;
- domestic pre-carriage/on-forwarding → existing `DomesticPricingEngine`;
- explicit local pickup/delivery → existing governed local/cartage path.

Each child-engine line is stamped with the leg ID/key before roll-up.

### 8.2 Child-engine boundaries

Child engines:

- do not insert or remove POM;
- do not infer journey pattern;
- do not select ProductCodes outside supplied leg context;
- do not declare whole-journey completeness;
- expose BUY and SELL coverage independently;
- preserve selected-rate metadata.

### 8.3 Missing BUY

A required domestic leg is blocked when:

- no valid BUY rate exists;
- BUY selection is ambiguous;
- BUY provenance is unapproved or expired;
- SELL exists but BUY does not.

The orchestrator emits `DOMESTIC_BUY_MISSING` even when a SELL line can be calculated.

### 8.4 Granular SPOT merge

Current bucket-level replacement must not be used for Phase 16.

A SPOT line matches/replaces a standard line only by compatible identity:

```text
journey_revision
leg_key
product_code
commercial_position
component
currency
```

Rules:

- only the exact overridden line is replaced;
- unrelated standard lines remain;
- a SPOT freight line does not erase documentation, security or handling;
- unresolved SPOT lines remain visible and cannot silently displace standard lines;
- duplicate identities trigger review.

## 9. Domestic-rate architecture

Reuse existing domestic rate tables and deterministic selectors. Do not build a second pricing engine.

Extend domestic rate rows, or a shared provenance mixin, with:

```text
source_type
source_reference
source_document_name
rate_owner
approval_status
approved_by
approved_at
evidence_notes
```

Apply initially to:

- `DomesticCOGS`;
- `DomesticSellRate`;
- domestic `Surcharge` records.

Selection keeps existing route/date/currency/counterparty logic and adds:

- approved-source filtering;
- precedence tier;
- service/customer specificity where available;
- equal-precedence ambiguity;
- provenance serialization into audit output.

No fallback from BUY to SELL, from expired to historical, or from missing contract to an inferred rate is permitted.

## 10. Recalculation and revisioning

When trusted route or service input changes:

1. generate a new input fingerprint;
2. lock the quote/SPE revision parent;
3. allocate the next revision number;
4. regenerate the journey;
5. compare old and new legs;
6. retain unchanged compatible legs;
7. supersede removed or changed legs;
8. exclude incompatible old lines from totals;
9. preserve their evidence and prior decisions;
10. rerun charge context and ProductCode resolution;
11. recalculate and reconcile totals;
12. finalize only when all blockers clear.

A destination change from LAE to HGU must never retain LAE domestic charges.

## 11. Totals and reconciliation

`JourneyReconciliationService` performs four gates.

### Gate 1 — Line integrity

- every included line has a valid leg;
- ProductCode domain matches the leg;
- required BUY lines exist;
- currency, tax and basis are resolvable.

### Gate 2 — Leg totals

```text
sum(line cost) = leg cost
sum(line sell) = leg sell
sum(line GST) = leg GST
sum(line margin) = leg margin
```

### Gate 3 — Journey totals

The sum of leg totals equals journey totals after governed FX and tax calculations.

### Gate 4 — Customer output

Customer-output grouping preserves reconciled sell and GST totals. Compatible lines may group at the output boundary but internal source lines remain unchanged.

Stable blockers:

```text
CHARGE_LEG_UNASSIGNED
PRODUCTCODE_DOMAIN_MISMATCH
DOMESTIC_BUY_MISSING
RATE_SELECTION_AMBIGUOUS
FX_REQUIRED
TAX_TREATMENT_UNRESOLVED
LEG_TOTAL_MISMATCH
JOURNEY_TOTAL_MISMATCH
CUSTOMER_OUTPUT_MISMATCH
```

These blockers are non-overridable at launch.

## 12. SPOT and Exception Workspace integration

### 12.1 Draft Quote read payload

Add:

```text
shipment_context.journey
journey.legs[]
suggested_charges[].journey_leg_id
suggested_charges[].journey_leg_key
suggested_charges[].leg_role
suggested_charges[].product_code_domain
suggested_charges[].charge_context
```

### 12.2 ProductCode selector

Replace overall-direction-only selection with server-authoritative context filtering across:

```text
leg
domain
canonical charge type
commercial position
mode
location
basis
```

### 12.3 Resolve actions

Mapping, classifying or adding a charge requires a valid leg. The operator chooses the business movement, not a ProductCode database ID.

Example:

```text
What does this FSC apply to?
- International air freight
- POM → LAE domestic on-forwarding
- LAE → POM domestic pre-carriage
- Local pickup/delivery
```

### 12.4 Finalisation

The existing finalisation workflow consumes Phase 16 blockers. No manager/admin override is introduced for gateway, required leg, missing BUY, ProductCode-domain or reconciliation failures.

## 13. API boundaries

Recommended contracts:

```text
POST /api/v4/journeys/plan/
- optional diagnostic/UAT endpoint

POST /api/v4/quote/calculate/
- accepts customer route
- returns canonical journey and leg-aware result

GET /api/v4/product-codes/
- legacy domain filter retained
- add context-aware filtering or a dedicated resolver endpoint

GET /api/v3/spot/envelopes/<id>/draft-quote/
- returns journey and leg context

POST /api/v3/spot/envelopes/<id>/draft-quote/resolve/
- validates decisions against the persisted journey revision
```

Public quote APIs remain customer-friendly. Internal/manager responses retain leg and provenance detail.

## 14. Security and governance

- Existing quote and SPOT RBAC remains authoritative.
- Journey records inherit organization, operating entity, branch, department and owner from the quote/SPE.
- Sales users cannot enable route automation or approve rate provenance.
- Route policies and ProductCode context rules are manager/admin governed.
- Client-supplied journey, leg and domain claims are always revalidated server-side.
- Every automatic assignment records architecture/rule version.

## 15. Migration and compatibility

### Stage 1 — Contracts and diagnostics

- add typed contracts and pure planner;
- compare planned journeys with current direct-lane behaviour;
- no pricing behaviour change.

### Stage 2 — Persistence foundation

- add journey and leg models;
- add nullable charge-line links and context snapshots;
- seed route policies disabled;
- no guessed historical backfill.

### Stage 3 — ProductCode context rules

- add context-rule model;
- migrate only reviewed mappings;
- audit overlap/ambiguity;
- retain legacy path outside Phase 16.

### Stage 4 — Orchestration

- compose existing engines behind feature flags;
- stamp lines with legs;
- implement missing-BUY blockers and granular SPOT merge.

### Stage 5 — Reconciliation and UI

- enforce totals gates;
- expose journey and clarification UI;
- execute route-specific UAT.

### Stage 6 — Controlled enablement

Enable separately:

```text
IMP_POM
EXP_POM
IMP_LAE
EXP_LAE
IMP_HGU
```

`EXP_HGU` remains disabled until HGU→POM rate readiness and route UAT pass.

## 16. Test architecture

### Unit tests

- country direction and gateway planner;
- pattern and leg generation;
- deterministic leg keys;
- parent/revision uniqueness and concurrent revision allocation;
- route-policy fail-closed behaviour;
- charge-context completeness;
- per-leg ProductCode domain;
- context-rule specificity and ambiguity;
- rate provenance and precedence;
- missing BUY despite available SELL;
- reconciliation arithmetic.

### Integration tests

- planner → context → ProductCode → engines → roll-up;
- SPOT resolution with leg validation;
- granular SPOT replacement;
- route change and journey revision;
- finalisation blockers;
- customer-output parity.

### Mandatory architecture scenarios

```text
ARCH-16C-001  Import journey contains IMPORT and DOMESTIC ProductCodes.
ARCH-16C-002  Export journey contains EXPORT and DOMESTIC ProductCodes.
ARCH-16C-003  Raw JSON direction cannot change ProductCode domain.
ARCH-16C-004  Missing route policy disables automation.
ARCH-16C-005  EXP_HGU remains disabled while HGU→POM gate is unmet.
ARCH-16C-006  SPOT freight override preserves unrelated standard charges.
ARCH-16C-007  LAE lines cannot survive a route change to HGU.
ARCH-16C-008  Customer output equals reconciled internal totals.
ARCH-16C-009  Multiple revisions can coexist for one quote/SPE without collision.
ARCH-16C-010  Concurrent recalculation cannot allocate duplicate revision numbers.
```

All `UAT-16A-001` through `UAT-16A-020` remain mandatory.

## 17. Delivery boundaries

### Phase 16D

- typed journey and ChargeContext contracts;
- ProductCode context-rule persistence;
- leg-aware ProductCode resolver;
- resolver tests and diagnostics;
- no multi-leg quote roll-up until resolver gates pass.

### Phase 16E

- journey planner;
- journey/leg persistence;
- multi-leg orchestration using existing engines;
- route policies seeded disabled.

### Phase 16F

- domestic-rate provenance and precedence;
- missing-BUY controls;
- leg/journey totals reconciliation;
- granular SPOT merge.

### Phase 16G

- journey presentation;
- business clarification workflow;
- manual sourcing and ProductCode exception UX.

### Phase 16H–16I

- regression hardening;
- staging UAT;
- controlled route enablement.

## 18. Phase 16C exit gate

```text
JOURNEY_CONTRACT_DEFINED = YES
JOURNEY_REVISION_MODEL_DEFINED = YES
LEG_PERSISTENCE_DEFINED = YES
POM_GATEWAY_ENFORCEMENT_DEFINED = YES
PER_LEG_PRODUCTCODE_DOMAIN_DEFINED = YES
PRODUCTCODE_CONTEXT_RULES_DEFINED = YES
MULTI_LEG_ORCHESTRATION_DEFINED = YES
DOMESTIC_RATE_PROVENANCE_DEFINED = YES
MISSING_BUY_BLOCKER_DEFINED = YES
GRANULAR_SPOT_MERGE_DEFINED = YES
TOTALS_RECONCILIATION_DEFINED = YES
ROUTE_FEATURE_FLAGS_DEFINED = YES
IMPLEMENTATION_SEQUENCE_DEFINED = YES
```

After this architecture is reviewed and approved:

```text
READY_FOR_PHASE_16D_IMPLEMENTATION = YES
```

No implementation may weaken the Phase 16A commercial guardrails.