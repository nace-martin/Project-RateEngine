# Air Freight Accounting Mapping Review Pack

Status: Accounting mapping assumptions documented. Current launch recommendation is **NO-GO** because real pilot evidence is still missing.

This pack is for a human reviewer to confirm, reject, or pause the accounting mapping assumptions and pilot readiness controls for the remaining Air Freight pilot launch items. It summarizes the live Exception Workspace evidence already captured and lists the exact decisions still required before launch.

The chart of accounts provides broad/general GL accounts, not exact GL accounts for every ProductCode or charge line. RateEngine GL values in this pack are internal broad mapping assumptions used for reporting and operational classification. Exact GL-per-charge mapping is not a launch blocker. GST follows existing company policy.

Do not use `/quotes/spot/exception-workspace-demo` as evidence. Valid evidence must use `/quotes/spot/<envelope_id>/exception-workspace`.

## Evidence Summary

| Area | Current status | Evidence |
| --- | --- | --- |
| Import A2D handling/storage | Passed system evidence | Phase 13.1O staged envelope `81fe3173-13ca-464f-bb3d-8b15657ac505`; route `/quotes/spot/81fe3173-13ca-464f-bb3d-8b15657ac505/exception-workspace`; `import handling` accepted as `IMP-HANDLE-DEST`; `storage` accepted as `IMP-STORAGE-DEST`; reload preserved decisions. |
| Broad FSC control | Passed system evidence with manual review | Broad `FSC` did not auto-price; it required manual review/ProductCode request. Manual map to `IMP-FSC-CARTAGE-DEST` was used only to complete finalization guardrail testing. |
| Generic handling control | Passed system evidence with manual review | Generic `handling` did not auto-price; reviewer manually mapped it to `IMP-HANDLE-DEST`. |
| Misc recovery control | Passed system evidence with manual review | `misc recovery` did not auto-price; explicit ignore/exclusion persisted after reload. |
| Finalization guardrail | Passed system evidence | Finalize returned `400` while a blocker remained; returned `200` after allowed reviewer action; post-finalize resolve returned `409 DRAFT_QUOTE_FINALIZED`. |
| Reopen control | Passed system evidence | Finance reopen returned `403`; manager reopen returned `200`. |
| Export A2A | Deferred | No export A2A live envelope evidence captured. |
| Documentation/AWB ambiguity | Deferred | No docs/AWB live envelope evidence captured. |
| Customs pass-through | Deferred unless in pilot scope | Treat as manual review unless a scoped customs ProductCode is approved for the pilot scenario. |
| Customer-ready quote totals/output | Deferred | No customer-ready quote output or public quote review captured. Review means confirming the customer-facing quote total matches reviewed charge lines, decisions, exclusions, GST, currency handling, and margins. |

## Accounting And Readiness Decisions Required

