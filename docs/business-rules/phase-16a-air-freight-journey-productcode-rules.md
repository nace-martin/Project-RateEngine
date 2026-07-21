# RateEngine Phase 16A - International Air Freight Journey, Domestic Leg and ProductCode Business Rules

**Document ID:** RE-BR-16A-AIR-001  
**Version:** 1.0  
**Effective date:** 21 July 2026  
**Status:** Authoritative working baseline  
**Business owner:** Commercial Freight Manager  
**Applies to:** RateEngine international air-freight quoting, ProductCode assignment, domestic pre-carriage, domestic on-forwarding, design, development, automated tests and UAT  
**Canonical repository location:** `docs/business-rules/phase-16a-air-freight-journey-productcode-rules.md`

---

## 1. Authority and change control

This document is the source of truth for Phase 16 design and implementation. Code, ProductCode rules, rate configuration, tests, UAT scripts and user guidance must conform to it.

Where existing application behaviour conflicts with this document, the conflict must be treated as a defect or an explicitly approved change request. The application must not silently preserve contradictory legacy behaviour.

Changes to these rules require:

1. a documented business decision;
2. a version update to this document;
3. impact review for ProductCodes, rates, calculations, UI, audit, regression tests and UAT;
4. implementation only after the revised rule is accepted.

This document supersedes informal notes and chat decisions concerning the Phase 16 air-freight journey model.

---

## 2. Purpose and target outcome

RateEngine must automatically:

1. determine whether a shipment is an import or export from trusted route data;
2. construct the correct ordered shipment journey;
3. identify the leg and commercial context of every charge;
4. select the correct active ProductCode when one exact valid match exists;
5. source domestic rates from approved sources;
6. expose missing, conflicting or ambiguous information for manual review;
7. preserve the underlying leg, charge, rate and evidence detail while producing one coherent customer quote.

The user must not be asked to choose or type an internal ProductCode ID. The system must ask only the business question needed to resolve missing context.

---

## 3. Non-negotiable commercial principles

| Rule ID | Business rule |
|---|---|
| `BR-GOV-001` | POM is the only PNG international gateway for international air-freight shipments in the Phase 16 model. |
| `BR-GOV-002` | Every charge included in a quote must be attached to one identifiable shipment leg and commercial position. |
| `BR-GOV-003` | ProductCode assignment must be deterministic, context-compatible and auditable. |
| `BR-GOV-004` | AI or document intake may suggest the meaning of supplier text, but it must not invent, bypass or force a ProductCode. |
| `BR-GOV-005` | Users must never enter or select raw internal ProductCode database IDs. |
| `BR-GOV-006` | Ambiguous, unsupported or incomplete context must fail visibly into manual review. It must not be guessed. |
| `BR-GOV-007` | Missing BUY rates or required charge components must remain visible for manual sourcing. A local SELL rate must never be substituted as a hidden cost or completeness fallback. |
| `BR-GOV-008` | Quote totals are sacred. Customer totals must be derived from the actual reviewed charge lines and legs included in totals. |
| `BR-GOV-009` | Automatic and user-assisted decisions must retain source evidence, rule version, outcome, operator and timestamp. |
| `BR-GOV-010` | No commercially relevant charge may be silently invented, discarded or moved to another leg. |
| `BR-GOV-011` | Wrong-domain ProductCodes, unsupported gateway routes and unresolved required legs are hard failures, not warnings. |
| `BR-GOV-012` | The initial release must be feature-flagged by supported route group so that unsafe route groups can be disabled independently. |

---

## 4. Definitions

### 4.1 Gateway

The PNG airport through which the international air-freight leg enters or leaves Papua New Guinea. For this release, the gateway is always Port Moresby (`POM`).

### 4.2 International leg

The air-freight movement between POM and an overseas airport.

### 4.3 Domestic pre-carriage

A domestic movement from a PNG regional origin to POM before an export international leg.

Examples:

- Lae (`LAE`) to POM before POM to Brisbane;
- Mount Hagen (`HGU`) to POM before POM to Singapore.

