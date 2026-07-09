# Air Freight Pilot UAT Execution Pack

## 1. Pilot objective

Validate that the controlled Air Freight pilot can support quote intake, SPOT Exception Workspace review, scoped ProductCode and ChargeAlias resolution, deterministic quote calculation, and review finalization without unsafe auto-pricing of ambiguous supplier labels.

Phase 13.1J approved a controlled go for Air Freight pilot UAT even though the staging seed audit remains `not_ready`. The remaining missing and conflict items are accepted manual-review items or future enhancements, not seed blockers.

Non-negotiable UAT rule: unscoped ambiguous labels must not be auto-priced without manual review.

## 2. Pilot users and personas

| Persona | Role | UAT responsibility |
| --- | --- | --- |
| Sales operator | Sales | Create/import Air Freight quote scenarios, resolve workspace exceptions, and record usability feedback. |
| Branch manager | Manager | Review exceptions, approve reopen/finalization behavior, and decide whether defects block UAT continuation. |
| Finance reviewer | Finance | Check GST, currency, ProductCode, and charge classification outputs for invoice-readiness risk. |
| Admin/support | Admin | Run preflight commands, inspect audit output, triage defects, and capture remediation actions. |

## 3. Recommended first pilot sequence

1. Run dry-run seed check:

   ```bash
   python backend/manage.py air_freight_pilot_seed_plan --format json
   ```

2. Confirm ProductCodes and aliases are present:
   - ProductCode reuse count is `2` for `IMP-HANDLE-DEST` and `IMP-STORAGE-DEST`.
   - ChargeAlias skip count is `16`.
   - `apply_blocker_count` is `0`.
3. Run the read-only audit:

   ```bash
   python backend/manage.py air_freight_pilot_seed_audit --format json
   ```

4. Confirm remaining audit gaps match Phase 13.1J accepted items:
   - `misc_recoveries`
   - generic `handling`
   - scoped ProductCode and ChargeAlias multi-map warnings
5. Run selected Air Freight quote scenarios below.
6. Collect feedback using the template in this pack.
7. Classify defects as blocker, fix-before-pilot, manual-review acceptable, or future enhancement.
8. Decide proceed, fix, or rollback at the post-UAT decision gate.

## 4. Required UAT scenarios

| ID | Scenario | Test data shape | Expected pass outcome | Fail outcome |
| --- | --- | --- | --- | --- |
| AF-UAT-01 | Export airport-to-airport freight | POM to BNE or POM to SYD with freight, fuel surcharge, AWB/docs, screening | Freight and scoped surcharges resolve to export ProductCodes; quote totals calculate; finalization succeeds after review | Any ambiguous label auto-prices to an unrelated ProductCode, totals are wrong, or finalization bypasses unresolved blockers |
| AF-UAT-02 | Import airport-to-door destination handling | SIN/HKG/SYD to POM with import freight, destination handling, storage/warehouse | `import handling` maps to `IMP-HANDLE-DEST`; `storage` maps to `IMP-STORAGE-DEST`; GST treatment is visible/consistent | Destination handling or storage remains unresolvable despite seeded aliases, or maps to domestic/export ProductCodes |
| AF-UAT-03 | Fuel surcharge ambiguity | Supplier labels include `fuel surcharge`; optionally include broad `fsc` | Scoped `fuel surcharge` resolves only when mode/direction context is clear; broad `fsc` goes to manual review | Broad `fsc` auto-prices without context |
| AF-UAT-04 | Generic handling ambiguity | Supplier label is exactly `handling` without origin/destination context | Line remains manual-review-only; operator must choose the correct ProductCode or defer | Generic `handling` auto-prices |
| AF-UAT-05 | Miscellaneous recovery | Supplier label is `misc recovery`, `admin recovery`, or equivalent broad recovery wording | Line remains manual-review-only; no catch-all ProductCode is used | Misc recovery auto-prices to an unrelated ProductCode |
| AF-UAT-06 | Customs pass-through edge | Supplier label includes customs clearance or pass-through wording | Existing customs codes can be selected manually if applicable; otherwise line remains manual review | Customs pass-through auto-prices incorrectly or blocks unrelated Air Freight quote flow |
| AF-UAT-07 | Documentation/AWB ambiguity | Supplier has AWB, docs, documentation fee, or terminal fee labels | Scoped mappings are used where context is clear; ambiguous terminal/documentation labels can be reviewed manually | Documentation or terminal fee maps to the wrong mode/direction without review |
| AF-UAT-08 | Review finalization guardrails | Leave one unresolved blocker, then resolve it | Finalization fails while blocker remains and succeeds after resolution; finalized workspace is read-only | Finalization succeeds with unresolved blockers or finalized workspace remains editable |
| AF-UAT-09 | Manager reopen | Finalize a review, then reopen as manager | Manager can reopen; non-manager cannot; reopened workspace is editable | Unauthorized reopen succeeds or manager reopen fails |
| AF-UAT-10 | Finance review | Review ProductCodes, currency, GST, and totals for a completed quote | Finance can trace charge classifications and identify manual-review items | GST/currency/ProductCode output is inconsistent or untraceable |

