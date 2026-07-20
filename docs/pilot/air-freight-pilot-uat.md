# Air Freight Staging Pilot UAT Execution Pack

Status: executable staging plan for Phase 15A.

Current launch recommendation: **NO-GO** until all scenarios below have real staging evidence. Automated tests and local/demo evidence are not enough to mark the pilot GO.

## 1. Objective

Run a controlled staging UAT to decide whether the SPOT Air Freight pilot can launch. The run validates live SPOT intake, Exception Workspace review, ProductCode governance, finalization/reopen controls, quote totals, and customer-facing output without changing pricing logic or hiding missing/ambiguous charges.

The only allowed final recommendations are:

- `GO`: all mandatory scenarios pass with real staging evidence and no unresolved blocker.
- `CONDITIONAL GO`: no correctness/RBAC blocker remains, and any workaround or manual-review dependency is accepted by management with evidence.
- `NO-GO`: any blocker remains unresolved, required evidence is missing, or quote correctness cannot be verified.

## 2. Non-negotiable guardrails

- Missing charges, missing rates, unmapped labels, and unresolved coverage gaps must remain visible.
- Never auto-fill missing components with local SELL rates.
- Ambiguous labels must require manual review.
- ProductCode domain must come from trusted route countries, not free-text direction.
- Pending ProductCode requests must block finalization until approved/applied or otherwise resolved.
- Quote totals must match reviewed charge lines, exclusions, GST, currencies, FX/margins, and public output.
- Finance approval is not required for launch.
- Exact GL-per-charge mapping is not a launch blocker.

## 3. Staging preflight

Run in staging before scenario execution:

```bash
python backend/manage.py air_freight_pilot_seed_plan --format json
python backend/manage.py air_freight_pilot_seed_audit --format json
python backend/manage.py check
```

Record outputs in `docs/pilot/air-freight-pilot-evidence.md` or the external evidence folder. Do not run apply/cleanup/backfill commands during UAT unless separately approved after a dry run.

Required readiness interpretation:

| Check | Pass condition | Failure severity |
| --- | --- | --- |
| Seed plan | No apply blockers for already-approved Air Freight pilot seed scope. | Blocker if required ProductCode/alias records are missing for selected scenarios. |
| Seed audit | Known conservative ambiguity warnings only. | Blocker if a required scoped code is missing or broad ambiguity would auto-price. |
| Route-country classification | Import/export/domestic inferred from trusted route countries. | Blocker if UI/API relies on raw free-text direction. |
| Live workspace route | `/quotes/spot/<envelope_id>/exception-workspace` loads live Draft Quote payload. | Blocker if only demo workspace can execute. |

## 4. Required UAT scenario matrix

Severity values: `Blocker`, `Fix before pilot`, `Manual-review acceptable`, `Future enhancement`, `None`.