Domestic pre-carriage is not the international origin leg. It is a separate domestic leg feeding the POM gateway.

### 4.4 Domestic on-forwarding

A domestic movement from POM to a PNG regional destination after an import international leg.

Examples:

- POM to LAE after Singapore to POM;
- POM to HGU after Brisbane to POM.

Domestic on-forwarding is not part of the international freight leg. It is a separate domestic leg beginning after arrival at the POM gateway.

### 4.5 Final local delivery

A local pickup or delivery movement between an airport, branch, warehouse or terminal and the customer's specified address. It is separate from domestic pre-carriage and on-forwarding.

Examples:

- POM airport to a customer address in Port Moresby;
- LAE airport to a customer address in Lae.

A regional destination does not automatically mean final local delivery is included. The service scope must state it explicitly.

### 4.6 Charge context

The complete set of business dimensions needed to understand what a charge applies to and which ProductCode may be used.

### 4.7 ProductCode domain

The trusted import or export domain derived from the shipment's origin and destination countries. It is never taken from user-entered JSON, supplier wording or an editable frontend field.

### 4.8 Manual review

A visible unresolved state requiring a user or authorised reviewer to provide missing business context, source a rate, select an approved business option or request a ProductCode. Manual review is not permission to guess.

---

## 5. Direction and gateway rules

### 5.1 Direction derivation

| Rule ID | Route condition | Direction result |
|---|---|---|
| `BR-DIR-001` | Origin country is outside PNG and destination country is PNG | `IMPORT` |
| `BR-DIR-002` | Origin country is PNG and destination country is outside PNG | `EXPORT` |
| `BR-DIR-003` | Origin and destination countries are both PNG | `DOMESTIC_ONLY` and outside the Phase 16 international-air automation scope |
| `BR-DIR-004` | Neither origin nor destination country is PNG | `THIRD_COUNTRY` and unsupported |
| `BR-DIR-005` | Country data is missing, invalid or contradictory | Direction unresolved; block ProductCode assignment and journey finalisation |

### 5.2 POM-only gateway enforcement

| Rule ID | Business rule |
|---|---|
| `BR-GW-001` | Every supported international import air journey must contain an international leg ending at POM. |
| `BR-GW-002` | Every supported international export air journey must contain an international leg starting at POM. |
| `BR-GW-003` | LAE, HGU and all other PNG locations are domestic origins or destinations only in an international air journey. |
| `BR-GW-004` | The system must not treat LAE, HGU or another PNG location as an international air gateway. |
| `BR-GW-005` | A user-entered direct international route to or from a regional PNG location must be reconstructed through POM when the route is otherwise supported. If reconstruction is not possible, the route must be blocked. |
| `BR-GW-006` | A supplier document or parsed route must not override the POM gateway rule. |

---

## 6. Supported journey patterns

### 6.1 Import patterns

| Pattern ID | Customer route | Required ordered journey | Launch status |
|---|---|---|---|
| `IMP-POM` | Overseas airport to POM | 1. International air: Overseas -> POM | Supported |
| `IMP-LAE` | Overseas airport to LAE | 1. International air: Overseas -> POM; 2. Domestic on-forwarding: POM -> LAE | Supported |
| `IMP-HGU` | Overseas airport to HGU | 1. International air: Overseas -> POM; 2. Domestic on-forwarding: POM -> HGU | Supported |

Rules:

- `BR-JNY-IMP-001`: An import ending at POM has no regional domestic on-forwarding leg unless another domestic destination is explicitly selected.
- `BR-JNY-IMP-002`: An import ending at LAE must include POM-to-LAE domestic on-forwarding.
- `BR-JNY-IMP-003`: An import ending at HGU must include POM-to-HGU domestic on-forwarding.
- `BR-JNY-IMP-004`: POM import arrival, customs, breakdown and international destination handling charges remain attached to the international import destination context.
- `BR-JNY-IMP-005`: Charges specifically incurred to transfer, book, handle or carry cargo from POM to a regional destination belong to the domestic on-forwarding leg.
- `BR-JNY-IMP-006`: Final delivery from the regional airport is an optional separate leg and must not be inferred merely because the final PNG city is LAE or HGU.

