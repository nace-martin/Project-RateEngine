# RateEngine Phase 16B - International Air Freight Requirements and Current-System Gap Assessment

**Document ID:** RE-REQ-16B-AIR-001  
**Version:** 1.0  
**Assessment date:** 21 July 2026  
**Status:** Authoritative requirements baseline and read-only repository assessment  
**Source business rules:** `docs/business-rules/phase-16a-air-freight-journey-productcode-rules.md`  
**Repository assessed:** `nace-martin/Project-RateEngine`  
**Assessed branch / commit:** `main` at `f14c3ba2f37af1897cef38f3570f74d10aa37f14`  
**Applies to:** Phase 16C architecture, Phase 16D-16G implementation, automated tests, staging UAT and launch decisions

---

## 1. Purpose

This document converts the Phase 16A business rules into testable requirements and records the current RateEngine implementation status against each requirement.

It is intentionally read-only. It does not create ProductCodes, alter rates, change calculations, add migrations or modify application behaviour.

Status values used in this assessment:

- `SUPPORTED` - current code substantially satisfies the requirement;
- `PARTIALLY_SUPPORTED` - a useful foundation exists, but the Phase 16 rule is not fully satisfied;
- `MISSING` - no adequate implementation exists;
- `CONFLICTING` - current behaviour would prevent or contradict the Phase 16 rule;
- `OUT_OF_SCOPE` - the condition is intentionally excluded from automated launch scope.

---

## 2. Executive assessment

### 2.1 Overall verdict

**Phase 16B is ready to proceed to Phase 16C architecture design, but RateEngine is not ready for Phase 16 implementation.**

The repository already provides several strong foundations:

- trusted PNG import/export/domestic country classification;
- separate import, export and domestic pricing engines;
- deterministic rate-selection services with not-found and ambiguity errors;
- domestic COGS and SELL tables;
- domestic POM-to-LAE, LAE-to-POM and POM-to-HGU launch rates;
- ProductCode domains and direction-scoped selection;
- SPOT ProductCode exception handling, audit and finalisation controls;
- customer-output grouping that preserves internal source lines.

The primary missing capability is not another rate table. It is a **journey orchestration layer** that can construct and price an international shipment as ordered international and domestic legs.

### 2.2 Principal launch blockers

1. There is no POM-only international-gateway enforcement or route reconstruction.
2. There is no persisted or contractual shipment-journey / shipment-leg model.
3. Import and export engines cannot compose the domestic engine for regional PNG origins or destinations.
4. SPOT charges have only `airfreight`, `origin_charges` and `destination_charges` buckets; they cannot identify domestic pre-carriage, domestic on-forwarding or final local delivery legs.
5. ProductCode validation uses the overall shipment direction. It therefore rejects `DOMESTIC` ProductCodes inside an `IMPORT` or `EXPORT` international journey.
6. The configured launch tariff contains no HGU-to-POM domestic COGS or SELL freight rate.
7. Domestic-rate rows do not capture the full approved-source hierarchy, source evidence, rate owner, service level, customer specificity or approval status required by Phase 16A.
8. There are no route-group feature flags limiting automation to POM, LAE and HGU.
9. Existing international quote totals do not roll up explicit domestic legs while preserving leg-level reconciliation.

### 2.3 Critical architecture conclusion

ProductCode domain must be resolved **per charge leg**, not once for the whole shipment:

- international import leg and POM import gateway charges use `IMPORT` ProductCodes;
- international export leg and POM export gateway charges use `EXPORT` ProductCodes;
- domestic air pre-carriage or on-forwarding freight and domestic-air surcharges use `DOMESTIC` ProductCodes;
- the journey role still records whether that domestic leg is `EXPORT_PRE_CARRIAGE` or `IMPORT_ON_FORWARDING`.

This retains one commercial truth for domestic air freight while preserving the international journey context. The current overall-direction ProductCode validator must be redesigned for leg-aware validation before Phase 16 can work.

---

## 3. Repository evidence reviewed