## 5. Manual-review rules

| Label or condition | Required handling |
| --- | --- |
| `misc_recoveries` or broad miscellaneous recovery wording | Manual review only. Do not auto-price. Capture exact label and proposed future mapping. |
| Generic `handling` | Manual review only unless origin/destination/mode context is explicit. |
| Broad `fsc` | Manual review only unless scoped context clearly selects airline, pickup, cartage, or domestic fuel. |
| Customs pass-through | Manual review unless a scoped ProductCode is obvious and finance accepts the treatment. |
| Terminal/documentation ambiguity | Manual review if the label lacks mode/direction context. |
| Multiple ProductCode candidates | Operator must choose a scoped ProductCode; system must not silently choose an arbitrary candidate. |

## 6. Stop/go criteria

Go criteria:

- Seed plan dry-run reports `ready_for_apply`, `apply_blocker_count=0`, ProductCode reuse `2`, and ChargeAlias skip `16`.
- No UAT scenario shows unscoped ambiguous labels being auto-priced.
- Sales can complete core export and import Air Freight quote flows.
- Manager reopen and finalization guardrails behave as expected.
- Finance accepts ProductCode, GST, currency, and manual-review handling for pilot scope.

Stop criteria:

- Any unscoped ambiguous label auto-prices without manual review.
- Import destination handling or storage maps to the wrong ProductCode.
- Finalization succeeds with unresolved blockers.
- Cross-role or cross-scope access bypasses expected permissions.
- Quote totals are materially wrong and cannot be explained through review decisions.

Conditional proceed criteria:

- Minor usability issues may proceed if documented and assigned.
- Manual-review workload may proceed if it is limited to the accepted Phase 13.1J items.
- Future enhancements may proceed only if they do not affect pilot quote correctness.

## 7. Feedback capture template

| Field | Value |
| --- | --- |
| Tester name |  |
| Persona | Sales / Manager / Finance / Admin |
| Date |  |
| Scenario ID |  |
| Origin/destination |  |
| Supplier label tested |  |
| Expected ProductCode or manual-review result |  |
| Actual result |  |
| Pass/fail |  |
| Severity | Blocker / Fix before pilot / Manual-review acceptable / Future enhancement |
| Evidence link or screenshot |  |
| Notes |  |
| Owner |  |
| Target phase |  |

## 8. Known risks

| Risk | Mitigation |
| --- | --- |
| Audit remains `not_ready` because conservative conflict reporting treats scoped multi-maps as conflicts. | Use Phase 13.1J classifications during UAT; do not treat scoped multi-maps as seed blockers. |
| Broad supplier labels may appear more often than expected. | Route broad labels to manual review and capture exact labels for later mapping decisions. |
| Finance may reject GST or GL treatment for a specific supplier recovery. | Do not expand seed data during UAT; record the issue for Phase 13.1L or later. |
| Customs pass-through may become part of pilot scope. | Keep manual-review handling unless a specific scoped customs mapping is approved. |
| Operator may choose the wrong ProductCode manually. | Require manager/finance review for failed or uncertain scenarios. |

## 9. Post-UAT decision gate

| Decision | Criteria |
| --- | --- |
| Proceed | All go criteria pass; no stop criteria triggered; remaining issues are manual-review acceptable or future enhancements. |
| Fix before pilot | Core flow works, but one or more non-destructive fixes are required before wider pilot use. |
| Roll back / pause | Any stop criterion is triggered or quote correctness cannot be verified. |

The post-UAT decision must include:

- Scenario pass/fail summary.
- Defect list with severity.
- Manual-review label list.
- Recommended seed or alias changes, if any.
- Finance sign-off status.
- Manager sign-off status.

## 10. Recommended Phase 13.1L scope

Phase 13.1L should summarize UAT execution evidence and produce a defect/remediation decision pack. It should not add seed writes unless UAT produces a specific approved ProductCode or scoped ChargeAlias requirement.

## 11. Phase 13.1L evidence and defect decision pack

