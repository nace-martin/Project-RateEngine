# Tasks: AIR · Import · A2D — Deterministic currency & destination-fee policy

**Input**: Design documents from `/specs/003-jsonpath-c-users/`

## Phase 1: Project Setup
- [X] T001: Create a new Django app named `pricing_v2` in the `backend` directory.

## Phase 2: Data Structures
- [X] T002: [P] Create `backend/pricing_v2/dataclasses.py` and define the `Policy`, `Recipe`, and `Snapshot` data classes as described in `data-model.md`.

## Phase 3: Core Logic
- [X] T003: [P] Create `backend/pricing_v2/recipes.py` and implement the recipes for currency and fee selection logic.
- [X] T004: Create `backend/pricing_v2/pricing_service_v2.py` and implement the `PricingServiceV2` class. This service will use the policies and recipes to price a quote according to the rules in `spec.md`.

## Phase 4: API Endpoint
- [X] T005: Create a new test file `backend/tests/test_quote_v2.py`. This file will contain integration tests for the new pricing logic, including tests for the PREPAID and COLLECT scenarios from `quickstart.md`.
- [X] T006: Update `backend/quotes/views_v2.py` to use the `PricingServiceV2` for A2D import quotes.
- [X] T007: Update `backend/quotes/urls.py` to ensure the `/api/v2/quotes/` endpoint is correctly wired to the updated `views_v2.py`.

## Phase 5: Integration and Validation
- [X] T008: Create seed data required for the new pricing logic to function correctly.
- [X] T009: Manually test the `/api/v2/quotes/` endpoint using the `curl` commands from `quickstart.md` to validate the implementation against the acceptance criteria.

## Dependencies
- T001 blocks all other tasks.
- T002 blocks T003 and T004.
- T003 and T004 block T006.
- T005 can be worked on in parallel with T002, T003, T004, but must be completed before T006.
- T006 blocks T007.
- T008 can be worked on in parallel with other tasks but must be completed before T009.
- T009 is the final validation step.

## Parallel Example
```
# T002 and T003 can be executed in parallel:
Task: "[P] Create backend/pricing_v2/dataclasses.py and define the Policy, Recipe, and Snapshot data classes as described in data-model.md."
Task: "[P] Create backend/pricing_v2/recipes.py and implement the recipes for currency and fee selection logic."
```
