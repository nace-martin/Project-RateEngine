# Implementation Plan: BUY Source Adapters (“Universal Translator”)

**Branch**: `feat/003-buy-source-adapters` | **Date**: 2025-10-02 | **Spec**: [./spec.md](./spec.md)
**Input**: Feature specification from `specs/003-buy-source-adapters/spec.md`

## Execution Flow (/plan command scope)
This plan follows the execution flow defined in the `plan-template.md`. All steps have been completed, and the generated artifacts are located in this directory.

## Summary
This plan implements the spec for **BUY Source Adapters**, which normalize partner prices (rate cards, spot emails) into a single internal `BuyOffer`/`BuyMenu` format. This allows for deterministic selection, consistent application of business rules, and resilient error handling, adhering to the project constitution.

## Technical Context
**Language/Version**: Python 3.11+
**Primary Dependencies**: Django, Django REST Framework
**Storage**: N/A for this feature (future phase may use DB for rate cards)
**Testing**: pytest
**Target Platform**: Backend Server (Linux)
**Project Type**: Web application (backend focus)
**Performance Goals**: Adapters ≤ 2s each; total compute ≤ 3s prod.
**Constraints**: Must handle HTML parsing for rate cards; must provide clear `is_incomplete` responses instead of errors.
**Scale/Scope**: MVP includes two adapters (RateCard, Spot) for AIR freight.

## Constitution Check
*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **[x] §1 Code Quality**: Is the design deterministic and does it respect the Universal Translator architecture?
- **[x] §2 Testing**: Are business-real test scenarios defined?
- **[x] §3 UX**: Does the design prioritize simplicity and workflow awareness?
- **[x] §5 Determinism**: Does the selection logic follow the strict priority and tie-breaker rules?
- **[x] §6 Resilience**: Are failure modes handled gracefully (no 500s)? Are performance budgets respected?
- **[x] §7 Observability**: Does the design include all required fields in the audit snapshot?
- **[x] §8 RBAC**: Is the data properly segregated between Sales and Manager roles?
- **[x] §10 Business Rules**: Are all relevant hard guardrails (weight, fees, rounding) accounted for?
- **[x] §15 DoD**: Does the plan account for all items in the Definition of Done?

## Project Structure

### Documentation (this feature)
```
specs/003-buy-source-adapters/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   └── api.yaml         # Phase 1 output
└── tasks.md             # Phase 2 output (/tasks command)
```

### Source Code (repository root)
```
backend/
└── pricing_v2/
    ├── adapters/
    │   ├── base.py
    │   ├── ratecard_adapter.py
    │   └── spot_adapter.py
    ├── tests/
    │   └── test_buy_source_adapters.py
    ├── dataclasses_v2.py
    ├── pricing_service_v2.py
    └── types_v2.py
```

**Structure Decision**: Option 2: Web application

## Phase 0: Outline & Research
- **Status**: Complete
- **Output**: [research.md](./research.md)
- **Summary**: The feature spec and user-provided implementation plan were sufficiently detailed, so no external research was required.

## Phase 1: Design & Contracts
- **Status**: Complete
- **Outputs**:
  - [data-model.md](./data-model.md)
  - [contracts/api.yaml](./contracts/api.yaml)
  - [quickstart.md](./quickstart.md)
- **Summary**: Core data structures (enums and dataclasses), API contracts, and user-facing test scenarios have been defined.

## Phase 2: Task Planning Approach
*This section describes what the /tasks command will do - DO NOT execute during /plan*

**Task Generation Strategy**:
The `/tasks` command will generate a `tasks.md` file by breaking down the user-provided implementation plan into granular, executable tasks. The strategy will follow the phases defined by the user:

1.  **Phase 1 (Foundation & Test Scaffolding)**: Create tasks for the types, dataclasses, service stubs, adapter skeletons, and initial `xfail` tests.
2.  **Phase 2 (RateCardAdapter v1)**: Create tasks for the HTML parser, `collect` logic, and implementing rules to make AC1, AC2, and AC3 pass.
3.  **Phase 3 (SpotAdapter v1)**: Create tasks for handling the UI input contract, the `collect` logic, and tests for AC4.
4.  **Phase 4 (Integration & Guardrails)**: Create tasks for the API wiring, feature flags, circuit breaker, snapshot generation, and RBAC enforcement.
5.  **Phase 5 (Testing & Coverage)**: Create tasks for writing the final unit, service, and API tests to meet coverage gates.

**Ordering Strategy**:
- TDD order: Tests will be created before the implementation that makes them pass.
- Dependency order: Foundational types and dataclasses will be created first.
- Tasks will be marked `[P]` for parallel execution where possible (e.g., creating independent files).

## Progress Tracking
*This checklist is updated during execution flow*

**Phase Status**:
- [x] Phase 0: Research complete (/plan command)
- [x] Phase 1: Design complete (/plan command)
- [x] Phase 2: Task planning complete (/plan command - describe approach only)
- [ ] Phase 3: Tasks generated (/tasks command)
- [ ] Phase 4: Implementation complete
- [ ] Phase 5: Validation passed

**Gate Status**:
- [x] Initial Constitution Check: PASS
- [x] Post-Design Constitution Check: PASS
- [x] All NEEDS CLARIFICATION resolved
- [ ] Complexity deviations documented

---
*Based on Constitution v3.1.0 - See `/.specify/memory/constitution.md`*
