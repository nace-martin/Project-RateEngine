# Air Freight Staging Pilot Evidence Log

Status: Phase 15B evidence capture log.

Current launch recommendation: **NO-GO**. Phase 15B could not execute the live staging scenarios because this agent session does not have staging application/database access or staging user credentials. Local automated checks are recorded below as supporting evidence only and are not sufficient to mark the pilot GO.

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
| AF15A-01 Export airport-to-airport quote | Blocked | Source quote, extracted charges, ProductCodes, blockers, totals, public output. | Not available | Not available | Not executed: no staging application/database access or staging user credentials in this session. | Needs staging test | NO-GO until captured. |
| AF15A-02 Import destination-handling quote | Blocked | Source quote, import handling/storage mappings, GST/currency/totals, public output. | Not available | Not available | Not executed: no staging application/database access or staging user credentials in this session. | Needs staging test | NO-GO until captured. |
| AF15A-03 Fuel/FSC ambiguity | Blocked | Broad `FSC` before/after review, finalization blocked while unresolved. | Not available | Not available | Not executed: no staging application/database access or staging user credentials in this session. | Needs staging test | NO-GO until captured. |
| AF15A-04 Generic handling charge | Blocked | Generic `handling` stays manual review and is resolved/excluded with audit. | Not available | Not available | Not executed: no staging application/database access or staging user credentials in this session. | Needs staging test | NO-GO until captured. |
| AF15A-05 Miscellaneous recovery unresolved | Blocked | `misc recovery` remains visible/unresolved or explicitly excluded with reason. | Not available | Not available | Not executed: no staging application/database access or staging user credentials in this session. | Needs staging test | NO-GO until captured. |
| AF15A-06 Customs pass-through charge | Blocked | Customs pass-through manual review or scoped ProductCode selection evidence. | Not available | Not available | Not executed: no staging application/database access or staging user credentials in this session. | Needs staging test if customs appears in pilot replies | Conditional only if customs absent/out of pilot scope and management accepts that scope. |
| AF15A-07 Documentation/AWB ambiguity | Blocked | AWB/docs/terminal ambiguity and scoped/manual treatment. | Not available | Not available | Not executed: no staging application/database access or staging user credentials in this session. | Needs staging test | NO-GO until captured. |
| AF15A-08 Unknown item mapped existing ProductCode | Blocked | Unknown item detail collection, selected ProductCode, single created charge, totals. | Not available | Not available | Not executed: no staging application/database access or staging user credentials in this session. | Needs staging test | NO-GO until captured. |
| AF15A-09 Unknown item new ProductCode request | Blocked | Pending request metadata and finalization blocked while pending. | Not available | Not available | Not executed: no staging application/database access or staging user credentials in this session. | Needs staging test | NO-GO until captured. |
| AF15A-10 Rejected request correction/resubmission | Blocked | Rejection, correction, new request, approval/apply, audit trail. | Not available | Not available | Not executed: no staging application/database access or staging user credentials in this session. | Needs staging test | NO-GO until captured. |
| AF15A-11 Finalize, manager reopen, edit, re-finalize | Blocked | Finalize lock, manager/admin reopen, edit, re-finalize, totals before/after. | Not available | Not available | Not executed: no staging application/database access or staging user credentials in this session. | Needs staging test | NO-GO until captured. |
| AF15A-12 Unauthorized-role checks | Blocked | Sales/finance/cross-scope/unauthenticated attempts and unchanged state. | Not available | Not available | Not executed: no staging application/database access or staging user credentials in this session. | Needs staging test | NO-GO until captured. |

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
| Seed plan dry run | `python backend/manage.py air_freight_pilot_seed_plan --format json` | Blocked locally; staging not executed. | Local command returned `django.db.utils.OperationalError: no such table: product_codes`. | This is not staging evidence. The local default SQLite database was not migrated/seeded. Requires staging DB/API access before UAT. |
| Seed audit | `python backend/manage.py air_freight_pilot_seed_audit --format json` | Not executed after seed-plan blocker. |  | Requires staging DB/API access. |
| Django check | `python backend/manage.py check` | Passed locally: `System check identified no issues (0 silenced).` | Local terminal output. | Supporting evidence only; not a staging scenario pass. |
| Live workspace availability | Open `/quotes/spot/<envelope_id>/exception-workspace` | Not executed. |  | Requires staging URL, SPE ID, and user credentials. |
| ProductCode selector domain | Confirm domain comes from trusted route countries | Not executed. |  | Requires live staging workspace evidence. |

## Defect / blocker log

| ID | Finding | Classification | Scope decision | Status |
| --- | --- | --- | --- | --- |
| P15B-ENV-01 | Phase 15B cannot execute real staging UAT from this agent session because staging application/database access, staging URL, and role-specific user credentials were not available. | Launch blocker for evidence completeness, not a confirmed product defect. | No code fix in scope; requires environment/access handoff and rerun. | Open. |
| P15B-LOCAL-01 | Local seed-plan command failed with `no such table: product_codes` because the local default SQLite DB is not migrated/seeded. | Environment/setup issue; not launch evidence. | No migration or seed apply was run because Phase 15B requires staging evidence and production-like data, not local synthetic DB mutation. | Open as local-only note. |

## Launch decision summary

| Decision item | Status | Notes |
| --- | --- | --- |
| All mandatory scenarios executed | No | AF15A-01 through AF15A-12 were blocked by missing staging access. |
| Zero unresolved blockers | No | Evidence-completeness blocker P15B-ENV-01 remains open. |
| Quote totals/public output verified | No | No staging quote/customer output evidence was available. |
| Manager/admin reopen verified | No | Requires staging manager/admin UI evidence. |
| Unauthorized-role checks verified | No | Requires staging sales/finance/cross-scope/unauthenticated UI/API evidence. |
| Manual-review workload accepted | Pending | Requires manager review after real UAT execution. |

Current recommendation: **NO-GO**.

A future update may change this to `CONDITIONAL GO` or `GO` only after real staging evidence is attached and reviewed. Automated tests, local `manage.py check`, and local/demo evidence must remain supporting evidence only.