| Area | Principal evidence |
|---|---|
| Country classification | `backend/core/business_rules.py` |
| SPOT scope and triggers | `backend/quotes/spot_services.py` |
| SPOT envelope and charge data | `backend/quotes/spot_models.py` |
| Draft Quote route direction | `backend/quotes/services/draft_quote_adapter.py` |
| ProductCode map validation | `backend/quotes/services/draft_quote_resolve_service.py` |
| ProductCode and rate models | `backend/pricing_v4/models.py` |
| Rate selection | `backend/pricing_v4/services/rate_selector.py` |
| Domestic calculation | `backend/pricing_v4/engine/domestic_engine.py` |
| International calculation | `backend/pricing_v4/engine/import_engine.py`, `backend/pricing_v4/engine/export_engine.py` |
| Calculation/API orchestration | `backend/pricing_v4/views.py`, `backend/pricing_v4/adapter.py` |
| ProductCode API | `backend/pricing_v4/views.py::ProductCodeListViewSet` |
| Domestic tariff data | `backend/pricing_v4/management/commands/seed_launch_domestic_tariffs.py` |
| Existing on-forwarding audit | `docs/audits/business-rule-next-phase-audit.md` |
| Customer output grouping | `backend/quotes/quote_result_contract.py`, public quote serializers/views |
| Existing UAT controls | `docs/pilot/air-freight-pilot-uat.md` and Phase 13-15 pilot documents |

---

## 4. Requirements traceability matrix