### 6.2 Export patterns

| Pattern ID | Customer route | Required ordered journey | Launch status |
|---|---|---|---|
| `EXP-POM` | POM to overseas airport | 1. International air: POM -> Overseas | Supported |
| `EXP-LAE` | LAE to overseas airport | 1. Domestic pre-carriage: LAE -> POM; 2. International air: POM -> Overseas | Supported |
| `EXP-HGU` | HGU to overseas airport | 1. Domestic pre-carriage: HGU -> POM; 2. International air: POM -> Overseas | Supported |

Rules:

- `BR-JNY-EXP-001`: An export beginning at POM has no regional domestic pre-carriage leg unless another PNG origin is explicitly selected.
- `BR-JNY-EXP-002`: An export beginning at LAE must include LAE-to-POM domestic pre-carriage.
- `BR-JNY-EXP-003`: An export beginning at HGU must include HGU-to-POM domestic pre-carriage.
- `BR-JNY-EXP-004`: Regional pickup, regional terminal handling and domestic freight to POM belong to the domestic pre-carriage leg.
- `BR-JNY-EXP-005`: Export documentation, security, AWB, terminal and airline-origin charges at POM belong to the international export origin context.
- `BR-JNY-EXP-006`: Overseas destination charges, when quoted, belong to the export destination context and are not confused with PNG domestic legs.

### 6.3 Invalid or unsupported patterns

| Rule ID | Route or condition | Required behaviour |
|---|---|---|
| `BR-JNY-INV-001` | Overseas -> LAE shown as a direct international leg | Reconstruct as Overseas -> POM -> LAE or block if the domestic leg is unsupported/missing |
| `BR-JNY-INV-002` | LAE -> Overseas shown as a direct international leg | Reconstruct as LAE -> POM -> Overseas or block if the domestic leg is unsupported/missing |
| `BR-JNY-INV-003` | International air route uses any PNG gateway other than POM | Hard block |
| `BR-JNY-INV-004` | Domestic-only PNG route | Route to existing/manual domestic workflow; do not apply Phase 16 international rules |
| `BR-JNY-INV-005` | Third-country route with no PNG origin or destination | Unsupported |
| `BR-JNY-INV-006` | More than one regional domestic stop | Unsupported at launch; manual SPOT review |

---

## 7. Journey and leg construction rules

Each journey must be an ordered list of explicit legs. A leg must contain at least:

- sequence number;
- leg type;
- transport mode;
- origin and destination location;
- operating entity and responsible branch where applicable;
- supplier/carrier or manual-source status;
- rate source and validity;
- chargeable weight or applicable rating quantity;
- charges and ProductCodes;
- currency, tax treatment and totals inclusion;
- source evidence;
- review status.

| Rule ID | Business rule |
|---|---|
| `BR-LEG-001` | A charge cannot be included in totals without a leg assignment. |
| `BR-LEG-002` | Leg sequence must reflect the physical journey order. |
| `BR-LEG-003` | The international and domestic legs must retain separate calculations even when presented as one customer quote. |
| `BR-LEG-004` | The system must not merge international freight, POM gateway handling and domestic linehaul into one hidden undifferentiated cost. |
| `BR-LEG-005` | Optional local pickup or delivery must be explicitly selected or evidenced. |
| `BR-LEG-006` | Removing or changing a journey location must trigger leg regeneration and charge-context revalidation. |
| `BR-LEG-007` | Recalculation must not retain charges that are incompatible with the regenerated journey. Those charges must be reclassified or returned to review. |

---

## 8. Charge-context model

### 8.1 Required dimensions

