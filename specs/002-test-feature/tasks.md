# Tasks: AIR · Import · A2D (Airport→Door) v2 rating policy — PREPAID & COLLECT

**Input**: Design documents from `C:\Users\commercial.manager\dev\Project-RateEngine\specs\002-test-feature\`
**Prerequisites**: plan.md (required), research.md, data-model.md, quickstart.md

## Execution Flow (main)
```
1. Load plan.md from feature directory
   → If not found: ERROR "No implementation plan found"
   → Extract: tech stack, libraries, structure
2. Load optional design documents:
   → data-model.md: Extract entities → model tasks
   → contracts/: Each file → contract test task
   → research.md: Extract decisions → setup tasks
3. Generate tasks by category:
   → Setup: project init, dependencies, linting
   → Tests: contract tests, integration tests
   → Core: models, services, CLI commands
   → Integration: DB, middleware, logging
   → Polish: unit tests, performance, docs
4. Apply task rules:
   → Different files = mark [P] for parallel
   → Same file = sequential (no [P])
   → Tests before implementation (TDD)
5. Number tasks sequentially (T001, T002...)
6. Generate dependency graph
7. Create parallel execution examples
8. Validate task completeness:
   → All contracts have tests?
   → All entities have models?
   → All endpoints implemented?
9. Return: SUCCESS (tasks ready for execution)
```

## Format: `[ID] [P?] Description`
- **[P]**: Can run in parallel (different files, no dependencies)
- Include exact file paths in descriptions

## Path Conventions
- **Web app**: `backend/`, `frontend/`

## Phase 3.1: Setup
- [X] T001 [P] Ensure `backend/pricing_v2` module is correctly set up and accessible.

## Phase 3.2: Tests First (TDD) ⚠️ MUST COMPLETE BEFORE 3.3
**CRITICAL: These tests MUST be written and MUST FAIL before ANY implementation**
- [X] T002 [P] Create `backend/pricing_v2/tests/test_a2d_import_policy.py` with a test case for PREPAID A2D Import (e.g., BNE→POM, 81kg), asserting `totals.invoice_ccy == "AUD"` and only destination-side services.
- [X] T003 [P] In `backend/pricing_v2/tests/test_a2d_import_policy.py`, add a test case for COLLECT A2D Import (e.g., BNE→POM, 81kg), asserting `totals.invoice_ccy == "PGK"` and only destination-side services.
- [X] T004 [P] In `backend/pricing_v2/tests/test_a2d_import_policy.py`, add a test case for missing BUY data, asserting `is_incomplete == true` with a clear reason, and no server error.
- [X] T005 [P] Update `backend/tests/test_quote_v2.py` to include golden tests covering both PREPAID and COLLECT for at least AU→PG lanes, as per the spec.

## Phase 3.3: Core Implementation (ONLY after tests are failing)
- [X] T006 In `backend/pricing_v2/dataclasses_v2.py`, update `QuoteContext` to include any new fields required for policy flags (if any).
- [X] T007 In `backend/pricing_v2/dataclasses_v2.py`, update `NormalizedContext` to include derived audience and invoice currency.
- [X] T008 In `backend/pricing_v2/dataclasses_v2.py`, update `BuyResult` to include details on selected fees.
- [X] T009 In `backend/pricing_v2/dataclasses_v2.py`, update `SellResult` to reflect the new fee menu and currency rules.
- [X] T010 In `backend/pricing_v2/dataclasses_v2.py`, update `Totals` to include `invoice_ccy`, `is_incomplete` flag, and `reasons` for manual intervention.
- [X] T011 In `backend/pricing_v2/dataclasses_v2.py`, define a `Snapshot` dataclass to record policy decisions, skipped fees, and reasons.
- [X] T012 In `backend/pricing_v2/recipes.py`, implement or modify logic for audience and invoice currency derivation based on PREPAID/COLLECT payment terms.
- [X] T013 In `backend/pricing_v2/recipes.py`, implement or modify logic for fee menu selection to include only DESTINATION-side services and exclude ORIGIN-side services for A2D imports.
- [X] T014 In `backend/pricing_v2/recipes.py`, implement logic to skip fees if their base is absent and record a warning in the snapshot.
- [X] T015 In `backend/pricing_v2/pricing_service_v2.py`, update the `normalize` function to derive audience and invoice currency.
- [X] T016 In `backend/pricing_v2/pricing_service_v2.py`, update the `rate_buy` function to apply the new fee menu selection rules and handle missing BUY data.
- [X] T017 In `backend/pricing_v2/pricing_service_v2.py`, update the `map_to_sell` function to reflect the new fee menu and currency rules.
- [X] T018 In `backend/pricing_v2/pricing_service_v2.py`, update the `tax_fx_round` function to ensure `totals.invoice_ccy` is correctly set and itemized sell lines are aligned to the invoice currency.
- [X] T019 In `backend/pricing_v2/pricing_service_v2.py`, update the `compute_quote_v2` orchestrator function to handle the `is_incomplete` flag and snapshot generation.

## Phase 3.4: Integration
- [X] T020 Ensure the `/api/quote/compute2` endpoint correctly utilizes the updated `pricing_v2` module and its new policy rules.

## Phase 3.5: Polish
- [X] T021 [P] Run formatting and import sorting for all modified and new Python files.
- [X] T022 Run all tests and ensure they pass.
- [X] T023 Manually test the `/api/quote/compute2` endpoint with the new PREPAID, COLLECT, and missing BUY data scenarios.
- [X] T024 [P] Update `README_v2.md` or other relevant documentation with details about the new policy rules and their impact.

## Dependencies
- T001 before all other tasks.
- T002-T005 before T006-T019.
- T006-T011 before T012-T014.
- T012-T014 before T015-T019.
- T015-T019 can be worked on in order.
- T020 after T006-T019.
- T021-T024 at the end.

## Parallel Example
```
# Launch T001, T002, T003, T004, T005 together:
Task: "[P] Ensure backend/pricing_v2 module is correctly set up and accessible."
Task: "[P] Create backend/pricing_v2/tests/test_a2d_import_policy.py with a test case for PREPAID A2D Import..."
Task: "[P] In backend/pricing_v2/tests/test_a2d_import_policy.py, add a test case for COLLECT A2D Import..."
Task: "[P] In backend/pricing_v2/tests/test_a2d_import_policy.py, add a test case for missing BUY data..."
Task: "[P] Update backend/tests/test_quote_v2.py to include golden tests covering both PREPAID and COLLECT..."
```