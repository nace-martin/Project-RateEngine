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
- [ ] T001 [P] Create new directory `backend/pricing_v2`.
- [ ] T002 [P] Add `QUOTER_V2_ENABLED` to `backend/rate_engine/settings.py` and parse it from environment variables.

## Phase 3.2: Tests First (TDD) ⚠️ MUST COMPLETE BEFORE 3.3
**CRITICAL: These tests MUST be written and MUST FAIL before ANY implementation**
- [ ] T003 [P] Create `backend/tests/test_quote_v2.py` and add 10 golden test cases covering IMPORT/EXPORT/DOMESTIC, MIN vs +45/+100, CAF direction, GST, rounding, bridge/no-bridge, and a manual case.

## Phase 3.3: Core Implementation (ONLY after tests are failing)
- [ ] T004 [P] Create `backend/pricing_v2/dataclasses_v2.py` and define `QuoteContext`, `NormalizedContext`, `BuyResult`, `SellResult`, and `Totals` dataclasses.
- [ ] T005 [P] Create `backend/pricing_v2/recipes.py` and implement the `AUDIENCE`, `INVOICE_CCY`, and `SCOPE_SEGMENTS` tiny tables, a minimal `SellRecipe` for (A2D, PNG_CUSTOMER_PREPAID), and the recipe executor.
- [ ] T006 Create `backend/pricing_v2/pricing_service_v2.py` and implement the `normalize` function.
- [ ] T007 In `backend/pricing_v2/pricing_service_v2.py`, implement the `rate_buy` function.
- [ ] T008 In `backend/pricing_v2/pricing_service_v2.py`, implement the `map_to_sell` function.
- [ ] T009 In `backend/pricing_v2/pricing_service_v2.py`, implement the `tax_fx_round` function.
- [ ] T010 In `backend/pricing_v2/pricing_service_v2.py`, implement the `compute_quote_v2` orchestrator function.

## Phase 3.4: Integration
- [ ] T011 Create `backend/quotes/views_v2.py` (or extend `backend/quotes/views.py`) to add the `/api/quote/compute2` endpoint, which uses `compute_quote_v2` when `QUOTER_V2_ENABLED` is true.
- [ ] T012 Update `backend/rate_engine/urls.py` to include the new `/api/quote/compute2` URL.

## Phase 3.5: Polish
- [ ] T013 [P] Create `README_v2.md` with diagrams of the new architecture, the tiny rule tables, and onboarding notes for Sales/Finance.
- [ ] T014 Run all tests and ensure they pass.
- [ ] T015 Manually test the `/api/quote/compute2` endpoint.

## Dependencies
- T001, T002 before all other tasks.
- T003 before T006-T010.
- T004, T005 before T006-T010.
- T006-T010 can be worked on in order.
- T011, T012 after T010.
- T013-T015 at the end.

## Parallel Example
```
# Launch T001-T005 together:
Task: "[P] Create new directory backend/pricing_v2"
Task: "[P] Add QUOTER_V2_ENABLED to backend/rate_engine/settings.py and parse it from environment variables."
Task: "[P] Create backend/tests/test_quote_v2.py and add 10 golden test cases..."
Task: "[P] Create backend/pricing_v2/dataclasses_v2.py and define dataclasses..."
Task: "[P] Create backend/pricing_v2/recipes.py and implement tiny tables..."
```

```