| Requirement ID | Phase 16A rules | Testable requirement | Current status | Current evidence / gap | Acceptance criterion | Priority | Planned phase |
|---|---|---|---|---|---|---|---|
| `REQ-16B-001` | BR-DIR-001 to 005 | Derive IMPORT, EXPORT, DOMESTIC_ONLY or unsupported direction from trusted countries and fail when country data is missing. | `SUPPORTED` | `classify_png_shipment()` implements PG direction matrix and fails for missing/third-country routes. Current return value is `DOMESTIC`, not the document label `DOMESTIC_ONLY`. | Given trusted country pairs, the resolver returns the expected domain; missing or third-country data blocks automation. | Launch blocker | 16C regression only |
| `REQ-16B-002` | BR-GW-001, BR-GW-002 | Every international air import ends its international leg at POM; every export starts its international leg at POM. | `MISSING` | Country classification does not enforce airport gateway. | SIN-LAE becomes SIN-POM plus POM-LAE; LAE-SIN becomes LAE-POM plus POM-SIN. | Launch blocker | 16C-16E |
| `REQ-16B-003` | BR-GW-003 to 006 | Never treat LAE, HGU or another PNG airport as an international gateway, regardless of user or supplier text. | `MISSING` | Current route validation accepts any PNG airport as an import/export endpoint. | Direct international regional routes are reconstructed through POM or hard-blocked. | Launch blocker | 16C-16E |
| `REQ-16B-004` | BR-JNY-IMP-001 to 006 | Construct `IMP-POM`, `IMP-LAE` and `IMP-HGU` as ordered journey patterns. | `MISSING` | Import engine calculates one lane only and cannot invoke the domestic engine. | All three import UAT patterns contain the exact required legs in order. | Launch blocker | 16C-16E |
| `REQ-16B-005` | BR-JNY-EXP-001 to 006 | Construct `EXP-POM`, `EXP-LAE` and `EXP-HGU` as ordered journey patterns. | `MISSING` | Export engine calculates one lane only and cannot invoke the domestic engine. | All three export UAT patterns contain the exact required legs in order. | Launch blocker | 16C-16E |
| `REQ-16B-006` | BR-JNY-INV-001 to 006 | Reconstruct supported direct regional routes and reject unsupported gateways, domestic-only, third-country and multi-stop patterns. | `PARTIALLY_SUPPORTED` | Domestic-only and third-country classification exist. Gateway reconstruction and multi-stop controls do not. | Every invalid pattern returns a deterministic route decision and no silently incomplete quote. | Launch blocker | 16C-16E |
| `REQ-16B-007` | BR-LEG-001 to 005 | Represent a journey as ordered explicit legs and attach every included charge to one leg. | `MISSING` | No `ShipmentJourney` or `ShipmentLeg` model/contract exists. SPE charge buckets are not leg identifiers. | API and persistence expose leg ID, sequence, type, mode, origin and destination for each included line. | Launch blocker | 16C |
| `REQ-16B-008` | BR-LEG-006, BR-LEG-007 | Regenerate legs and revalidate charges when route or location changes. | `MISSING` | No journey generator exists. | Changing LAE destination to HGU removes/reviews LAE leg lines and generates the HGU leg. | Launch blocker | 16C-16E |
| `REQ-16B-009` | BR-GOV-002, BR-GOV-010 | Prevent totals inclusion for an unassigned or silently moved charge. | `PARTIALLY_SUPPORTED` | SPOT lines support totals exclusion and evidence, but no leg assignment is available. | A line without a valid leg remains visible and blocks finalisation. | Launch blocker | 16C-16G |
| `REQ-16B-010` | Section 8.1 | Resolve the full charge context: domain, journey pattern, leg, position, location, mode, family, basis, rate source, currency, tax, date and evidence. | `PARTIALLY_SUPPORTED` | Current models cover domain, category, bucket, basis, route snapshots, currency and evidence. Journey pattern, leg type/sequence, operational role and governed rate-source hierarchy are absent. | A charge-context object validates all mandatory dimensions before ProductCode selection. | Launch blocker | 16C-16D |
| `REQ-16B-011` | Section 8.2 | Distinguish international origin/freight/destination from domestic pre-carriage/on-forwarding origin/freight/destination and optional final delivery. | `MISSING` | Current charge buckets provide only origin, freight and destination at shipment level. | Every UAT charge is classified to the correct leg and commercial position. | Launch blocker | 16C-16D |
| `REQ-16B-012` | Section 8.3, BR-GOV-006 | For ambiguous labels such as FSC or Handling, request the minimum business clarification rather than guessing. | `PARTIALLY_SUPPORTED` | SPOT supports ambiguous/unmapped review, but questions are not driven by leg-aware context. | An ambiguous FSC asks what movement it applies to, then re-runs context and ProductCode resolution. | Required | 16D-16G |
| `REQ-16B-013` | BR-PC-001 to 003 | Derive ProductCode domain from trusted route and leg context. | `CONFLICTING` | Current Draft Quote resolver derives one expected domain from the whole shipment and rejects any other domain. A domestic leg inside an import/export journey therefore cannot use `DOMESTIC` ProductCodes. | International charges validate to IMPORT/EXPORT; domestic leg charges validate to DOMESTIC without losing journey role. | Launch blocker | 16C-16D |
| `REQ-16B-014` | BR-PC-004 to 006 | Reuse aliases or prior mappings only when route, leg, mode and position remain compatible; do not fall back to a generic code. | `PARTIALLY_SUPPORTED` | ChargeAlias supports mode/domain and origin/main/destination scopes, but not journey leg, location or transport mode. | An alias match incompatible with the current leg is rejected or reviewed. | Launch blocker | 16C-16D |
| `REQ-16B-015` | Section 9.1, 9.3 | Assign a ProductCode automatically only when exactly one active, effective and scope-compatible candidate remains. | `PARTIALLY_SUPPORTED` | Exact/ambiguous alias handling and manual mapping exist. ProductCode has no active/effective fields and candidate filtering lacks Phase 16 context. | One candidate auto-assigns; multiple or zero candidates remain unresolved. | Launch blocker | 16C-16D |
| `REQ-16B-016` | BR-PC-005 | Exclude inactive, expired, wrong-domain and wrong-scope ProductCodes. | `PARTIALLY_SUPPORTED` | Wrong-domain rejection exists. ProductCode itself has no active or validity fields; aliases have active/review state. | Candidate query returns only effective ProductCodes and compatible approved aliases. | Required | 16C-16D |
| `REQ-16B-017` | BR-PC-007, BR-GOV-005 | Never require raw ProductCode IDs from the user. | `SUPPORTED` | Frontend uses human-readable API-backed ProductCode options; IDs remain implementation details. | Operator chooses business meaning/code name, never types an internal ID. | Required | Regression only |
| `REQ-16B-018` | BR-PC-008, BR-GOV-009 | Audit automatic assignment, clarification, override and later changes. | `PARTIALLY_SUPPORTED` | DraftQuoteDecisionDB and charge `rule_meta` audit manual decisions. Automatic resolver rule version and full context are not stored. | Decision record contains candidates, chosen code, rule version, context, evidence, user and timestamp. | Required | 16C-16D |
| `REQ-16B-019` | Section 10.1, 10.2 | Select domestic rates using approved source precedence and exact route/service/customer/date context. | `PARTIALLY_SUPPORTED` | Deterministic date, route, ProductCode, currency and counterparty selection exists. Contract/customer-specific precedence and approval/source-type hierarchy do not. | Most specific valid approved source wins; equal precedence conflicts block. | Launch blocker | 16C-16F |
| `REQ-16B-020` | BR-RATE-001, 002 | A required domestic leg must have a BUY cost or visible manual-source blocker; never substitute SELL for BUY. | `PARTIALLY_SUPPORTED` | Domestic engine has separate COGS/SELL and emits a missing placeholder only when both are absent. It can still produce a SELL line when BUY is missing. International journey finalisation does not know a domestic BUY is required. | Missing BUY always creates a blocking sourcing gap even when a SELL tariff exists. | Launch blocker | 16F |
| `REQ-16B-021` | BR-RATE-003 to 008 | Preserve cost, sell, minimum, weight basis, surcharge, currency, GST, validity, supplier and evidence. | `PARTIALLY_SUPPORTED` | Rate tables cover cost/sell, basis, currency and validity. Rate rows lack source evidence, approval, owner and tax fields; domestic GST is derived from ProductCode. | Each selected domestic rate exposes provenance and all calculation dimensions in audit output. | Required | 16C-16F |
| `REQ-16B-022` | BR-MR-008 to 010 | Missing, conflicting or expired domestic rates must enter manual review. | `PARTIALLY_SUPPORTED` | Rate selector raises not-found/ambiguity. No international-leg orchestrator converts these into Phase 16 journey blockers. | Draft remains open with route-specific sourcing action and cannot finalise. | Launch blocker | 16F-16G |
| `REQ-16B-023` | BR-MR-001 to 007 | Missing route, gateway, leg or ProductCode context must block completion with a specific remediation. | `PARTIALLY_SUPPORTED` | Country and ProductCode errors exist. Gateway and leg errors do not. | Every blocker has a stable error code and business action. | Launch blocker | 16C-16G |
| `REQ-16B-024` | BR-MR-011 to 015 | Ambiguous basis, FX, tax or totals mismatch must block finalisation/publication. | `PARTIALLY_SUPPORTED` | SPOT supports basis/currency review and unresolved-item finalisation blocks. Explicit leg reconciliation and publication comparison are not Phase 16 aware. | Finalise/publish fails until charge, leg and output totals reconcile. | Launch blocker | 16F-16H |
| `REQ-16B-025` | Section 11.3 | No launch override for gateway, required leg, totals, wrong-domain code or missing BUY. | `MISSING` | These Phase 16 blocker types do not yet exist. | Permissions cannot bypass the five non-overridable controls. | Launch blocker | 16C-16G |
| `REQ-16B-026` | Section 12.1 | Automate only international air via POM for POM, LAE and HGU route patterns. | `MISSING` | Current domestic tariff seed contains many PNG routes; no journey automation allowlist exists. | Route allowlist exposes only six approved journey patterns. | Launch blocker | 16C-16E |
| `REQ-16B-027` | BR-GOV-012 | Feature-flag automation by route group. | `MISSING` | No route-group feature flag was found. | IMP-LAE, IMP-HGU, EXP-LAE and EXP-HGU can be independently disabled. | Launch blocker | 16C-16E |
| `REQ-16B-028` | Section 12.2 | Excluded locations, modes, multi-stop, special cargo and unsupported services remain manual/SPOT. | `PARTIALLY_SUPPORTED` | SPOT/manual commodity controls exist. Route, mode and location exclusions are not governed by a Phase 16 allowlist. | Excluded case never appears automatically complete and preserves all evidence. | Required | 16C-16G |
| `REQ-16B-029` | BR-TOT-001 to 003 | Produce one customer quote from included leg lines while retaining underlying calculations and explicit exclusions. | `PARTIALLY_SUPPORTED` | Quote line result and exclusion behaviour exist, but not multi-leg roll-up. | Quote total equals the sum of included lines across all journey legs. | Launch blocker | 16F |
| `REQ-16B-030` | BR-TOT-004, 005 | Group compatible public lines only at output boundaries and preserve internal lines. | `SUPPORTED` | Existing ProductCode grouping protects currency/tax/component boundaries and retains internal lines. | Phase 16 domestic lines follow the same grouping guardrails. | Required | Regression only |
| `REQ-16B-031` | BR-TOT-006 | Missing domestic components must remain visible and prevent a complete-looking total. | `MISSING` | International quotes have no required domestic leg/component awareness. | Missing POM-LAE or HGU-POM component appears as a visible blocker, not a zero-hidden line. | Launch blocker | 16F-16G |
| `REQ-16B-032` | BR-TOT-007 | Reopen/recalculate without losing evidence and with affected leg regeneration. | `PARTIALLY_SUPPORTED` | SPOT reopen and decision persistence exist. Journey regeneration does not. | Reopened route change produces correct new legs and preserved decision history. | Required | 16E-16H |
| `REQ-16B-033` | Section 14 | Retain full ProductCode, rate, leg, source and before/after audit evidence. | `PARTIALLY_SUPPORTED` | Strong SPOT evidence exists, but leg and automatic-rate provenance fields are incomplete. | Audit can reconstruct why each final charge and rate was used. | Required | 16C-16F |
| `REQ-16B-034` | Section 15 | Implement all 20 canonical scenarios as traceable automated and UAT cases. | `MISSING` | Existing tests cover direction, domestic engine and SPOT independently, not the Phase 16 journeys. | Every UAT ID links to at least one automated test and recorded staging evidence. | Launch blocker | 16H-16I |

