# Tasks: BUY Source Adapters (“Universal Translator”)

**Input**: Design documents from `/specs/003-buy-source-adapters/`

This task list is generated from the implementation plan and design artifacts. Tasks are ordered by dependency, with tests preceding implementation.

## Format: `[ID] [P?] Description`
- **[P]**: Can run in parallel (different files, no dependencies)
- File paths are relative to the `backend/` directory.

## Phase 1: Foundation & Test Scaffolding
- [X] T001 [P] Create `pricing_v2/types_v2.py` with enums: `ProvenanceType`, `FeeBasis`, `Side`, `PaymentTerm`.
- [X] T002 [P] Create `pricing_v2/utils_v2.py` with the `chargeable_kg()` utility function.
- [X] T003 [P] Create `pricing_v2/dataclasses_v2.py` with all required dataclasses (`Provenance`, `BuyBreak`, `BuyFee`, etc.).
- [X] T004 [P] Create `pricing_v2/adapters/base.py` with the `BaseBuyAdapter` abstract base class.
- [X] T005 [P] Create skeleton file `pricing_v2/adapters/ratecard_adapter.py` inheriting from `BaseBuyAdapter`.
- [X] T006 [P] Create skeleton file `pricing_v2/adapters/spot_adapter.py` inheriting from `BaseBuyAdapter`.
- [X] T007 Create `pricing_v2/pricing_service_v2.py` with stub methods for `build_buy_menu()` and `select_best_offer()`.
- [X] T008 Create test file `pricing_v2/tests/test_buy_source_adapters.py` with `xfail` tests for Acceptance Criteria AC1, AC2, AC3, and AC5.

## Phase 2: RateCardAdapter v1 Implementation
- [X] T009 Implement the HTML parser in `pricing_v2/adapters/ratecard_adapter.py` to extract lanes, breaks, fees, and validity from the 2025 HTML card fixtures.
- [X] T010 Add logic to the `RateCardAdapter` to normalize fee codes and encode fee dependencies.
- [X] T011 Implement fee calculation logic in `RateCardAdapter` for mins/caps and percent-of-base rules (fuel%).
- [X] T012 Implement the `collect` method in `RateCardAdapter` to produce `BuyOffer` objects with correct `Provenance`.
- [X] T013 Update `pricing_v2/tests/test_buy_source_adapters.py` to make the tests for AC1, AC2, and AC3 pass using the `RateCardAdapter`.

## Phase 3: SpotAdapter v1 Implementation
- [X] T014 Define the JSON schema for mapped spot quote inputs from the UI in `pricing_v2/adapters/spot_adapter.py`.
- [X] T015 Implement the `collect` method in `SpotAdapter` to transform the mapped JSON into a `BuyOffer`.
- [X] T016 Add a test case to `pricing_v2/tests/test_buy_source_adapters.py` for AC4 to verify comparing and pinning a spot offer against a rate card offer.

## Phase 4: Integration & Guardrails
- [X] T017 Create the `POST /api/quote/compute2` endpoint and wire it to the `pricing_service_v2`.
- [X] T018 Implement feature flags `RATECARD_ADAPTER_ENABLED` and `SPOT_ADAPTER_ENABLED` in `pricing_service_v2`.
- [X] T019 Implement the circuit breaker logic for adapters in `pricing_service_v2.build_buy_menu()`.
- [X] T020 Implement the incomplete path logic in the API view to return HTTP 200 with `is_incomplete=true` when the buy menu is empty.
- [X] T021 Implement snapshot generation in the API view to include `selection_rationale`, `included_fees`, `skipped_fees_with_reasons[]`, and `phase_timings_ms`.
- [X] T022 Implement RBAC serializers for the `/api/quote/compute2` endpoint to hide BUY-side data from Sales roles.
- [X] T023 Add API tests to verify the RBAC payload differences and the snapshot structure.

## Phase 5: Polish & Documentation
- [X] T024 [P] Add golden HTML card fixtures and sample spot email data to the `pricing_v2/tests/` directory.
- [X] T025 [P] Write unit tests for the `ratecard_adapter.py` parser and fee math to achieve ≥90% coverage.
- [X] T026 [P] Write unit tests for `pricing_service_v2.py` selection logic to achieve ≥85% coverage.
- [X] T027 [P] Update `README_v2.md` and `QuotingMatrix.md` with details about the v2 engine.
- [X] T028 [P] Draft `RELEASE_NOTES_v0.4.0.md`.

## Dependencies
- **Phase 1 (T001-T007)** must be completed before other phases.
- **T008** (xfail tests) must be completed before implementation tasks (T009+).
- **RateCardAdapter tasks (T009-T012)** block **T013**.
- **SpotAdapter tasks (T014-T015)** block **T016**.
- **Core implementation (Phases 2-3)** should be complete before **Phase 4 (Integration)**.
- **Phase 5 (Polish)** can be done in parallel after the core features are complete.

## Parallel Example
```
# The initial file scaffolding in Phase 1 can be run in parallel:
Task: "[P] Create `pricing_v2/types_v2.py` with enums..."
Task: "[P] Create `pricing_v2/utils_v2.py` with the `chargeable_kg()`..."
Task: "[P] Create `pricing_v2/dataclasses_v2.py` with all required dataclasses..."
Task: "[P] Create `pricing_v2/adapters/base.py`..."

# Polish tasks in Phase 5 can also be run in parallel:
Task: "[P] Add golden HTML card fixtures..."
Task: "[P] Write unit tests for the `ratecard_adapter.py`..."
Task: "[P] Update `README_v2.md` and `QuotingMatrix.md`..."
```
