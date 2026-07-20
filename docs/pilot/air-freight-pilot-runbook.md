# Air Freight Staging Pilot Runbook

Status: executable operator/admin runbook for Phase 15A staging UAT.

Use with:

- `docs/pilot/air-freight-pilot-uat.md`
- `docs/pilot/air-freight-pilot-evidence.md`

Current launch recommendation remains **NO-GO** until real staging evidence is complete.

## 1. Roles

| Role | Allowed UAT actions |
| --- | --- |
| Sales operator | Create/import pilot quotes, review Draft Quote exceptions, map existing ProductCodes, request ProductCodes, ignore/exclude with reasons, finalize when blockers are cleared. |
| Manager | Observe/validate operator path, reopen finalized reviews, accept/reject conditional workarounds, classify defects. |
| Admin/support | Run preflight commands, verify seed/audit output, approve/reject ProductCode requests, collect API evidence. |
| Finance | Optional advisory review of ProductCodes, GST, currencies, totals, and broad GL assumptions. Finance approval is not required. |

Sales and finance must not be able to reopen finalized reviews. Cross-scope or unauthenticated users must not access or mutate the workspace.

## 2. Preflight

From the repository root in staging:

```bash
python backend/manage.py check
python backend/manage.py air_freight_pilot_seed_plan --format json
python backend/manage.py air_freight_pilot_seed_audit --format json
```

Record outputs in `air-freight-pilot-evidence.md`.

Stop before UAT if:

- a required scoped Air Freight ProductCode is missing;
- seed/audit output shows broad labels could auto-price without review;
- staging users lack active organization/operating-entity/branch/department membership;
- the live Exception Workspace route is unavailable;
- source evidence for a scenario is insufficient.

## 3. Synthetic source inputs

These are safe synthetic staging inputs. They must not be pasted into production customer records unless explicitly approved.

### AF15A-01 Export airport-to-airport

```text
Supplier: Phase 15A Export Air
Route: POM, Papua New Guinea to BNE, Australia
Mode: Air Freight
Service: Airport to Airport
Charges:
Air freight USD 880.00
Fuel surcharge USD 120.00
AWB fee USD 35.00
Screening fee USD 18.00
Total USD 1053.00
Notes: Valid 7 days.
```

### AF15A-02 Import destination handling

```text
Supplier: Phase 15A Import Air
Route: SIN, Singapore to POM, Papua New Guinea
Mode: Air Freight
Service: Airport to Door
Charges:
Air freight USD 740.00
Import handling PGK 125.00
Storage / warehouse PGK 55.00
Total: mixed currency as listed
```

### AF15A-03 Fuel/FSC ambiguity

```text
Supplier: Phase 15A Ambiguous Fuel
Route: HKG, Hong Kong to POM, Papua New Guinea
Mode: Air Freight
Charges:
Air freight USD 600.00
FSC USD 48.00
Fuel surcharge USD 72.00
Total USD 720.00
```

Expected: broad `FSC` requires manual review; do not auto-price it.

### AF15A-04 Generic handling

```text
Supplier: Phase 15A Generic Handling
Route: SIN, Singapore to POM, Papua New Guinea
Mode: Air Freight
Charges:
Handling USD 44.00
Air freight USD 500.00
```

Expected: `handling` requires manual review unless scope is added by evidence.

### AF15A-05 Miscellaneous recovery

```text
Supplier: Phase 15A Misc Recovery
Route: POM, Papua New Guinea to SYD, Australia
Mode: Air Freight
Charges:
Air freight USD 700.00
Misc recovery USD 33.00
```

Expected: `misc recovery` remains unresolved/manual review or explicitly excluded with reason.

### AF15A-06 Customs pass-through

```text
Supplier: Phase 15A Customs Edge
Route: SIN, Singapore to POM, Papua New Guinea
Mode: Air Freight
Charges:
Air freight USD 720.00
Customs clearance pass-through PGK 95.00
```

Expected: manual review unless an approved scoped customs ProductCode is selected.

### AF15A-07 Documentation/AWB ambiguity

```text
Supplier: Phase 15A Docs AWB
Route: POM, Papua New Guinea to BNE, Australia
Mode: Air Freight
Charges:
AWB USD 35.00
Documentation fee USD 25.00
Terminal fee USD 60.00
Air freight USD 810.00
```

Expected: scoped AWB/docs can map only if context is clear; terminal/documentation ambiguity remains reviewable.

### AF15A-08 Unknown mapped to existing ProductCode

```text
Supplier note outside table:
Documentation fee USD 25 applies per shipment.
```

Expected: unknown item requires operator detail collection before classifying as a charge; exactly one charge is created after reload/replay.

### AF15A-09 Unknown new ProductCode request