| ID | Scenario | Required source input | Expected extracted charges | Expected ProductCodes | Expected manual-review items | Expected blockers | Expected totals/customer-facing output | Evidence to capture | Pass/fail criteria | Severity if fails |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AF15A-01 | Export airport-to-airport quote | Export route using trusted countries, e.g. POM/PG to BNE/AU or SYD/AU; supplier text includes air freight, fuel surcharge, AWB/docs, screening/security. | Freight, fuel/FSC, AWB/docs, screening/security; no destination delivery/local-only charge unless supplied. | Export freight and scoped export surcharges/docs/security codes already present in staging. | Broad `freight`, `fuel`, `docs`, `terminal`, or `screening` labels if scope is unclear. | Any unknown, pending request, or ambiguous ProductCode remains a blocker until reviewed. | Public/customer quote shows only reviewed included charges; totals equal included export charges plus approved taxes/FX/margins; no hidden local SELL fill. | Source text/PDF, SPE ID, quote ID, draft payload, ProductCodes, warning list, totals panel, public quote/PDF screenshot. | Pass if scoped export charges resolve or remain reviewable, blockers prevent finalize until resolved, and customer output matches reviewed charges. | Blocker for wrong ProductCode, hidden rate fill, wrong totals, or unresolved finalize bypass. |
| AF15A-02 | Import destination-handling quote | Import route using trusted countries, e.g. SIN/SG or HKG/HK to POM/PG; supplier text includes import freight, destination handling, storage/warehouse. | Import freight, destination handling, storage/warehouse. | `IMP-HANDLE-DEST`, `IMP-STORAGE-DEST`, plus import freight where applicable. | Generic `handling` if not explicitly destination/import scoped. | Missing import handling/storage mapping blocks finalize until mapped/requested. | Customer output includes reviewed import destination charges and correct GST/currency treatment; no export/domestic code leakage. | SPE/quote IDs, extracted labels, mapped ProductCodes, GST visibility, totals, public output. | Pass if destination handling/storage map only to import destination codes or remain manual review. | Blocker for domestic/export mapping or incorrect customer total. |
| AF15A-03 | Fuel/FSC ambiguity requiring manual review | Any air route with supplier text containing both explicit `fuel surcharge` and broad `FSC`. | Explicit fuel line and broad FSC line if present. | Scoped fuel ProductCode only when direction/scope is unambiguous. | Broad `FSC` must remain manual review. | Broad `FSC` blocks finalization until mapped, ignored, or ProductCode request is approved/applied. | Totals exclude unresolved broad FSC from final output until a reviewed action decides inclusion/exclusion. | Before/after workspace screenshots, review queue, ProductCode selector domain, finalization failure while FSC unresolved. | Pass if broad FSC is never auto-priced and pending request blocks finalize. | Blocker if broad FSC auto-prices or finalizes unresolved. |
| AF15A-04 | Generic handling charge | Route may be import or export; supplier text has exact label `handling` with amount and no origin/destination qualifier. | One generic handling charge. | None automatically unless existing evidence proves scope. Operator may manually choose a scoped ProductCode. | Generic `handling` requires manual review. | Blocks finalization until manual mapping, approved request, or explicit exclusion. | Customer output includes it only after reviewed mapping; if excluded, exclusion reason is auditable and totals omit it. | Source label, review queue, action taken, final totals. | Pass if generic handling does not auto-price. | Blocker if auto-priced to import/export/domestic handling without review. |
| AF15A-05 | Miscellaneous recovery remains unresolved | Supplier text includes `misc recovery`, `admin recovery`, or equivalent broad recovery. | Misc recovery line or unknown item. | None by default. | Must remain manual review; no catch-all ProductCode. | Must block finalization while unresolved unless operator explicitly excludes with reason or creates approved governance path. | Customer output must not silently include/exclude without audit; totals reflect reviewed inclusion/exclusion only. | Review queue, exclusion/request evidence, totals before/after. | Pass if unresolved misc remains visible and auditable. | Blocker if hidden, auto-priced, or finalized unresolved. |
| AF15A-06 | Customs pass-through charge | Supplier text includes customs clearance, customs pass-through, permit, quarantine, or regulatory wording on Air Freight quote. | Customs/regulatory pass-through line. | Existing customs ProductCode may be manually selected only when route/scope is clear. | Customs pass-through must be manual review unless approved scoped mapping exists. | Blocks finalization until reviewed. | Customer output includes reviewed customs pass-through only; no unrelated customs charge aggregation. | Source text, selected ProductCode or unresolved blocker, totals/public output. | Pass if customs does not auto-price incorrectly and does not block unrelated charges. | Blocker if wrong customs ProductCode or wrong totals. |
| AF15A-07 | Documentation/AWB ambiguity | Supplier text includes AWB, docs, documentation fee, terminal fee, or document charge. | AWB/docs/terminal/document charge lines. | Scoped AWB/docs ProductCodes only when context is clear. | Terminal/documentation ambiguity remains manual review if direction/scope unclear. | Ambiguous docs/AWB/terminal blocks until resolved. | Customer output separates included reviewed docs/AWB charges from notes/exclusions; totals match. | Extracted labels, ProductCode candidates, final decisions, public output. | Pass if scoped labels map safely and ambiguous labels stay reviewable. | Blocker if wrong mode/direction docs ProductCode. |
| AF15A-08 | Unknown item mapped to existing ProductCode | Supplier text contains an unstructured line not parsed as a charge, e.g. `Documentation fee USD 25`. | Unknown item in Draft Quote, then created charge line after operator completes label/bucket/currency/amount/unit and selects catalog ProductCode. | Operator-selected existing ProductCode matching trusted route-country domain. | Unknown item requires operator detail collection before mapping. | Unknown item blocks finalization until classified. | One created charge, no duplicate replay charge, included only if reviewed; public total includes exactly one charge. | Unknown item before action, submitted payload fields, reload result, charge count, totals. | Pass if complete payload uses selected ProductCode and source evidence is preserved. | Blocker if generic label used, missing fields submitted, or duplicate charge created. |
| AF15A-09 | Unknown item requesting a new ProductCode | Supplier text contains unknown commercial charge with no existing approved ProductCode. | Unknown item creates provisional charge plus pending ProductCodeCreationRequest. | None until admin approves. | Request metadata must include source label, bucket, unit, currency, amount, and trusted route-country domain. | Pending request blocks finalization. | Customer output cannot finalize with pending request; no silent local SELL substitution. | Request record, source charge metadata, finalization failure, admin queue screenshot. | Pass if pending request blocks finalization and metadata is complete. | Blocker if pending request finalizes or suggested bucket/unit missing. |
| AF15A-10 | Rejected request, correction and resubmission | Start from a pending ProductCode request, reject it as admin, then operator corrects and resubmits. | Existing charge remains needs-review with rejected request metadata; corrected request created. | Approved ProductCode only after admin approval; applying approved code resolves charge. | Rejected status remains visible; resubmission does not mutate rejected historical record. | Rejected/new pending request blocks finalization until approved/applied, mapped existing, or ignored. | Customer output remains unavailable for finalized state until corrected ProductCode is applied. | Admin rejection reason, correction payload, new request ID, approved/apply evidence, audit trail. | Pass if request lifecycle is auditable and finalization waits for resolution. | Blocker if rejected request is hidden or finalization bypasses pending correction. |
| AF15A-11 | Finalize, manager reopen, edit and re-finalize | Complete a reviewed quote, finalize as authorized operator, reopen as manager/admin, edit one non-total or amount field in a controlled way, re-finalize. | No new extraction required; use completed scenario quote. | Existing resolved ProductCodes remain intact unless edited intentionally. | None after first finalize; any edit-created blocker must be visible. | Finalized workspace locked; reopen visible only to manager/admin; after reopen workspace returns `in_review`; re-finalize requires blockers clear. | Customer output before/after edit must match reviewed lines; any changed total is intentional and documented. | Finalize response, post-finalize lock, sales/finance no-action view, manager reopen confirmation, reload state, edit evidence, re-finalize. | Pass if manager/admin can reopen, unauthorized cannot, duplicate reopen blocked, and totals remain explainable. | Blocker for unauthorized reopen, failed lock, or unexplained total change. |
| AF15A-12 | Unauthorized-role checks | Attempt read/action/finalize/reopen as sales, finance, cross-scope user, and unauthenticated user according to role. | No charge changes expected for unauthorized actions. | None. | Unauthorized users must not see/use manager/admin-only reopen. | Forbidden/not-found responses must preserve existing state. | No customer-facing output changes. | Role, endpoint/UI action, HTTP response or hidden UI state, unchanged review status. | Pass if sales/finance cannot reopen, cross-scope cannot access, and failed actions do not mutate state. | Blocker for permission bypass. |

