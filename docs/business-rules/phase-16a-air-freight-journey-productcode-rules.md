# RateEngine Phase 16A — International Air Freight Journey, Domestic Leg and ProductCode Business Rules

**Document ID:** RE-BR-16A-AIR-001  
**Version:** 1.1  
**Effective date:** 21 July 2026  
**Status:** Authoritative business-rules baseline  
**Business owner:** Commercial Freight Manager  
**Canonical location:** `docs/business-rules/phase-16a-air-freight-journey-productcode-rules.md`

## 1. Authority

This document is the source of truth for Phase 16 architecture, implementation, ProductCode rules, domestic rates, tests and UAT. Conflicting legacy behaviour is a defect unless a later approved version explicitly changes the rule.

Changes require a documented business decision, version update, impact assessment and corresponding test/UAT changes.

## 2. Non-negotiable principles

| Rule ID | Rule |
|---|---|
| `BR-GOV-001` | POM is the only PNG international air gateway. |
| `BR-GOV-002` | Every included charge must be assigned to one explicit journey leg and commercial position. |
| `BR-GOV-003` | ProductCode assignment is deterministic, context-compatible and auditable. |
| `BR-GOV-004` | AI may interpret evidence but must not invent, approve or force ProductCodes. |
| `BR-GOV-005` | Users never type or select raw ProductCode database IDs. |
| `BR-GOV-006` | Ambiguous, unsupported or incomplete context fails visibly into review. |
| `BR-GOV-007` | Missing BUY costs remain visible. SELL must never be substituted as hidden cost or completeness evidence. |
| `BR-GOV-008` | Quote totals are derived only from reviewed, included leg charge lines. |
| `BR-GOV-009` | Automatic and assisted decisions retain evidence, rule version, result, user and timestamp. |
| `BR-GOV-010` | Commercial data is never silently invented, discarded or moved between legs. |
| `BR-GOV-011` | Wrong-domain ProductCodes, non-POM gateways and unresolved required legs are hard failures. |
| `BR-GOV-012` | Automation is controlled by route-group feature flags. |

## 3. Definitions

- **Gateway:** POM, the only PNG airport used by an international air leg.
- **International leg:** Overseas airport to POM for imports, or POM to overseas airport for exports.
- **Domestic pre-carriage:** Regional PNG airport to POM before export.
- **Domestic on-forwarding:** POM to regional PNG airport after import.
- **Final local pickup/delivery:** Separate local cartage between airport/terminal and an address. It is never inferred merely from the city.
- **Journey direction:** Overall `IMPORT` or `EXPORT`, derived from trusted countries.
- **ProductCode domain:** Derived from the assigned leg, not once for the whole journey:
  - international import and POM import-gateway charges → `IMPORT`;
  - international export and POM export-gateway charges → `EXPORT`;
  - domestic pre-carriage/on-forwarding charges → `DOMESTIC`;
  - existing import/export local ProductCodes may remain applicable where pickup/delivery is part of the international service rather than a separately modelled domestic transport leg.
- **Manual review:** A visible unresolved state. It is not permission to guess.

## 4. Direction and gateway

| Rule ID | Condition | Result |
|---|---|---|
| `BR-DIR-001` | Non-PNG origin, PNG destination | `IMPORT` |
| `BR-DIR-002` | PNG origin, non-PNG destination | `EXPORT` |
| `BR-DIR-003` | PNG origin and destination | `DOMESTIC_ONLY`; outside Phase 16 international automation |
| `BR-DIR-004` | Neither endpoint is PNG | `THIRD_COUNTRY`; unsupported |
| `BR-DIR-005` | Missing, invalid or contradictory countries | Block journey and ProductCode resolution |

| Rule ID | Gateway rule |
|---|---|
| `BR-GW-001` | Every import international leg ends at POM. |
| `BR-GW-002` | Every export international leg starts at POM. |
| `BR-GW-003` | LAE, HGU and other PNG locations are domestic endpoints within an international journey. |
| `BR-GW-004` | No regional PNG location may be treated as an international gateway. |
| `BR-GW-005` | A direct international regional route is reconstructed through POM when supported; otherwise blocked. |
| `BR-GW-006` | Supplier text, parsed routes and editable fields cannot override the gateway rule. |

## 5. Journey patterns

### Imports