---

## 5. Current-system gap assessment by subsystem

### 5.1 Direction and gateway

`classify_png_shipment()` is suitable as the trusted top-level country classifier. It should remain small and deterministic.

It must not be expanded into a full routing engine. Phase 16C should introduce a separate journey resolver that receives trusted countries and airport/location codes, applies the POM rule, and produces a journey decision.

Current risk: `SIN -> LAE` is correctly classified as `IMPORT`, but nothing prevents the application from treating LAE as the direct international destination.

### 5.2 Journey and leg representation

No durable journey abstraction was found.

Current structures are insufficient:

- `SpotPricingEnvelopeDB.shipment_context_json` stores one overall origin/destination;
- `SPEChargeLineDB.bucket` stores only airfreight/origin/destination;
- `QuoteComponent` represents commercial grouping, not physical journey order;
- import/export/domestic engines return independent `QuoteResult` objects;
- no orchestration contract links those results as legs.

Phase 16C must define the canonical journey and leg contract before migrations or engine integration are attempted.

### 5.3 ProductCode assignment

#### Existing strengths

- ProductCode domains are explicit: EXPORT, IMPORT and DOMESTIC.
- ID ranges are domain-protected.
- aliases support approved/candidate/rejected states and origin/main/destination scope.
- SPOT mapping fails closed when trusted direction is unavailable.
- wrong-domain manual mappings are rejected.
- unresolved codes have a governed ProductCode request lifecycle.