## 5. Evidence record template

Use `docs/pilot/air-freight-pilot-evidence.md` for staging evidence summaries. Attach screenshots/API payloads externally if needed.

| Field | Value |
| --- | --- |
| Scenario ID |  |
| Tester / role |  |
| Date/time |  |
| Environment | Staging |
| Source input reference |  |
| Route countries / mode / scope |  |
| SPE ID |  |
| Quote ID |  |
| Extracted charges |  |
| Unknown/unclassified items |  |
| ProductCodes used |  |
| ProductCode requests |  |
| Manual-review items |  |
| Blockers before resolution |  |
| Actions taken |  |
| Blockers after resolution |  |
| Totals / currencies / GST / margin notes |  |
| Public output evidence |  |
| Pass/fail |  |
| Severity |  |
| Recommended action |  |
| Reviewer decision | GO / CONDITIONAL GO / NO-GO / Pending |

## 6. Pass/fail and severity rules

| Finding | Severity | Required action |
| --- | --- | --- |
| Unsafe ambiguous auto-pricing | Blocker | Stop pilot decision; fix and retest affected charge type. |
| Wrong ProductCode domain/category | Blocker | Fix mapping/path and retest. |
| Materially wrong customer-facing total | Blocker | Fix before launch; quote-first integrity failure. |
| Missing charge hidden from workspace/output | Blocker | Restore visible gap; retest. |
| Finalization with unresolved blocker/pending request | Blocker | Fix finalization guardrail. |
| Unauthorized reopen/action | Blocker | Fix RBAC/UI gating. |
| Manual-review broad label behaves as expected | Manual-review acceptable | Capture label/action; proceed only if workload acceptable. |
| Minor UI clarity issue with correct data/audit | Fix before pilot or Future enhancement | Manager decides whether workaround is acceptable. |
| Exact GL-per-charge ambiguity | Not launch blocker | Record advisory note only. |

## 7. Decision gate

After all scenario evidence is captured, assign one recommendation:

| Recommendation | Required evidence state |
| --- | --- |
| GO | All 12 scenarios pass; zero unresolved blockers; totals/public output verified; manager accepts residual manual-review workload. |
| CONDITIONAL GO | No correctness/RBAC blocker remains; one or more manual-review controls or non-critical workarounds are documented with owner and manager acceptance. |
| NO-GO | Any mandatory scenario is untested, any blocker remains, or quote correctness/customer output cannot be verified. |

Current Phase 15A recommendation: **NO-GO** because this phase prepares the run pack and does not itself provide real staging evidence for every scenario.

## 8. Deliberately out of scope

- Backend RBAC redesign.
- Pricing, GST, FX, margin, quote output, or V4 adapter changes.
- New migrations.
- Seed apply/backfill/cleanup writes.
- Finance approval as a launch gate.