| Dimension | Allowed or typical values | Use |
|---|---|---|
| Service domain | Air Freight | Mandatory selection and validation |
| Shipment direction | Import, Export | Mandatory; derived from trusted countries |
| Journey pattern | IMP-POM, IMP-LAE, IMP-HGU, EXP-POM, EXP-LAE, EXP-HGU | Mandatory |
| Leg type | International, Domestic pre-carriage, Domestic on-forwarding, Final local pickup/delivery | Mandatory |
| Leg sequence | 1, 2, 3... | Mandatory |
| Commercial position | Origin, Freight, Destination | Mandatory where ProductCode catalogue distinguishes it |
| Operational location | POM, LAE, HGU, overseas origin/destination | Mandatory where location-sensitive |
| Transport mode | International air, Domestic air, Local road/cartage | Mandatory |
| Charge family | Freight, Fuel, Handling, Documentation, AWB, Security, Storage, Customs, Screening, Cartage, Delivery, Other governed family | Mandatory |
| Calculation basis | Flat, per kg, minimum-or-per-kg, percentage, per shipment, per AWB/document, per piece, per day | Mandatory when relevant |
| Rate source | Contract, tariff, approved rate card, supplier spot, manual source | Rating and audit |
| Currency | Source currency | Rating and validation, not a substitute for context |
| Tax treatment | Existing company GST/tax policy | Calculation and validation |
| Effective date | Quote/rate validity date | Rate and ProductCode validity |
| Evidence | Source text, table row, rate reference, user decision | Audit and review |
| Include in totals | Yes/No with reason | Quote integrity |

### 8.2 Commercial-position rules

| Direction and leg | Commercial position examples |
|---|---|
| Import international leg at overseas departure | Import origin |
| Import international air linehaul | Import freight |
| Import arrival/customs/handling at POM | Import destination |
| Import POM-to-LAE/HGU domestic linehaul | Import domestic on-forwarding freight |
| Import transfer handling at POM specifically for onward domestic movement | Import domestic on-forwarding origin |
| Import handling/delivery at LAE/HGU after domestic arrival | Import domestic on-forwarding destination or final delivery, depending on purpose |
| Export regional-to-POM domestic linehaul | Export domestic pre-carriage freight |
| Export regional handling specifically for movement to POM | Export domestic pre-carriage origin |
| Export processing at POM before international departure | Export origin |
| Export international air linehaul | Export freight |
| Export charges at overseas arrival | Export destination |

### 8.3 Ambiguous labels

A label alone is not sufficient when it can apply to multiple contexts.

Examples requiring context resolution include:

- `FSC`;
- `Handling`;
- `Terminal Fee`;
- `Documentation`;
- `Delivery`;
- `Airport Charge`;
- `Transfer Fee`.

For `FSC`, the system must distinguish, at minimum:

- international airline fuel surcharge;
- domestic air fuel surcharge;
- pickup/cartage fuel surcharge;
- domestic on-forwarding fuel surcharge;
- final delivery fuel surcharge.

The system must ask a business clarification such as "What movement does this fuel surcharge apply to?" It must not ask the user to choose a ProductCode ID.

---

## 9. ProductCode assignment hierarchy

### 9.1 Resolver sequence

ProductCode selection must follow this sequence. Later steps may narrow a candidate set but must not contradict earlier trusted context.

1. **Validate route countries and derive direction.**
2. **Enforce the POM gateway and construct the journey.**
3. **Attach the charge to a specific leg.**
4. **Determine commercial position within that leg.**
5. **Normalise the charge family from governed aliases and evidence.**
6. **Apply transport mode and operational location.**
7. **Apply calculation basis or document type where the ProductCode catalogue distinguishes it.**
8. **Filter to active, effective and scope-compatible ProductCodes.**
9. **Assign only when one exact valid ProductCode remains.**

### 9.2 Precedence and trust

| Rule ID | Business rule |
|---|---|
| `BR-PC-001` | Trusted origin and destination countries outrank parsed or user-supplied direction labels. |
| `BR-PC-002` | Route-derived import/export domain cannot be overridden by frontend JSON, supplier terminology or a previous mapping. |
| `BR-PC-003` | Journey leg and commercial position outrank generic charge aliases. |
| `BR-PC-004` | An accepted alias or prior mapping may be reused only when its stored context remains compatible with the current route, leg, mode and position. |
| `BR-PC-005` | Inactive, expired, wrong-domain or wrong-scope ProductCodes are not candidates. |
| `BR-PC-006` | A generic ProductCode must not be used merely because a specific code is missing. |
| `BR-PC-007` | The ProductCode ID is an implementation detail. The user sees the business classification and human-readable ProductCode code/name. |
| `BR-PC-008` | Any override must preserve the original system classification, the replacement, reason, user and timestamp. |