#### Gaps

ProductCode currently lacks the Phase 16 dimensions needed for exact context matching:

- journey role;
- leg type;
- transport mode;
- operational location;
- service domain;
- effective/active lifecycle on ProductCode itself;
- contextual specificity ranking.

#### Direct conflict to resolve

`_expected_product_code_domain()` returns the shipment's overall IMPORT/EXPORT/DOMESTIC direction. `_validate_product_code_domain()` then requires every mapped line to match that single domain.

That is safe for a single-leg quote but incompatible with Phase 16. An import to LAE needs IMPORT codes for the international/POM context and DOMESTIC codes for the POM-LAE air leg.

#### Phase 16C recommended rule

Add `product_code_domain` to the resolved charge context and derive it from the assigned leg:

| Leg / charge context | ProductCode domain |
|---|---|
| International import and POM import gateway charges | IMPORT |
| International export and POM export gateway charges | EXPORT |
| Domestic air pre-carriage/on-forwarding freight and domestic-air surcharges | DOMESTIC |
| International destination charges overseas | EXPORT |
| Optional local PNG cartage directly tied to import/export service | Existing IMPORT/EXPORT local ProductCode rules unless explicitly modelled as a separate domestic transport service |

This avoids creating duplicate domestic freight ProductCodes merely to label the wider journey direction.