```text
Supplier note outside table:
Special airside recovery USD 40 applies at destination.
```

Expected: pending ProductCode request is created with bucket/unit/currency/amount/source metadata and blocks finalization.

### AF15A-10 Rejected request correction/resubmission

Use AF15A-09 request, reject it as admin with reason, then resubmit corrected request and approve/apply it.

### AF15A-11 Finalize/reopen/edit/re-finalize

Use a completed scenario quote after all blockers are resolved.

### AF15A-12 Unauthorized checks

Use any finalized scenario quote and attempt actions as sales, finance, cross-scope, and unauthenticated users.

## 4. Scenario execution steps

For each scenario:

1. Create or identify a staging quote/SPOT envelope using the synthetic source input.
2. Confirm trusted route countries and mode are present in the quote/envelope.
3. Open `/quotes/spot/<envelope_id>/exception-workspace`.
4. Confirm the live-data banner is visible and the route is not the demo workspace.
5. Capture the initial Draft Quote state:
   - extracted charges;
   - unknown items;
   - review queue;
   - warnings;
   - totals validation.
6. Resolve only with evidence-backed actions:
   - map existing ProductCode;
   - request ProductCode;
   - ignore/exclude with reason;
   - classify unknown as note/charge;
   - leave unresolved if the scenario requires it.
7. Refresh/reload and confirm persistence.
8. Attempt finalization where the scenario requires it.
9. Capture customer-facing quote output for completed quote scenarios.
10. Record evidence and pass/fail result.

## 5. ProductCode request lifecycle

Required ProductCode request fields:

- source label / description;
- suggested code/name;
- bucket;
- unit/basis;
- currency;
- amount;
- source route-country-derived domain;
- reason;
- source envelope and charge/unknown-item evidence.

Lifecycle:

```text
Operator request
→ Pending admin review
→ Admin approve or reject
→ Operator applies approved ProductCode or corrects/resubmits
→ Finalization only after blocker clears
```

Pending or rejected requests are not resolved ProductCodes and must block finalization unless the charge is explicitly mapped to an existing ProductCode or excluded with an auditable reason.

## 6. Finalize and manager reopen

Finalize pass path:

1. Resolve all required blockers.
2. Confirm `remaining_blockers=0` and `available_actions` includes `finalize`.
3. Click **Finalize Review**.
4. Confirm review status is `finalized` and workspace is read-only.
5. Confirm further resolve actions fail or are disabled.

Reopen path:

1. Log in as manager/admin.
2. Open the finalized live workspace.
3. Confirm **Reopen Review** appears only for manager/admin and live finalized workspace.
4. Confirm the dialog before reopening.
5. Reopen.
6. Confirm the workspace reloads from backend and returns to `in_review` editable state.
7. Edit or resolve a controlled item.
8. Re-finalize and verify totals/customer output again.

Failure path:

- Sales/finance/cross-scope/unauthenticated users must not see or successfully call reopen.
- Failed reopen must keep the workspace finalized and locked.
- Duplicate clicks must not create duplicate reopen requests or mutate local state unexpectedly.

## 7. Totals and customer-facing output verification

For every completed quote scenario, record:

- included charge lines;
- excluded/ignored lines and reasons;
- currency grouping;
- GST treatment by ProductCode;
- FX/margin where visible;
- calculated totals;
- public/customer quote or PDF output.

Pass only if the customer-facing total is explainable from reviewed included charge lines and approved tax/currency/margin rules. Do not pass a scenario if a missing charge, unresolved ProductCode, or mixed-currency issue is hidden.

## 8. Defect triage

| Defect | Severity |
| --- | --- |
| Unsafe ambiguous auto-pricing | Blocker |
| Wrong ProductCode domain/category | Blocker |
| Wrong customer-facing total | Blocker |
| Finalization bypasses unresolved blocker or pending request | Blocker |
| Unauthorized access/reopen/action | Blocker |
| Required scenario cannot be completed due to UI/API issue | Fix before pilot |
| Broad label remains manual review and is auditable | Manual-review acceptable |
| Exact GL-per-charge gap | Not launch blocker |
| Usability improvement with correct audit/totals | Future enhancement or Fix before pilot, manager decision |

## 9. Decision meeting checklist

Before recommending launch, confirm:

- all 12 scenarios have evidence records;
- zero unresolved blockers remain;
- customer-facing quote totals/output were reviewed for export and import scenarios;
- pending request and rejected-request workflows were tested;
- manager reopen was tested in live workspace;
- unauthorized-role checks passed;
- manual-review workload is accepted by management;
- any `CONDITIONAL GO` item has owner, workaround, and retest/monitoring plan.

If any item is missing, recommendation remains **NO-GO**.