Phase 13.1L captures UAT evidence, classifies findings, and decides what must be fixed before pilot launch versus what can be deferred. This section is a decision pack only: no code changes, seed writes, migrations, or frontend changes.

### Evidence capture method

For each scenario in Section 4, capture one evidence record after the tester completes the flow. Evidence should be stored with the UAT issue, ticket, or shared pilot folder, then summarized in the post-UAT decision gate.

Evidence buckets:

| Bucket | Evidence examples | Required reviewer |
| --- | --- | --- |
| System evidence | Seed plan output, seed audit output, quote/envelope IDs, ProductCodes, aliases, warnings, final status | Admin/support |
| User evidence | Tester notes, user actions, screenshots, unexpected behavior, usability findings | Sales operator or manager |
| Reviewer/finance evidence | GST/GL review, currency checks, ProductCode acceptance, manual-review acceptance or rejection | Finance reviewer |

### Evidence record template

| Field | Value |
| --- | --- |
| Tester |  |
| Date |  |
| Scenario |  |
| Quote/envelope ID |  |
| ProductCodes used |  |
| Aliases used |  |
| Manual-review items triggered |  |
| Warnings shown |  |
| User actions |  |
| Final status |  |
| Pass/fail outcome |  |
| Severity |  |
| Recommended action |  |
| Evidence bucket | System / User / Reviewer-Finance |
| Owner |  |
| Target decision | Go / Fix / Defer |

### Defect severity definitions

| Severity | Definition | Required action |
| --- | --- | --- |
| Blocker | Unsafe pricing, wrong ProductCode, wrong totals, finalization/RBAC failure, or finance rejection affecting pilot correctness | Fix before pilot launch; do not proceed until retested |
| Fix before pilot | Flow can be completed, but issue creates meaningful operator risk, repeated manual workaround, or support burden | Fix before broader pilot use unless manager accepts a written workaround |
| Manual-review acceptable | Issue is already within Phase 13.1J accepted manual-review scope and does not corrupt quote output | Proceed with documented manual-review handling |
| Future enhancement | Issue is outside pilot-critical path and does not affect correctness or controlled UAT operation | Defer to later phase |

### Pass/fail classification rules

| Result | Classification rule |
| --- | --- |
| Pass | Expected ProductCodes or manual-review outcomes occur, totals are explainable, permissions hold, and finance accepts GST/GL treatment. |
| Fail - blocker | Any blocker rule below is triggered. |
| Fail - fix before pilot | No blocker occurs, but user cannot complete the scenario without an unacceptable workaround. |
| Pass with manual review | The scenario completes after accepted manual review for broad or ambiguous labels. |
| Defer | Finding is outside pilot scope and has no effect on quote correctness or launch readiness. |

Clear blocker rules:

- Unsafe ambiguous auto-pricing.
- Wrong ProductCode mapping.
- Materially wrong totals.
- Finalization bypasses blockers.
- Permission/RBAC failure.
- GST/GL finance rejection.

### Go/fix/defer decision table

| Finding type | Decision | Notes |
| --- | --- | --- |
| Blocker severity finding | Fix | Must be corrected and retested before pilot launch. |
| Multiple blocker findings in one scenario | Fix | Pause launch decision until root cause is understood. |
| Fix-before-pilot finding with accepted workaround | Conditional go | Requires manager and finance acknowledgement. |
| Manual-review acceptable finding | Go | Capture label and action taken; no seed change required. |
| Future enhancement | Defer | Add to backlog only if it has a clear owner and business value. |
| Finance rejection of GST/GL treatment | Fix | Treat as blocker for affected ProductCode or charge type. |
| Unscoped ambiguous label manually reviewed correctly | Go | Confirms Phase 13.1J control is working. |

### Pilot launch decision gate

Use this gate after all required UAT scenarios have evidence records.

| Gate item | Launch requirement |
| --- | --- |
| Scenario coverage | All required scenarios have evidence records. |
| Blockers | Zero unresolved blocker findings. |
| Fix-before-pilot findings | Resolved, or explicitly accepted by manager and finance with workaround. |
| Manual-review findings | All accepted manual-review findings have labels and selected actions recorded. |
| Finance sign-off | Finance accepts ProductCodes, GST/GL treatment, currency handling, and manual-review controls. |
| Manager sign-off | Manager accepts workflow, reopen/finalization behavior, and residual risks. |
| Support readiness | Admin/support has command outputs and issue list attached to the launch decision. |

Launch recommendation values:

