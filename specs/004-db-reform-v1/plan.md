# Implementation Plan: DB Reform v1

**Branch**: `004-db-reform-v1` | **Date**: Tuesday 23 September 2025 | **Spec**: specs/004-db-reform-v1/spec.md
**Input**: Feature specification from `/specs/004-db-reform-v1/spec.md`

## Execution Flow (/plan command scope)
```
1. Load feature spec from Input path
   → If not found: ERROR "No feature spec at {path}"
2. Fill Technical Context (scan for NEEDS CLARIFICATION)
   → Detect Project Type from context (web=frontend+backend, mobile=app+api)
   → Set Structure Decision based on project type
3. Fill the Constitution Check section based on the content of the constitution document.
4. Evaluate Constitution Check section below
   → If violations exist: Document in Complexity Tracking
   → If no justification possible: ERROR "Simplify approach first"
   → Update Progress Tracking: Initial Constitution Check
5. Execute Phase 0 → research.md
   → If NEEDS CLARIFICATION remain: ERROR "Resolve unknowns"
6. Execute Phase 1 → contracts, data-model.md, quickstart.md, agent-specific template file (e.g., `CLAUDE.md` for Claude Code, `.github/copilot-instructions.md` for GitHub Copilot, `GEMINI.md` for Gemini CLI, `QWEN.md` for Qwen Code or `AGENTS.md` for opencode).
7. Re-evaluate Constitution Check section
   → If new violations: Refactor design, return to Phase 1
   → Update Progress Tracking: Post-Design Constitution Check
8. Plan Phase 2 → Describe task generation approach (DO NOT create tasks.md)
9. STOP - Ready for /tasks command
```

**IMPORTANT**: The /plan command STOPS at step 7. Phases 2-4 are executed by other commands:
- Phase 2: /tasks command creates tasks.md
- Phase 3-4: Implementation execution (manual or via tools)

## Summary
This feature aims to enhance data integrity, consistency, and performance within the pricing and quoting modules by introducing stricter database constraints, standardizing data precision, and optimizing JSON queries. It focuses on preventing invalid data entries, ensuring deterministic pricing, and improving system resilience without disrupting existing data.

## Technical Context
**Language/Version**: Python (Django), PostgreSQL
**Primary Dependencies**: Django, Django REST Framework
**Storage**: PostgreSQL
**Testing**: pytest
**Target Platform**: Linux server
**Project Type**: Web application
**Performance Goals**: Speed up JSON filters [NEEDS CLARIFICATION: specific performance targets for JSON queries?]
**Constraints**: Without breaking current data, idempotent migrations, no 500s on missing BUY.
**Scale/Scope**: Lock down core enums (currencies/units/audience), prevent overlapping ratecards & ladders, add quote fail-safe flags, standardize money precision, speed up JSON filters.

## Constitution Check
*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Principle: Test-First (NON-NEGOTIABLE)**: The plan includes writing DB integrity tests and API tests before implementation, aligning with the TDD principle.
- **Principle: Observability**: The plan includes adding structured logging for incomplete quotes and Grafana/SQL counts, aligning with observability requirements.
- **Principle: Simplicity**: The plan aims to simplify data models by replacing magic strings with FKs and standardizing precision.
- **Principle: Integration Testing**: The plan includes API tests for quotes with missing BUY, which will involve integration testing.

## Project Structure

### Documentation (this feature)
```
specs/[###-feature]/
├── plan.md              # This file (/plan command output)
├── research.md          # Phase 0 output (/plan command)
├── data-model.md        # Phase 1 output (/plan command)
├── quickstart.md        # Phase 1 output (/plan command)
├── contracts/           # Phase 1 output (/plan command)
└── tasks.md             # Phase 2 output (/tasks command - NOT created by /plan)
```

### Source Code (repository root)
```
backend/
├── src/
│   ├── models/
│   ├── services/
│   └── api/
└── tests/

frontend/
├── src/
│   ├── components/
│   ├── pages/
│   └── services/
└── tests/
```

**Structure Decision**: Option 2: Web application

## Phase 0: Outline & Research
1. **Extract unknowns from Technical Context** above:
   - [NEEDS CLARIFICATION: specific performance targets for JSON queries?]
   - [NEEDS CLARIFICATION: Should a ratecard with an `expiry_date` earlier than its `effective_date` be prevented by the system or handled by business logic?]
   - [NEEDS CLARIFICATION: What is the expected behavior for existing invalid data (e.g., overlapping ratecards) during migration?]

