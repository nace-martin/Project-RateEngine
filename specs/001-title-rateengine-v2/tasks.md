# Tasks: RateEngine v2 — Simple Rating Core

**Input**: Design documents from `C:\Users\commercial.manager\dev\Project-RateEngine\specs\001-title-rateengine-v2\`
**Prerequisites**: plan.md (required), research.md, data-model.md, contracts/ 

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
- [X] T001 [P] Create new directory `backend/pricing_v2`.
- [X] T002 [P] Add `QUOTER_V2_ENABLED` to `backend/rate_engine/settings.py` and parse it from environment variables.

## Phase 3.2: Tests First (TDD) ⚠️ MUST COMPLETE BEFORE 3.3
**CRITICAL: These tests MUST be written and MUST FAIL before ANY implementation**
- [X] T003 [P] Create `backend/pricing_v2/tests/test_air_a2d_prepaid.py` with a test case for BNE→POM, 81kg, PREPAID, asserting `manual_required == False`, correct margin on FREIGHT, pass-through surcharges, and correct totals in `invoice_ccy`.
- [X] T004 [P] Create `backend/tests/test_quote_v2.py` and add 10 golden test cases covering IMPORT/EXPORT/DOMESTIC, MIN vs +45/+100, CAF direction, GST, rounding, bridge/no-bridge, and a manual case.

## Phase 3.3: Core Implementation (ONLY after tests are failing)
- [X] T005 [P] Create `backend/pricing_v2/dataclasses_v2.py` and define `QuoteContext`, `NormalizedContext`, `BuyResult`, `SellResult`, and `Totals` dataclasses.
- [X] T006 In `backend/pricing_v2/dataclasses_v2.py`, extend `QuoteContext` and add `CalcLine` and `CalcResultV2` dataclasses.
- [X] T007 [P] Create `backend/pricing_v2/recipes.py` and implement the `AUDIENCE`, `INVOICE_CCY`, and `SCOPE_SEGMENTS` tiny tables, a minimal `SellRecipe` for (A2D, PNG_CUSTOMER_PREPAID), and the recipe executor.
- [X] T008 In `backend/pricing_v2/recipes.py`, implement the `RECIPE_INDEX` with key ("AIR","A2D","PREPAID") and the `recipe_air_a2d_prepaid` function.
- [X] T009 Create `backend/pricing_v2/pricing_service_v2.py` and implement the `normalize` function.
- [X] T010 In `backend/pricing_v2/pricing_service_v2.py`, implement the `rate_buy` function.
- [X] T011 In `backend/pricing_v2/pricing_service_v2.py`, implement the `map_to_sell` function.
- [X] T012 In `backend/pricing_v2/pricing_service_v2.py`, implement the `tax_fx_round` function.
- [X] T013 In `backend/pricing_v2/pricing_service_v2.py`, implement the `run_recipe` executor and helper functions.
- [X] T014 In `backend/pricing_v2/pricing_service_v2.py`, implement the `compute_quote_v2` orchestrator function.

## Phase 3.4: Integration
- [X] T015 [P] Ensure `seed_bne_to_pom` loads BUY lane breaks and common surcharges. Add any missing fees required by the recipe.
- [X] T016 Create `backend/quotes/views_v2.py` to add the `/api/quote/compute2` endpoint, which uses `compute_quote_v2` when `QUOTER_V2_ENABLED` is true.
- [X] T017 [P] In `backend/quotes/views_v2.py`, guard the endpoint with the `QUOTER_V2_ENABLED` feature flag.
- [X] T018 Update `backend/rate_engine/urls.py` to include the new `/api/quote/compute2` URL.

## Phase 3.5: Polish
- [X] T019 [P] Update `specs/001-title-rateengine-v2/quickstart.md` with the POST example.
- [X] T020 [P] Create `README_v2.md` with diagrams of the new architecture, the tiny rule tables, and onboarding notes for Sales/Finance.
- [X] T021 [P] Run formatting and import sorting for the new files.
- [X] T022 Run all tests and ensure they pass.
- [X] T023 Manually test the `/api/quote/compute2` endpoint.

## Dependencies
- T001, T002 before all other tasks.
- T003, T004 before T009-T014.
- T005, T006 before T007, T008, T013.
- T007, T008 before T013.
- T009-T012, T013 can be worked on in order.
- T014 after T009-T013.
- T015 before T003.
- T016, T017, T018 after T014.
- T019, T020, T021, T022, T023 at the end.

## Parallel Example
```
# Launch T001, T002, T003, T004, T005, T007, T015 together:
Task: "[P] Create new directory backend/pricing_v2"
Task: "[P] Add QUOTER_V2_ENABLED to backend/rate_engine/settings.py and parse it from environment variables."
Task: "[P] Create backend/pricing_v2/tests/test_air_a2d_prepaid.py with a test case for BNE→POM..."
Task: "[P] Create backend/tests/test_quote_v2.py and add 10 golden test cases..."
Task: "[P] Create backend/pricing_v2/dataclasses_v2.py and define dataclasses..."
Task: "[P] Create backend/pricing_v2/recipes.py and implement tiny tables..."
Task: "[P] Ensure seed_bne_to_pom loads BUY lane breaks and common surcharges. Add any missing fees required by the recipe."
```