### 5.4 Domestic pricing and rate source

The domestic engine is a useful reusable calculation unit. It already supports:

- route-specific COGS and SELL freight;
- separate cost and sell;
- date validity;
- currency and counterparty selection;
- global domestic surcharges;
- missing-rate placeholders;
- ProductCode line output;
- GST calculation.

It is currently a standalone quote engine. The international engines do not dispatch to it.

Important safety gap: `_calculate_freight()` emits a missing placeholder only when both COGS and SELL are missing. Phase 16 requires missing BUY to remain a blocker even when a SELL tariff exists.

### 5.5 SPOT and manual review

The Exception Workspace is a strong base for ProductCode and source-evidence exceptions. It already handles:

- ambiguous/unmapped lines;
- manual ProductCode selection;
- ProductCode request, approval and rejection;
- persisted user decisions;
- ignored items with evidence;
- finalisation lock and manager/admin reopen;
- wrong overall-domain mapping rejection.

It does not yet understand:

- gateway failures;
- missing journey legs;
- domestic rate sourcing per leg;
- leg-aware ProductCode candidates;
- route reconstruction;
- per-leg totals reconciliation.

Phase 16G should extend the existing workspace rather than create a parallel exception UI.

### 5.6 Quote totals and public output

Existing output-boundary grouping should be retained. The missing work is upstream:

1. calculate each leg separately;
2. preserve each line's leg identity;
3. consolidate included lines into one quote result;
4. reconcile per-leg subtotal, quote total and public total;
5. group only compatible public lines.

The existing SPOT merge audit also identifies a separate risk: bucket-level replacement can remove valid standard lines when one SPOT line exists in the bucket. Phase 16 implementation must use line/ProductCode-level reconciliation, not broad bucket replacement.

---

## 6. ProductCode catalogue gap report

### 6.1 Existing relevant catalogue structure

| Capability | Current state |
|---|---|
| Overall domain | IMPORT / EXPORT / DOMESTIC |
| Broad category | Freight, handling, clearance, documentation, regulatory, cartage, agency, screening, surcharge |
| Default unit | Shipment, kg or percent |
| Alias domain scope | Import, export, domestic or any |
| Alias position scope | Origin, main, destination or any |
| Domestic freight code | `DOM-FRT-AIR` |
| Domestic surcharge examples | `DOM-DOC`, `DOM-TERMINAL`, `DOM-AWB`, `DOM-SECURITY`, `DOM-FSC`, `DOM-DG-HANDLING` |
| Import destination examples | `IMP-HANDLE-DEST`, `IMP-STORAGE-DEST` |

### 6.2 Catalogue gaps

1. No ProductCode/alias dimension identifies domestic pre-carriage versus domestic on-forwarding.
2. No dimension identifies the physical leg or sequence.
3. No mode field distinguishes domestic air from local road/cartage within the same broad category.
4. No operational-location scope distinguishes POM transfer handling from LAE/HGU arrival handling.
5. Generic aliases such as FSC can match only broad domain/position scopes, not the exact movement.
6. ProductCode records have no active/effective lifecycle fields.
7. The API endpoint filters by one domain only and cannot request valid codes for a selected leg context.
8. Current overall-direction validation rejects domestic codes inside international journeys.