| Pattern | Customer route | Ordered legs | Launch status |
|---|---|---|---|
| `IMP-POM` | Overseas → POM | International: Overseas → POM | Enabled after implementation/UAT |
| `IMP-LAE` | Overseas → LAE | International: Overseas → POM; On-forwarding: POM → LAE | Enabled after implementation/UAT |
| `IMP-HGU` | Overseas → HGU | International: Overseas → POM; On-forwarding: POM → HGU | Enabled after implementation/UAT |

- `BR-JNY-IMP-001`: POM imports contain no regional onward leg unless explicitly selected.
- `BR-JNY-IMP-002`: LAE imports include POM → LAE.
- `BR-JNY-IMP-003`: HGU imports include POM → HGU.
- `BR-JNY-IMP-004`: POM import arrival, customs, breakdown and gateway handling remain in the international import destination context.
- `BR-JNY-IMP-005`: Charges incurred specifically for onward transfer/book/handling/carriage belong to the domestic onward leg.
- `BR-JNY-IMP-006`: Regional final delivery is optional and separate.

### Exports

| Pattern | Customer route | Ordered legs | Launch status |
|---|---|---|---|
| `EXP-POM` | POM → Overseas | International: POM → Overseas | Enabled after implementation/UAT |
| `EXP-LAE` | LAE → Overseas | Pre-carriage: LAE → POM; International: POM → Overseas | Enabled after implementation/UAT |
| `EXP-HGU` | HGU → Overseas | Pre-carriage: HGU → POM; International: POM → Overseas | **Disabled until approved HGU → POM BUY and SELL coverage is configured and verified** |

- `BR-JNY-EXP-001`: POM exports contain no regional pre-carriage unless explicitly selected.
- `BR-JNY-EXP-002`: LAE exports include LAE → POM.
- `BR-JNY-EXP-003`: HGU exports require HGU → POM but remain launch-gated while rates are missing.
- `BR-JNY-EXP-004`: Regional pickup, regional handling and regional-to-POM freight belong to pre-carriage.
- `BR-JNY-EXP-005`: Export documentation, security, AWB, terminal and airline-origin charges at POM belong to the international export origin context.
- `BR-JNY-EXP-006`: Overseas destination charges remain export destination charges.

### Invalid or unsupported

| Rule ID | Condition | Behaviour |
|---|---|---|
| `BR-JNY-INV-001` | Overseas → regional PNG shown as direct international | Insert POM or block |
| `BR-JNY-INV-002` | Regional PNG → overseas shown as direct international | Insert POM or block |
| `BR-JNY-INV-003` | International air uses a PNG gateway other than POM | Hard block |
| `BR-JNY-INV-004` | Domestic-only route | Existing/manual domestic workflow |
| `BR-JNY-INV-005` | Third-country route | Unsupported |
| `BR-JNY-INV-006` | More than one regional domestic stop | Manual SPOT at launch |

## 6. Journey and leg contract

Every journey is an ordered list of explicit legs. Each leg records sequence, role, mode, origin, destination, responsible branch, supplier/carrier or manual-source status, chargeable quantity, rate provenance, charges, currencies, tax, totals status, evidence and review status.

| Rule ID | Rule |
|---|---|
| `BR-LEG-001` | A charge without a valid leg cannot enter totals. |
| `BR-LEG-002` | Leg sequence follows physical movement order. |
| `BR-LEG-003` | International and domestic calculations stay separate beneath the combined quote. |
| `BR-LEG-004` | International freight, POM gateway charges and domestic linehaul are never hidden as one undifferentiated cost. |
| `BR-LEG-005` | Local pickup/delivery requires explicit selection or evidence. |
| `BR-LEG-006` | Route/location changes regenerate affected legs and revalidate charge context. |
| `BR-LEG-007` | Incompatible old charges are removed from totals and returned to classification/review. |

## 7. Charge context

Mandatory dimensions:

`service_domain`, `journey_direction`, `journey_pattern`, `leg_id`, `leg_role`, `leg_sequence`, `product_code_domain`, `commercial_position`, `operational_location`, `transport_mode`, `charge_family`, `calculation_basis`, `rate_source`, `currency`, `tax_treatment`, `effective_date`, `evidence`, `include_in_totals`.

Commercial-position examples:

- overseas departure on import → import origin;
- international import linehaul → import freight;
- POM arrival/customs/gateway handling → import destination;
- POM → LAE/HGU linehaul → domestic on-forwarding freight;
- regional → POM export movement → domestic pre-carriage freight;
- POM export processing → export origin;
- POM → overseas linehaul → export freight;
- overseas arrival → export destination.