### 9.3 Resolver outcomes

| Outcome | Required behaviour |
|---|---|
| One exact valid match | Assign automatically and record the rule version and context |
| More than one valid match | Ask the minimum business clarification needed; re-run the resolver after the answer |
| No valid match | Keep unresolved; offer the governed ProductCode request workflow |
| Incomplete shipment context | Block assignment and identify the missing route/leg information |
| Candidate conflicts with route domain or leg | Reject candidate; return to manual review |
| Pending ProductCode request | Keep charge visible and unresolved under the existing finalisation policy |

---

## 10. Domestic rate sources and precedence

### 10.1 Approved source types

Domestic pre-carriage and on-forwarding rates may come only from:

1. an active customer-specific contracted rate approved for the exact route and service;
2. an active carrier or supplier contract/tariff;
3. an approved EFM domestic route rate card;
4. a current supplier spot quotation attached to the quote evidence;
5. manual sourcing recorded against the quote when no approved configured rate exists.

### 10.2 Selection hierarchy

The most specific valid rate wins, subject to all of the following matching:

- operating entity;
- origin and destination;
- direction/leg type;
- transport mode and service level;
- commodity or special-handling constraints;
- weight/quantity band and minimum;
- customer scope where applicable;
- effective date and validity;
- currency and tax treatment.

If two equally specific active rates conflict, the system must not choose the cheapest, latest or highest-margin rate automatically. It must send the conflict to manual review.

### 10.3 Rating safeguards

| Rule ID | Business rule |
|---|---|
| `BR-RATE-001` | A domestic leg cannot be treated as complete without an applicable BUY cost or a recorded manual-source requirement. |
| `BR-RATE-002` | An existing local SELL rate must never be used as a hidden substitute for a missing BUY cost. |
| `BR-RATE-003` | Sell pricing must be calculated from the approved cost and existing margin/pricing rules, unless a governed customer sell tariff explicitly applies. |
| `BR-RATE-004` | Expired rates are invalid unless an authorised override policy explicitly permits use and records the reason. No such automatic override is included at launch. |
| `BR-RATE-005` | Minimum charges, chargeable weight, fuel, handling and other domestic components must remain individually reviewable. |
| `BR-RATE-006` | The source currency must be preserved. FX conversion must follow the existing RateEngine/company policy. |
| `BR-RATE-007` | GST and tax treatment must follow existing company policy and remain visible at charge level. |
| `BR-RATE-008` | A spot rate must retain supplier, date, validity and source evidence. |

---

## 11. Manual-review conditions

### 11.1 Hard blockers

The following conditions block automatic completion and finalisation:

| Rule ID | Condition | Required action |
|---|---|---|
| `BR-MR-001` | Missing or invalid origin/destination country | Correct shipment context |
| `BR-MR-002` | International air route does not pass through POM | Reconstruct through POM or reject as unsupported |
| `BR-MR-003` | Required domestic pre-carriage/on-forwarding leg is missing | Add/regenerate the leg |
| `BR-MR-004` | Charge has no leg assignment | Classify the charge to a leg |
| `BR-MR-005` | ProductCode candidate conflicts with direction, leg, mode or location | Select a compatible business context or request a ProductCode |
| `BR-MR-006` | Multiple exact ProductCode candidates remain | Answer business clarification |
| `BR-MR-007` | No ProductCode exists for a required charge | Use ProductCode request workflow |
| `BR-MR-008` | Required domestic BUY rate is missing | Source and record an approved rate |
| `BR-MR-009` | Two active domestic rates conflict at equal precedence | Authorised user chooses and records reason |
| `BR-MR-010` | Rate is expired or outside route/service/weight scope | Obtain a valid rate |
| `BR-MR-011` | Calculation basis, minimum or percentage base is ambiguous | Resolve commercial basis |
| `BR-MR-012` | Required FX rate/currency handling is missing or contradictory | Resolve currency treatment |
| `BR-MR-013` | GST/tax treatment cannot be determined under existing policy | Authorised review |
| `BR-MR-014` | Reviewed totals do not reconcile with leg and charge-line totals | Correct calculation before finalisation |
| `BR-MR-015` | Customer output differs from reviewed totals or omits a required leg/charge | Block publication and correct output |
| `BR-MR-016` | Route/location/mode is outside launch scope | Use manual SPOT workflow or wait for later scope |