2. **Generate and dispatch research agents**:
   - Task: "Research specific performance targets for JSON queries in PostgreSQL for the pricing and quoting modules."
   - Task: "Research best practices for handling invalid date ranges (e.g., expiry_date < effective_date) in Django models or database constraints."
   - Task: "Research strategies for handling existing data that violates new database constraints during migrations in Django/PostgreSQL, considering options like data cleansing, soft deletion, or specific error handling."

3. **Consolidate findings** in `research.md` using format:
   - Decision: [what was chosen]
   - Rationale: [why chosen]
   - Alternatives considered: [what else evaluated]

**Output**: research.md with all NEEDS CLARIFICATION resolved

## Phase 1: Design & Contracts
*Prerequisites: research.md complete*

1. **Extract entities from feature spec** → `data-model.md`:
   - Currencies, Units, Audiences, Ratecards, Cartage Ladders, Storage Tiers, Quotes, Quote Lines, Organizations, Pricing Policy, Ratecard Fees, Service Items, Route Legs, Stations.
   - Define fields, relationships, and validation rules based on the migrations and requirements.

2. **Generate API contracts** from functional requirements:
   - For each user action (e.g., creating/updating ratecards, quotes) → relevant API endpoints.
   - Output OpenAPI/GraphQL schema to `/contracts/` (e.g., for quote creation/update, ratecard management).

3. **Generate contract tests** from contracts:
   - One test file per endpoint (e.g., `test_quotes_api.py`, `test_ratecards_api.py`).
   - Assert request/response schemas and expected error codes for constraint violations.
   - Tests must fail (no implementation yet).

4. **Extract test scenarios** from user stories:
   - Primary User Story: Ensure data integrity and consistency.
   - Acceptance Scenarios:
     - Overlapping ratecard windows blocked.
     - `is_incomplete` flag defaults and settable.
     - Overlapping cartage ladders blocked.
     - Overlapping storage tiers blocked.
     - Quote line precision.
     - Station IATA code validation.
   - Quickstart test = story validation steps.

5. **Update agent file incrementally** (O(1) operation):
   - Run `.specify/scripts/powershell/update-agent-context.ps1 -AgentType gemini` for your AI assistant
   - If exists: Add only NEW tech from current plan
   - Preserve manual additions between markers
   - Update recent changes (keep last 3)
   - Keep under 150 lines for token efficiency
   - Output to repository root

**Output**: data-model.md, /contracts/*, failing tests, quickstart.md, agent-specific file

## Phase 2: Task Planning Approach
*This section describes what the /tasks command will do - DO NOT execute during /plan*

**Task Generation Strategy**:
- Load `.specify/templates/tasks-template.md` as base.
- Generate tasks from Phase 1 design docs (contracts, data model, quickstart).
- Each migration file (0101-0110) will correspond to a set of database migration tasks.
- Each entity in `data-model.md` will lead to model creation/modification tasks.
- Each API contract will lead to API endpoint implementation tasks and contract test tasks.
- Each user story/acceptance scenario will lead to integration test tasks.
- Implementation tasks to make tests pass.

**Ordering Strategy**:
- TDD order: Tests before implementation.
- Dependency order: Database migrations first, then model changes, then service logic, then API endpoints.
- Group migration tasks by "Pack A" and "Pack B" as defined in the feature description.
- Mark [P] for parallel execution (independent files).

**Estimated Output**: 25-30 numbered, ordered tasks in tasks.md

**IMPORTANT**: This phase is executed by the /tasks command, NOT by /plan

## Phase 3+: Future Implementation
*These phases are beyond the scope of the /plan command*

**Phase 3**: Task execution (/tasks command creates tasks.md)
**Phase 4**: Implementation (execute tasks.md following constitutional principles)
**Phase 5**: Validation (run tests, execute quickstart.md, performance validation)

## Complexity Tracking
*Fill ONLY if Constitution Check has violations that must be justified*

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| [e.g., 4th project] | [current need] | [why 3 projects insufficient] |
| [e.g., Repository pattern] | [specific problem] | [why direct DB access insufficient] |


## Progress Tracking
*This checklist is updated during execution flow*

**Phase Status**:
- [ ] Phase 0: Research complete (/plan command)
- [ ] Phase 1: Design complete (/plan command)
- [ ] Phase 2: Task planning complete (/plan command - describe approach only)
- [ ] Phase 3: Tasks generated (/tasks command)
- [ ] Phase 4: Implementation complete
- [ ] Phase 5: Validation passed

**Gate Status**:
- [ ] Initial Constitution Check: PASS
- [ ] Post-Design Constitution Check: PASS
- [ ] All NEEDS CLARIFICATION resolved
- [ ] Complexity deviations documented

---
*Based on Constitution v2.1.1 - See `/memory/constitution.md`*