### 6.3 Do not create ProductCodes during Phase 16B

Phase 16C must first decide which missing distinctions belong in:

- the ProductCode's commercial identity;
- the journey/charge context;
- the rate row;
- the alias scope.

Strong recommendation: do not create separate `IMP-DOM-FRT-*` and `EXP-DOM-FRT-*` codes merely to encode journey role. Keep `DOM-FRT-AIR` as the domestic freight truth and store `IMPORT_ON_FORWARDING` / `EXPORT_PRE_CARRIAGE` on the leg and charge context.

Create a new ProductCode only when the charge is commercially different, not merely because it appears in a different journey.

---

## 7. Domestic rate-source inventory

The repository's launch tariff command states that COGS comes from the original buy-rate sheet and SELL comes from the corrected POM/LAE commercial sheet. The source sheets themselves, approval owner and validity evidence are not attached to the selected rate rows.

### 7.1 Launch route inventory found in code

| Required route | COGS freight | SELL freight | Currency | Repository status | Phase 16 assessment |
|---|---:|---:|---|---|---|
| POM -> LAE | K6.10/kg | K7.30/kg | PGK | Present in `seed_launch_domestic_tariffs.py` | Configured foundation; source approval/evidence still required |
| LAE -> POM | K6.10/kg | K7.10/kg | PGK | Present | Configured foundation; source approval/evidence still required |
| POM -> HGU | K8.85/kg | K10.30/kg | PGK | Present | Configured foundation; source approval/evidence still required |
| HGU -> POM | Not found | Not found | - | Missing from launch tariff tuples | **Launch blocker for EXP-HGU** |

### 7.2 Global domestic surcharge inventory found in code

#### COGS

| ProductCode | Basis | Rate | Minimum |
|---|---|---:|---:|
| `DOM-DOC` | Flat | K35.00 | - |
| `DOM-TERMINAL` | Flat | K35.00 | - |
| `DOM-SECURITY` | Per kg | K0.20 | K5.00 |
| `DOM-FSC` | Per kg | K0.50 | - |

#### SELL

| ProductCode | Basis | Rate | Minimum |
|---|---|---:|---:|
| `DOM-AWB` | Flat | K70.00 | - |
| `DOM-SECURITY` | Per kg | K0.20 | K5.00 |
| `DOM-FSC` | Per kg | K0.70 | - |
| `DOM-DG-HANDLING` | Flat | K195.00 | - |

Special uplifts also exist for express, valuable cargo, live animals and oversize cargo. Phase 16A excludes automatic special-cargo surcharges where no exact governed rate applies; these rules must remain subject to commodity eligibility and SPOT controls.

### 7.3 Rate-data gaps

- HGU-to-POM freight is missing.
- No source document/reference is persisted on DomesticCOGS or DomesticSellRate.
- No approval state or approving user is persisted on rate rows.
- No rate-source type expresses customer contract, carrier tariff, EFM rate card, supplier spot or manual source.
- No customer-specific domestic COGS/SELL selection hierarchy exists in the domestic engine.
- No service-level field distinguishes standard, express or other service on freight rate rows.
- No explicit commodity/special-handling scope exists on the base rate row; separate commodity rules are used.
- Domestic GST/tax is derived from ProductCode rather than rate source, which is acceptable if existing policy remains authoritative.
- Existing tariffs include many locations beyond the Phase 16 launch scope; automation therefore requires a separate journey allowlist, not deletion of those rates.

### 7.4 Required business evidence before Phase 16I UAT

For each of the four launch directions, record:

- supplier/carrier;
- exact source sheet or quotation;
- rate owner;
- validity dates;
- minimum charge;
- chargeable-weight rule;
- included and excluded surcharges;
- GST treatment;
- service level;
- approval status;
- whether the rate is COGS, SELL or both.

---

## 8. Manual-review and finalisation assessment

