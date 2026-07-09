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