| Recommendation | Use when |
| --- | --- |
| Proceed to pilot launch | Gate items pass and no unresolved blocker remains. |
| Fix blockers | Any blocker remains unresolved or finance rejects a charge treatment. |
| Proceed to deployment readiness | UAT passes and remaining items are manual-review acceptable or future enhancements. |
| Defer enhancements | Findings are outside pilot correctness and can be scheduled after launch. |

### Recommended Phase 13.1M path

| UAT result | Phase 13.1M should |
| --- | --- |
| Blockers found | Fix blockers first, retest affected scenarios, and update this evidence pack. |
| UAT passes with no blockers | Proceed to deployment readiness and pilot launch checklist confirmation. |
| Only manual-review or enhancement findings remain | Defer enhancements, keep manual-review controls, and document backlog items. |
| Finance rejects GST/GL/ProductCode treatment | Pause launch for affected charge type and create a focused remediation phase. |

## 12. Phase 13.1M controlled UAT execution evidence

Status: Pending live UAT execution.

No real UAT records were provided for Phase 13.1M. The tables below are ready-to-fill evidence logs and must not be treated as passed evidence until tester, quote/envelope, system output, and reviewer fields are completed.

### UAT execution results

| Scenario ID | Scenario | Tester | Date | Quote/envelope ID | Expected result | Actual result | ProductCodes used | Aliases used | Manual-review items triggered | Warnings shown | Final status | Outcome | Severity | Recommended action |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AF-UAT-01 | Export airport-to-airport freight | Pending | Pending | Pending | Export Air Freight quote resolves scoped freight, fuel, screening, and AWB/documentation charges; totals are explainable; finalization guardrails remain active. | Pending live UAT execution | Pending; expected export Air Freight, fuel surcharge, screening, AWB/docs ProductCodes as applicable | Pending; expected freight, fuel surcharge, screening, awb as applicable | Pending; broad or conflicting labels must require manual review | Pending | Pending | Pending | Pending | Execute scenario and attach system, user, and reviewer evidence. |
| AF-UAT-02 | Import airport-to-door destination handling | Pending | Pending | Pending | Import Air Freight quote resolves destination handling and storage where present; destination handling does not map to an origin/export code. | Pending live UAT execution | Pending; expected import handling and storage/warehouse ProductCodes as applicable | Pending; expected import handling and storage as applicable | Pending; uncertain destination labels must require manual review | Pending | Pending | Pending | Pending | Execute scenario and confirm ProductCode mapping before launch decision. |
| AF-UAT-03 | Fuel surcharge ambiguity | Pending | Pending | Pending | Scoped fuel surcharge labels resolve only when unambiguous; broad `fsc` or mixed-scope labels require manual review. | Pending live UAT execution | Pending; expected scoped fuel surcharge ProductCode only when direction/scope is clear | Pending; expected fuel surcharge or manually reviewed broad label | Pending; broad `fsc` must not auto-price | Pending | Pending | Pending | Pending | Execute ambiguity test and verify no unsafe broad-label auto-pricing. |
| AF-UAT-04 | Generic handling ambiguity | Pending | Pending | Pending | Generic handling labels do not auto-price without direction/scope; reviewer selects the correct handling treatment manually. | Pending live UAT execution | Pending; no automatic ProductCode expected for generic handling | Pending; expected handling | Pending; generic handling must require manual review | Pending | Pending | Pending | Pending | Execute scenario and record selected manual-review action. |
| AF-UAT-05 | Miscellaneous recovery | Pending | Pending | Pending | Miscellaneous recovery remains outside automatic seed scope and is routed to manual review or paused charge handling. | Pending live UAT execution | Pending; no automatic miscellaneous recoveries ProductCode expected | Pending | Pending; miscellaneous recovery must require manual review | Pending | Pending | Pending | Pending | Execute scenario and decide whether to proceed with manual review or pause the charge type. |
| AF-UAT-06 | Customs pass-through edge | Pending | Pending | Pending | Customs-related pass-through is not auto-priced unless a scoped, approved ProductCode is selected; uncertain charges require manual review. | Pending live UAT execution | Pending; expected manually selected customs pass-through ProductCode only if approved | Pending | Pending; customs edge cases must require manual review | Pending | Pending | Pending | Pending | Execute scenario and capture finance acceptance or rejection. |
| AF-UAT-07 | Documentation/AWB ambiguity | Pending | Pending | Pending | AWB/documentation labels resolve only when scope is clear; terminal or documentation conflicts are held for manual review. | Pending live UAT execution | Pending; expected scoped AWB/docs ProductCode where clear | Pending; expected awb, documentation fee, terminal fee as applicable | Pending; documentation or terminal conflicts must require manual review | Pending | Pending | Pending | Pending | Execute scenario and confirm conflict handling. |
| AF-UAT-08 | Review finalization guardrails | Pending | Pending | Pending | Finalization is blocked when required blockers remain and succeeds only after allowed review outcomes are complete. | Pending live UAT execution | Not applicable | Not applicable | Pending; unresolved blockers must prevent finalization | Pending | Pending | Pending | Pending | Execute finalization attempts before and after reviewer decisions. |
| AF-UAT-09 | Manager reopen | Pending | Pending | Pending | Manager can reopen an eligible finalized/reviewed item; unauthorized or out-of-scope users cannot bypass RBAC. | Pending live UAT execution | Not applicable | Not applicable | Pending | Pending | Pending | Pending | Pending | Execute manager and non-manager reopen paths and capture status codes/results. |
| AF-UAT-10 | Finance review | Pending | Pending | Pending | Finance accepts ProductCodes, GST/GL treatment, currency handling, totals, and manual-review controls for pilot scope. | Pending live UAT execution | Pending; record all ProductCodes used in reviewed quote | Pending; record aliases used in reviewed quote | Pending; finance-rejected items are blockers or paused charge types | Pending | Pending | Pending | Pending | Execute finance review and record sign-off or rejection. |