Ambiguous labels such as `FSC`, `Handling`, `Terminal Fee`, `Documentation`, `Delivery`, `Airport Charge` and `Transfer Fee` require the minimum business clarification. The user is asked what movement/service the charge applies to, not which ProductCode ID to use.

## 8. ProductCode assignment

Resolver order:

1. validate trusted countries and direction;
2. enforce POM and generate the journey;
3. assign the charge to a leg;
4. derive ProductCode domain from that leg;
5. determine commercial position;
6. normalise the governed charge family;
7. apply mode, location, basis and effective date;
8. filter to approved context-compatible candidates;
9. auto-assign only one exact match.

| Rule ID | Rule |
|---|---|
| `BR-PC-001` | Trusted countries outrank parsed/user direction labels. |
| `BR-PC-002` | Overall direction cannot be overridden; ProductCode domain is then derived per leg as `IMPORT`, `EXPORT` or `DOMESTIC`. |
| `BR-PC-003` | Leg and commercial position outrank generic aliases. |
| `BR-PC-004` | Prior mappings/aliases are reusable only when full context remains compatible. |
| `BR-PC-005` | Inactive, expired, wrong-domain or wrong-scope candidates are excluded. |
| `BR-PC-006` | A generic code is not used merely because a specific code is missing. |
| `BR-PC-007` | IDs remain implementation details; users see business meaning and code/name. |
| `BR-PC-008` | Overrides preserve original classification, replacement, reason, user and time. |

Outcomes:

- one exact valid candidate → assign and audit;
- multiple candidates → ask the minimum clarification and rerun;
- no candidate → unresolved with ProductCode request option;
- incomplete route/leg context → block and identify missing data;
- incompatible candidate → reject;
- pending request → remain visible under existing finalisation policy.

## 9. Domestic rates

Approved precedence, highest first:

1. active customer-specific contracted BUY rate;
2. active route/service contract;
3. approved carrier/transport tariff;
4. approved standard internal rate card;
5. valid supplier SPOT quote;
6. manual sourcing.

At equal precedence, the most specific valid route/service/weight/currency/customer match wins. Equal conflicting matches block.

| Rule ID | Rule |
|---|---|
| `BR-RATE-001` | Every required domestic leg needs an approved BUY cost or visible manual-sourcing blocker. |
| `BR-RATE-002` | SELL never substitutes for missing BUY. |
| `BR-RATE-003` | BUY and SELL remain separate and traceable. |
| `BR-RATE-004` | Selection uses route, mode, service, weight/basis, currency, customer and date where applicable. |
| `BR-RATE-005` | Minimums, fuel, handling, security, AWB/documentation and terminal charges are evaluated separately where configured. |
| `BR-RATE-006` | Expired, inactive, unapproved or unsupported rates are excluded. |
| `BR-RATE-007` | Selected rates retain source, supplier, owner, validity and evidence. |
| `BR-RATE-008` | Missing required components remain visible and prevent a complete-looking quote. |

Initial configured domestic freight evidence:

- POM → LAE: present;
- LAE → POM: present;
- POM → HGU: present;
- HGU → POM: absent and launch-blocking for `EXP-HGU`.

## 10. Manual-review conditions

| Rule ID | Trigger | Required action |
|---|---|---|
| `BR-MR-001` | Missing/invalid countries | Correct route data |
| `BR-MR-002` | Unsupported gateway | Block/reconstruct through POM |
| `BR-MR-003` | Unsupported journey/location/mode | Manual SPOT |
| `BR-MR-004` | Required leg missing | Generate or source it |
| `BR-MR-005` | Charge has no leg | Assign context before totals |
| `BR-MR-006` | Ambiguous charge context | Ask business clarification |
| `BR-MR-007` | No ProductCode | Governed request workflow |
| `BR-MR-008` | Required domestic BUY missing | Source approved rate |
| `BR-MR-009` | Equal-precedence conflicting rates | Authorised decision with reason |
| `BR-MR-010` | Expired/out-of-scope rate | Obtain valid rate |
| `BR-MR-011` | Ambiguous basis/minimum/percentage base | Resolve basis |
| `BR-MR-012` | Missing/contradictory FX | Resolve currency treatment |
| `BR-MR-013` | Tax treatment unresolved | Authorised review |
| `BR-MR-014` | Leg and line totals do not reconcile | Correct before finalisation |
| `BR-MR-015` | Customer output differs/omits required content | Block publication |
| `BR-MR-016` | Outside launch scope | Manual SPOT or later phase |