### 11.2 Review without silent completion

The following may allow the quote draft to remain open but must stay visibly unresolved:

- optional final local delivery not yet priced;
- supplier spot validity awaiting confirmation;
- special cargo handling awaiting supplier response;
- pending ProductCode creation request;
- non-mandatory commercial term requiring user acknowledgement;
- evidence quality warning where the commercial value has not been silently assumed.

Whether a draft can be finalised with any of these items is governed by the existing finalisation policy. Phase 16 does not weaken that policy.

### 11.3 Override policy

At launch:

- there is no override for a non-POM international gateway;
- there is no override for a missing required leg;
- there is no override for a totals mismatch;
- there is no override that permits a wrong-domain ProductCode;
- there is no override that silently supplies a missing BUY cost.

Any future manager override must be separately designed, permissioned and audited.

---

## 12. Initial launch scope

### 12.1 Included

| Scope item | Launch baseline |
|---|---|
| Service domain | International Air Freight |
| International gateway | POM only |
| PNG locations | POM, LAE and HGU |
| Import patterns | IMP-POM, IMP-LAE, IMP-HGU |
| Export patterns | EXP-POM, EXP-LAE, EXP-HGU |
| Domestic regional mode | Domestic air pre-carriage/on-forwarding between POM and LAE/HGU |
| ProductCode behaviour | Automatic assignment only for one exact valid context-compatible match |
| Rate behaviour | Approved configured rate, valid supplier spot rate or visible manual sourcing |
| Quote output | One customer quote with preserved leg-level calculation and evidence |
| Rollout | Route-group feature flags and controlled UAT |

### 12.2 Explicit exclusions at launch

The following are outside automated Phase 16 launch scope and must remain manual, SPOT or separately governed:

1. international air gateways in PNG other than POM;
2. PNG regional origins or destinations other than POM, LAE and HGU;
3. domestic-only shipments;
4. sea freight, coastal shipping and inter-island sea legs;
5. intercity road linehaul as a substitute for the defined domestic air leg;
6. multi-stop domestic journeys or more than one regional transfer;
7. third-country movements with no PNG origin or destination;
8. automated local pickup/final-delivery pricing where no approved existing rate source is configured;
9. automatic pricing of dangerous goods, live animals, perishables, oversized or other special cargo surcharges when an exact governed rate is unavailable;
10. automatic customs-only, brokerage-only or clearance-only journey construction;
11. automatic use of inferred supplier rates, stale quotes, emails without validity, or historical SELL values;
12. autonomous ProductCode creation or approval;
13. autonomous overrides of tax, FX, margin, gateway, totals or missing-rate controls.

Excluded shipments may still be quoted through the existing controlled manual/SPOT process. Exclusion means "not automatically completed," not "commercial evidence may be discarded."

---

## 13. Customer quote and totals rules

| Rule ID | Business rule |
|---|---|
| `BR-TOT-001` | The customer may receive one quote, but the system must retain every underlying journey leg and reviewed charge line. |
| `BR-TOT-002` | International cost, POM gateway charges, domestic pre-carriage/on-forwarding, optional delivery, tax and margin must roll up from included charge lines only. |
| `BR-TOT-003` | Informational, ignored or excluded lines must not enter totals and must retain an explicit reason. |
| `BR-TOT-004` | Compatible customer-facing lines may be grouped by ProductCode only at output boundaries; internal source lines and audit evidence remain intact. |
| `BR-TOT-005` | Lines with different ProductCodes, currencies, tax codes or incompatible commercial components must not be grouped. |
| `BR-TOT-006` | Missing domestic components remain visible and must not be concealed by a complete-looking customer total. |
| `BR-TOT-007` | Reopening or recalculating a quote must regenerate affected legs and totals without losing recorded evidence or decisions. |