### Defect and remediation decisions

| Issue | Severity | Affected scenario | Business risk | Recommended decision | Current status |
| --- | --- | --- | --- | --- | --- |
| Unsafe ambiguous auto-pricing | Blocker | AF-UAT-03, AF-UAT-04, AF-UAT-05, AF-UAT-07 | Wrong charge mapping or incorrect quote total can reach the customer. | Fix before pilot | Pending evidence |
| Wrong ProductCode mapping | Blocker | AF-UAT-01, AF-UAT-02, AF-UAT-06, AF-UAT-07, AF-UAT-10 | Revenue, cost, GST, GL, or operational reporting may be incorrect. | Fix before pilot | Pending evidence |
| Materially wrong totals | Blocker | AF-UAT-01, AF-UAT-02, AF-UAT-06, AF-UAT-10 | Pilot quote cannot be trusted for customer or finance review. | Fix before pilot | Pending evidence |
| Finalization bypasses blockers | Blocker | AF-UAT-08 | Unreviewed or unsafe quote state can be locked as final. | Fix before pilot | Pending evidence |
| Permission or RBAC failure | Blocker | AF-UAT-09 | Unauthorized user can reopen or act outside scope. | Fix before pilot | Pending evidence |
| GST or GL finance rejection | Blocker | AF-UAT-10 | Finance cannot accept the ProductCode or charge treatment. | Pause affected charge type | Pending evidence |
| Accepted broad-label manual review | Manual-review acceptable | AF-UAT-03, AF-UAT-04, AF-UAT-05, AF-UAT-06, AF-UAT-07 | Operator workload increases but quote correctness is preserved. | Proceed with manual review | Pending evidence |
| Non-critical usability enhancement | Future enhancement | Any scenario | Efficiency or clarity issue only; no quote correctness impact. | Defer | Pending evidence |

### Pilot decision

| Decision | Use when | Current Phase 13.1M status |
| --- | --- | --- |
| GO | All required scenarios have evidence, zero unresolved blockers remain, finance signs off, and manager accepts residual risks. | Not available; evidence pending |
| GO WITH CONDITIONS | No unresolved blockers remain, and remaining issues are documented manual-review items or accepted workarounds with owner and reviewer acknowledgement. | Not available; evidence pending |
| NO-GO | Any blocker remains unresolved, quote correctness cannot be verified, or finance rejects GST/GL/ProductCode treatment for pilot scope. | Not available; evidence pending |

Current Phase 13.1M decision: no launch decision yet. Live UAT evidence must be captured before choosing GO, GO WITH CONDITIONS, or NO-GO.

### Recommended Phase 13.1N scope

Because Phase 13.1M is pending live UAT execution, Phase 13.1N should collect completed evidence records for all required scenarios and then apply the decision framework above:

| Phase 13.1M result | Recommended Phase 13.1N path |
| --- | --- |
| Any blocker is confirmed | Open a blocker remediation phase and retest affected scenarios before launch. |
| No blockers and all scenarios pass | Move to the Air Freight pilot deployment readiness checklist. |
| Only manual-review items or enhancements remain | Defer enhancements, keep manual-review controls, and proceed to deployment readiness. |
| Finance rejects an affected charge type | Pause that charge type and create a focused GST/GL/ProductCode remediation phase. |
