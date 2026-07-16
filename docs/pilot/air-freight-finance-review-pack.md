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

## Accounting And Readiness Review Notes

| Review item | Current system evidence | Review notes / status |
| --- | --- | --- |
| `IMP-HANDLE-DEST` | Import Destination Handling; domain `IMPORT`; category `HANDLING`; GST `True`; broad internal revenue GL `4400`; broad internal cost GL `5400`; unit `SHIPMENT`. | GST policy application, broad internal GL assumptions, unit, and import destination handling usage logged. |
| `IMP-STORAGE-DEST` | Import Destination Storage / Warehouse; domain `IMPORT`; category `HANDLING`; GST `True`; broad internal revenue GL `4400`; broad internal cost GL `5400`; unit `SHIPMENT`. | GST policy application, broad internal GL assumptions, unit, and storage/warehouse usage logged. |
| Import fuel/FSC treatment | Broad `FSC` requires manual review. `IMP-FSC-CARTAGE-DEST` has domain `IMPORT`; category `SURCHARGE`; GST `True`; broad internal revenue GL `4000`; broad internal cost GL `5000`; unit `PERCENT`. | Pilot import FSC treatment logged. |
| Misc recovery exclusion/manual-review policy | Misc recovery was not auto-priced and was explicitly ignored/excluded from totals. | Exclusion/manual-review policy logged. |
| Generic handling manual-review control | Generic `handling` requires manual review and manager/commercial attention where uncertain. | Manual-review control and manager/commercial review requirement for generic handling logged. |
| Mixed-currency warning/control | Phase 13.1O showed mixed-currency warning while preserving auditable decisions. | Warning/control logged. |
| GST treatment | GST follows existing company policy; ProductCode GST flags are visible on reviewed ProductCodes. | GST policy application for all ProductCodes used in pilot-scope quote logged. |
| Revenue GL | Reviewed codes expose broad internal RateEngine revenue GL mappings. The COA does not provide exact GL accounts for every ProductCode. | Broad internal revenue GL assumptions logged. Exact GL-per-charge mapping is not a launch blocker. |
| Cost GL | Reviewed codes expose broad internal RateEngine cost GL mappings. The COA does not provide exact GL accounts for every ProductCode. | Broad internal cost GL assumptions logged. Exact GL-per-charge mapping is not a launch blocker. |
| Customer-ready quote totals/output | No customer-ready quote output evidence captured yet. | Quote output review pending real quote output verification before launch. |

## Evidence Reviewed For Commercial Awareness

| Evidence | Purpose |
| --- | --- |
| Live Exception Workspace route and envelope ID for each reviewed scenario. | Traceability and audit review. |
| ProductCodes, GST flags, broad internal revenue GL, broad internal cost GL, and units used in the quote. | Accounting mapping visibility. |
| Manual-review actions for broad `FSC`, generic `handling`, misc recovery, customs, documentation/AWB ambiguity. | Verification of manual-review controls. |
| Customer-ready quote totals and customer-facing output, including reviewed charge lines, decisions, exclusions, GST, currency handling, and margins. | Review of customer-facing calculations before launch. |
| Export A2A and documentation/AWB live scenario evidence. | Full pilot verification evidence. |

## Pilot Launch Recommendation Framework

The launch decision is a management function based on operational and correctness criteria. Review feedback serves as advisory input.

- **Launch Recommendation**: The recommendation is **NO-GO** only because required real pilot evidence and customer-ready quote-output evidence remain missing.
- **Feedback Collection**: Reviewers should record any observed correctness concerns or mapping observations in the feedback logs. If a correctness or mapping concern is found, the paused-charge remediation and manual-review controls must be utilized to pause or manually review the affected charges.
- **No Remediation Seeding**: Do not change parser logic, seed data, ProductCodes, ChargeAliases, pricing, totals, or public output in this review phase; if correctness concerns are verified by management, open a focused remediation PR.

## Advisory Review Feedback Log

| Field | Value / Notes |
| --- | --- |
| Reviewer name |  |
| Role | Finance / Commercial / Manager |
| Date |  |
| General mapping feedback |  |
| Observed correctness concerns, if any |  |
| Remediation recommendations |  |
| Evidence reviewed |  |