| Decision item | Current system evidence | Reviewer decision | Comments / conditions |
| --- | --- | --- | --- |
| `IMP-HANDLE-DEST` | Import Destination Handling; domain `IMPORT`; category `HANDLING`; GST `True`; broad internal revenue GL `4400`; broad internal cost GL `5400`; unit `SHIPMENT`. | Confirm / Reject / Pause |  |
| `IMP-STORAGE-DEST` | Import Destination Storage / Warehouse; domain `IMPORT`; category `HANDLING`; GST `True`; broad internal revenue GL `4400`; broad internal cost GL `5400`; unit `SHIPMENT`. | Confirm / Reject / Pause |  |
| Import fuel/FSC treatment | Broad `FSC` requires manual review. `IMP-FSC-CARTAGE-DEST` has domain `IMPORT`; category `SURCHARGE`; GST `True`; broad internal revenue GL `4000`; broad internal cost GL `5000`; unit `PERCENT`. | Confirm / Reject / Pause | Confirm only if this is acceptable for the pilot import FSC treatment; otherwise pause fuel/FSC pending remediation. |
| Misc recovery exclusion/manual-review policy | Misc recovery was not auto-priced and was explicitly ignored/excluded from totals. | Confirm / Reject / Pause |  |
| Generic handling manual-review control | Generic `handling` requires manual review and manager/commercial attention where uncertain. | Confirm / Reject / Pause |  |
| Mixed-currency warning/control | Phase 13.1O showed mixed-currency warning while preserving auditable decisions. | Confirm / Reject / Pause |  |
| GST treatment | GST follows existing company policy; ProductCode GST flags are visible on reviewed ProductCodes. | Confirm / Reject / Pause |  |
| Revenue GL | Reviewed codes expose broad internal RateEngine revenue GL mappings. The COA does not provide exact GL accounts for every ProductCode. | Confirm / Reject / Pause | Exact per-charge GL mapping is not a launch blocker. |
| Cost GL | Reviewed codes expose broad internal RateEngine cost GL mappings. The COA does not provide exact GL accounts for every ProductCode. | Confirm / Reject / Pause | Exact per-charge GL mapping is not a launch blocker. |
| Customer-ready quote totals/output | No customer-ready quote output evidence captured yet. | Confirm / Reject / Pause | Requires real quote output review before GO. Verify the customer-facing total matches reviewed charge lines, decisions, exclusions, GST, currency handling, and margins. |

## Evidence Reviewer Must Review

| Evidence | Required before |
| --- | --- |
| Live Exception Workspace route and envelope ID for each reviewed scenario. | Any approval decision. |
| ProductCodes, GST flags, broad internal revenue GL, broad internal cost GL, and units used in the quote. | Accounting mapping confirmation. |
| Manual-review actions for broad `FSC`, generic `handling`, misc recovery, customs, documentation/AWB ambiguity. | GO WITH CONDITIONS or paused charge type decision. |
| Customer-ready quote totals and customer-facing output, including reviewed charge lines, decisions, exclusions, GST, currency handling, and margins. | GO or GO WITH CONDITIONS. |
| Export A2A and documentation/AWB live scenario evidence. | Full pilot GO. |

## Go / No-Go Decision

| Decision | Use when | Current status |
| --- | --- | --- |
| GO | Accounting assumptions are confirmed, export A2A and docs/AWB evidence pass, customer-ready quote totals/output are accepted, and no blocker remains. | Not available. |
| GO WITH CONDITIONS | Accounting assumptions and manual-review controls are confirmed, customer-ready quote output is accepted, and any remaining items are explicitly outside pilot scope or accepted manual-review controls. | Not available yet. |
| NO-GO | Real pilot evidence is missing, customer-ready quote output is missing, or a blocker remains unresolved. | Current recommendation because real pilot evidence is missing. |
| Paused charge type | Reviewer rejects or cannot confirm one treatment, but the rest of the pilot may proceed with that charge type excluded or held for manual review. | Available only after the reviewer names the paused treatment and owner. |

If the reviewer confirms all required items and real pilot evidence is complete, update `docs/pilot/air-freight-pilot-uat.md` with the reviewer details and move the recommendation to GO or GO WITH CONDITIONS, depending on remaining scenario coverage.

If the reviewer rejects any ProductCode, GST policy application, broad internal GL mapping assumption, mixed-currency control, manual-review control, or quote-output treatment, keep launch at NO-GO or pause the affected charge type. Do not change parser logic, seed data, ProductCodes, ChargeAliases, pricing, totals, or public output in this review phase; open a focused remediation PR.

## Reviewer Sign-Off

| Field | Value |
| --- | --- |
| Reviewer name |  |
| Role | Finance / Commercial / Manager |
| Date |  |
| Decision | GO / GO WITH CONDITIONS / NO-GO / Paused charge type |
| Confirmed items |  |
| Rejected items |  |
| Paused charge types |  |
| Comments |  |
| Required remediation, if any |  |
| Evidence reviewed |  |
