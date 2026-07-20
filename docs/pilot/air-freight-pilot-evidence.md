# Air Freight Staging Pilot Evidence Log

Status: evidence capture template for Phase 15A staging execution.

Current launch recommendation: **NO-GO** until the evidence table below is completed from the staging environment and reviewed by management. This document must record real staging evidence; local/demo evidence and automated tests are supporting information only.

## Evidence handling rules

- Preserve source evidence exactly as received.
- Record the live Exception Workspace route: `/quotes/spot/<envelope_id>/exception-workspace`.
- Record both SPE ID and quote ID where available.
- Capture before/after blocker state for every manual decision.
- Capture totals, currencies, GST treatment, margins where visible, and public/customer output for completed quote scenarios.
- Capture backend error responses for failed finalize/reopen/unauthorized attempts.
- Do not mark `GO` based on tests alone.

## Scenario evidence matrix

| Scenario ID | Status | Staging evidence required | SPE ID | Quote ID | Current result | Severity | Launch impact |
| --- | --- | --- | --- | --- | --- | --- | --- |
| AF15A-01 Export airport-to-airport quote | Pending | Source quote, extracted charges, ProductCodes, blockers, totals, public output. |  |  | Not executed in Phase 15A. | Needs test | NO-GO until captured. |
| AF15A-02 Import destination-handling quote | Pending | Source quote, import handling/storage mappings, GST/currency/totals, public output. |  |  | Not executed in Phase 15A. | Needs test | NO-GO until captured. |
| AF15A-03 Fuel/FSC ambiguity | Pending | Broad `FSC` before/after review, finalization blocked while unresolved. |  |  | Not executed in Phase 15A. | Needs test | NO-GO until captured. |
| AF15A-04 Generic handling charge | Pending | Generic `handling` stays manual review and is resolved/excluded with audit. |  |  | Not executed in Phase 15A. | Needs test | NO-GO until captured. |
| AF15A-05 Miscellaneous recovery unresolved | Pending | `misc recovery` remains visible/unresolved or explicitly excluded with reason. |  |  | Not executed in Phase 15A. | Needs test | NO-GO until captured. |
| AF15A-06 Customs pass-through charge | Pending | Customs pass-through manual review or scoped ProductCode selection evidence. |  |  | Not executed in Phase 15A. | Needs test if customs appears in pilot replies | Conditional only if customs absent/out of pilot scope. |
| AF15A-07 Documentation/AWB ambiguity | Pending | AWB/docs/terminal ambiguity and scoped/manual treatment. |  |  | Not executed in Phase 15A. | Needs test | NO-GO until captured. |
| AF15A-08 Unknown item mapped existing ProductCode | Pending | Unknown item detail collection, selected ProductCode, single created charge, totals. |  |  | Not executed in Phase 15A. | Needs test | NO-GO until captured. |
| AF15A-09 Unknown item new ProductCode request | Pending | Pending request metadata and finalization blocked while pending. |  |  | Not executed in Phase 15A. | Needs test | NO-GO until captured. |
| AF15A-10 Rejected request correction/resubmission | Pending | Rejection, correction, new request, approval/apply, audit trail. |  |  | Not executed in Phase 15A. | Needs test | NO-GO until captured. |
| AF15A-11 Finalize, manager reopen, edit, re-finalize | Pending | Finalize lock, manager/admin reopen, edit, re-finalize, totals before/after. |  |  | Not executed in Phase 15A. | Needs test | NO-GO until captured. |
| AF15A-12 Unauthorized-role checks | Pending | Sales/finance/cross-scope/unauthenticated attempts and unchanged state. |  |  | Not executed in Phase 15A. | Needs test | NO-GO until captured. |

## Evidence record template

Copy this block once per scenario execution.

### Scenario AF15A-XX — title

| Field | Evidence |
| --- | --- |
| Tester / role |  |
| Date/time |  |
| Environment | Staging |
| Browser route |  |
| SPE ID |  |
| Quote ID |  |
| Source input reference |  |
| Trusted route countries |  |
| Mode / service scope / payment term |  |
| Raw source labels |  |
| Extracted charges |  |
| Unknown/unclassified items |  |
| Initial review queue / blockers |  |
| ProductCodes suggested by system |  |
| ProductCodes selected by operator |  |
| ProductCode request IDs/statuses |  |
| Manual-review decisions |  |
| Ignored/excluded lines and reasons |  |
| Finalization attempt result |  |
| Reopen attempt result, if applicable |  |
| Post-refresh state |  |
| Totals and currency evidence |  |
| GST evidence |  |
| Margin/FX evidence, if visible |  |
| Customer-facing/public quote output |  |
| Screenshots/API payload links |  |
| Pass/fail |  |
| Severity | Blocker / Fix before pilot / Manual-review acceptable / Future enhancement / None |
| Recommended action |  |
| Reviewer decision | GO / CONDITIONAL GO / NO-GO / Pending |

## Preflight evidence

| Check | Command / source | Result | Evidence link | Reviewer notes |
| --- | --- | --- | --- | --- |
| Seed plan dry run | `python backend/manage.py air_freight_pilot_seed_plan --format json` | Pending |  |  |
| Seed audit | `python backend/manage.py air_freight_pilot_seed_audit --format json` | Pending |  |  |
| Django check | `python backend/manage.py check` | Pending |  |  |
| Live workspace availability | Open `/quotes/spot/<envelope_id>/exception-workspace` | Pending |  |  |
| ProductCode selector domain | Confirm domain comes from trusted route countries | Pending |  |  |

## Launch decision summary

| Decision item | Status | Notes |
| --- | --- | --- |
| All mandatory scenarios executed | No | Phase 15A creates the pack only. |
| Zero unresolved blockers | Unknown | Requires staging evidence. |
| Quote totals/public output verified | No | Requires customer-ready staging quotes. |
| Manager/admin reopen verified | Pending | Requires staging UI evidence. |
| Unauthorized-role checks verified | Pending | Requires staging UI/API evidence. |
| Manual-review workload accepted | Pending | Requires manager review after UAT. |

Current recommendation: **NO-GO**.

A future update may change this to `CONDITIONAL GO` or `GO` only after real staging evidence is attached and reviewed.