---

## 14. Audit and evidence requirements

Every automatic ProductCode or rate decision must retain:

- shipment and leg identifiers;
- resolved direction and journey pattern;
- charge-context dimensions;
- source label/text and document location where available;
- candidate ProductCodes considered;
- selected ProductCode and human-readable code/name;
- resolver/rule version;
- rate source, validity and supplier;
- automatic/manual outcome;
- clarification or override reason;
- operator and timestamp;
- before/after values when a decision changes;
- totals inclusion decision.

Ignored means deliberately excluded with evidence. It never means disappeared.

---

## 15. Canonical UAT scenarios

These scenarios are mandatory and must be traceable to automated tests and UAT evidence.

| Scenario ID | Input | Expected result |
|---|---|---|
| `UAT-16A-001` | BNE -> POM | Import; one international leg; import origin/freight/destination contexts |
| `UAT-16A-002` | SIN -> LAE | Reconstructed as SIN -> POM -> LAE; international plus domestic on-forwarding |
| `UAT-16A-003` | BNE -> HGU | Reconstructed as BNE -> POM -> HGU; international plus domestic on-forwarding |
| `UAT-16A-004` | POM -> BNE | Export; one international leg; export origin/freight/destination contexts |
| `UAT-16A-005` | LAE -> SIN | Reconstructed as LAE -> POM -> SIN; domestic pre-carriage plus international |
| `UAT-16A-006` | HGU -> BNE | Reconstructed as HGU -> POM -> BNE; domestic pre-carriage plus international |
| `UAT-16A-007` | Supplier text says direct SIN -> LAE international | POM inserted; direct LAE international gateway rejected |
| `UAT-16A-008` | Required POM -> LAE rate missing | Visible manual-sourcing blocker; no SELL substitution |
| `UAT-16A-009` | `FSC` without leg context | Business clarification requested; no ProductCode guessed |
| `UAT-16A-010` | One exact compatible ProductCode | Automatically assigned and audited |
| `UAT-16A-011` | Two compatible ProductCodes | Manual business clarification required |
| `UAT-16A-012` | No ProductCode | Unresolved charge and ProductCode request option |
| `UAT-16A-013` | Import route offered export-domain ProductCode | Candidate rejected |
| `UAT-16A-014` | Equal-precedence conflicting domestic rates | Manual rate decision required |
| `UAT-16A-015` | Mixed currencies with valid FX | Correct source-currency preservation, conversion and disclosure |
| `UAT-16A-016` | Mixed currencies without valid FX | Finalisation blocked |
| `UAT-16A-017` | Charge not attached to a leg | Finalisation blocked |
| `UAT-16A-018` | Customer output total differs from reviewed charge total | Publication blocked |
| `UAT-16A-019` | Reopen LAE import and change destination to HGU | POM-to-LAE leg/charges removed or returned to review; POM-to-HGU regenerated |
| `UAT-16A-020` | Special cargo with no exact governed domestic surcharge | Route built, surcharge remains manual SPOT review |

---

## 16. Phase 16A exit criteria

Phase 16A is complete when:

1. this document is accepted as the governing baseline;
2. the ProductCode catalogue can be assessed against the context dimensions in this document;
3. domestic rate owners can identify the source and validity of POM-LAE and POM-HGU rates in both directions;
4. every Phase 16B requirement can reference one or more rule IDs from this document;
5. every Phase 16 test and UAT case can trace back to a rule ID;
6. no implementation team is required to invent a gateway, journey, leg, ProductCode or missing-rate rule.

---

## 17. Implementation interpretation rule

When a case is not explicitly covered:

1. do not infer a new commercial rule from code, labels or historical data;
2. preserve the evidence;
3. mark the item unsupported or unresolved;
4. obtain a business decision;
5. update this document before automating the new case.

That is deliberate. RateEngine should be fast, but it must not become confidently wrong.