| Phase 16 condition | Current support | Gap |
|---|---|---|
| Missing countries | Supported | Existing error must be carried into journey contract |
| Wrong ProductCode overall domain | Supported | Must become per-leg domain validation |
| Unmapped / ambiguous ProductCode | Supported | Needs leg-aware clarification questions |
| Pending ProductCode request | Supported | Must remain blocking under current policy |
| Missing domestic freight rate | Partial | Standalone domestic error exists; no international journey blocker |
| Equal-precedence rate conflict | Partial | Rate selector raises ambiguity; source precedence is incomplete |
| Missing domestic BUY with SELL present | Not supported safely | Must block; current domestic engine may still emit SELL |
| Missing required leg | Missing | Requires journey model/generator |
| Non-POM international gateway | Missing | Requires hard gateway rule |
| Charge without leg | Missing | Requires leg assignment |
| FX/tax ambiguity | Partial | Existing controls must be connected to leg roll-up |
| Totals mismatch | Partial | No leg reconciliation |
| Public output mismatch | Partial | Existing output safeguards, no multi-leg proof |
| Unsupported launch route | Missing | Requires allowlist/feature flag |

---

## 9. Required Phase 16C architecture decisions

Phase 16C must resolve the following before code implementation:

1. **Journey contract:** exact fields, stable enums and persistence boundary for journey and legs.
2. **Journey resolver:** pure deterministic service for direction, POM enforcement, pattern and leg generation.
3. **Per-leg ProductCode domain:** replace overall shipment-domain validation with context-aware validation.
4. **Charge-to-leg assignment:** how parser buckets, standard engine lines and manual lines receive leg identity.
5. **Pricing orchestrator:** compose import/export and domestic engines without mutating their core commercial calculations unnecessarily.
6. **Rate provenance:** extend or companion-model domestic rates with source type, evidence, approval and owner.
7. **Missing BUY behaviour:** represent cost gaps independently from SELL availability.
8. **Route feature flags:** independently enable IMP-LAE, IMP-HGU, EXP-LAE and EXP-HGU.
9. **Totals contract:** per-leg subtotal, total cost, sell, margin, GST, FX and public-output reconciliation.
10. **SPOT integration:** extend the existing Exception Workspace with journey/rate blockers rather than create a new workflow.
11. **Recalculation:** route changes regenerate affected legs while preserving audit history.
12. **Rollback:** disable route groups without reverting unrelated pricing features.

---

## 10. Recommended Phase 16C boundaries

Phase 16C should remain architecture and contract work only.

### Include

- architecture decision record;
- journey and charge-context schemas/enums;
- ProductCode domain decision flow;
- API request/response contracts;
- data-model proposal and migration plan;
- pricing-orchestrator design;
- rate-provenance design;
- feature-flag design;
- totals/reconciliation contract;
- implementation sequence and rollback plan.

### Exclude

- migrations;
- ProductCode creation;
- domestic-rate writes;
- engine behaviour changes;
- frontend implementation;
- live data backfill;
- route automation.

---

## 11. Phase 16B exit gate

Phase 16B is complete when this document and the Phase 16A source rules are accepted in the repository.

The phase concludes with the following decision:

```text
READY_FOR_PHASE_16C_DESIGN = YES
READY_FOR_PHASE_16_IMPLEMENTATION = NO
```

Implementation must not begin until Phase 16C resolves the per-leg ProductCode domain, journey contract, orchestration and rate-provenance decisions.

---

## 12. Immediate next action

Begin **Phase 16C - Journey, Charge Context and ProductCode Resolver Architecture**.

The first design artifact must show, end to end, how this example is represented and priced:

```text
SIN -> POM -> LAE

Leg 1: INTERNATIONAL_IMPORT
ProductCode domain: IMPORT

Leg 2: IMPORT_ON_FORWARDING / DOMESTIC_AIR
ProductCode domain: DOMESTIC

Customer output: one quote
Internal truth: two legs, separately calculated and reconciled
```

If the architecture cannot represent that case without guessing, duplicating commercial truth or hiding a missing BUY rate, it is not ready.