No launch override is permitted for non-POM gateway, missing required leg, totals mismatch, wrong-domain ProductCode or silently missing BUY cost.

## 11. Initial automated scope

Included after implementation and UAT:

- International Air Freight;
- POM gateway only;
- import patterns `IMP-POM`, `IMP-LAE`, `IMP-HGU`;
- export patterns `EXP-POM`, `EXP-LAE`;
- domestic air legs POM → LAE, LAE → POM and POM → HGU;
- one exact context-compatible ProductCode;
- configured approved rate, valid SPOT source or visible manual blocker;
- one customer quote with preserved leg calculations and evidence;
- route-group feature flags.

Excluded or disabled:

1. `EXP-HGU` / HGU → POM until approved BUY and SELL coverage exists;
2. other PNG international gateways;
3. regional locations other than POM, LAE and HGU;
4. domestic-only journeys under this international workflow;
5. sea/coastal/inter-island legs;
6. intercity road linehaul as substitute for the defined domestic air leg;
7. multi-stop domestic journeys;
8. third-country movements;
9. unconfigured automated local pickup/delivery;
10. unsupported automatic special-cargo surcharges;
11. customs-only/brokerage-only journey construction;
12. inferred, stale or unverified rates;
13. autonomous ProductCode approval/creation;
14. autonomous tax, FX, margin, gateway, totals or missing-rate overrides.

## 12. Totals and customer output

| Rule ID | Rule |
|---|---|
| `BR-TOT-001` | One customer quote retains all underlying legs and lines. |
| `BR-TOT-002` | Totals roll up from included international, gateway, domestic, delivery, tax and margin lines only. |
| `BR-TOT-003` | Ignored/informational lines remain evidenced and excluded. |
| `BR-TOT-004` | Compatible lines may group by ProductCode only at output boundaries. |
| `BR-TOT-005` | Different ProductCodes, currencies, tax codes or incompatible components do not group. |
| `BR-TOT-006` | Missing domestic components remain visible and prevent a complete-looking total. |
| `BR-TOT-007` | Reopen/recalculate regenerates affected legs without losing valid evidence/audit. |

Every automatic ProductCode/rate decision retains journey/leg identifiers, direction/pattern, context, evidence, candidates, selected code, rule version, rate provenance, outcome, reason, user/time, before/after values and totals treatment.

## 13. Canonical UAT

| ID | Input | Expected |
|---|---|---|
| `UAT-16A-001` | BNE → POM | One import international leg |
| `UAT-16A-002` | SIN → LAE | SIN → POM → LAE |
| `UAT-16A-003` | BNE → HGU | BNE → POM → HGU |
| `UAT-16A-004` | POM → BNE | One export international leg |
| `UAT-16A-005` | LAE → SIN | LAE → POM → SIN |
| `UAT-16A-006` | HGU → BNE | Pattern recognised but blocked/manual while HGU → POM rate gate is unmet; enabled only after verified coverage |
| `UAT-16A-007` | Supplier says direct SIN → LAE | POM inserted |
| `UAT-16A-008` | Required POM → LAE BUY missing | Visible blocker; no SELL substitution |
| `UAT-16A-009` | FSC lacks leg context | Business clarification |
| `UAT-16A-010` | One exact candidate | Auto-assigned and audited |
| `UAT-16A-011` | Two candidates | Clarification required |
| `UAT-16A-012` | No ProductCode | Request option; unresolved |
| `UAT-16A-013` | Wrong-domain candidate | Rejected |
| `UAT-16A-014` | Equal-precedence rates conflict | Manual decision |
| `UAT-16A-015` | Mixed currencies, valid FX | Preserve, convert and disclose |
| `UAT-16A-016` | Missing FX | Finalisation blocked |
| `UAT-16A-017` | Charge has no leg | Finalisation blocked |
| `UAT-16A-018` | Output total differs | Publication blocked |
| `UAT-16A-019` | Change LAE import to HGU | LAE leg invalidated; HGU leg generated |
| `UAT-16A-020` | Special cargo lacks governed surcharge | Manual SPOT |

## 14. Interpretation rule

For uncovered cases: preserve evidence, do not invent a rule, mark unsupported/unresolved, obtain a business decision, update this document, then automate.
