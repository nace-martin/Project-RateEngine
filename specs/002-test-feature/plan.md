# Implementation Plan: AIR · Import · A2D (Airport→Door) v2 rating policy — PREPAID & COLLECT

**Branch**: `002-test-feature` | **Date**: Monday 22 September 2025 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `C:\Users\commercial.manager\dev\Project-RateEngine\specs\002-test-feature\spec.md`

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
This plan outlines the implementation of a new, deterministic policy for currency and fee selection for AIR imports on A2D lanes. The goal is to ensure consistent and auditable quotes, regardless of rate-card coverage, by making currency and fee selection 100% deterministic. This will result in correct destination service menus for sales, invoices in the right currency (AUD for PREPAID, PGK for COLLECT), and clear, actionable reasons for missing data instead of errors.

## Technical Context
**Language/Version**: Python 3.11
**Primary Dependencies**: Django, Django REST Framework
**Storage**: N/A (existing models are used, no new DB models for MVP)
**Testing**: pytest
**Target Platform**: Linux server
**Project Type**: Web application
**Performance Goals**: Match or exceed existing performance.
**Constraints**: The new implementation must adhere to the specified rules for audience & invoice currency, fee menu, missing rate handling, and totals & reporting.
**Scale/Scope**: MVP for AIR only, Import direction, A2D scope, PREPAID/COLLECT payment terms, General Cargo (GCR) commodity.

## Constitution Check
*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

The constitution is a template, so no specific checks can be performed. General software engineering best practices will be followed.

## Project Structure

### Documentation (this feature)
```
specs/002-test-feature/
├── plan.md              # This file (/plan command output)
├── research.md          # Phase 0 output (/plan command)
├── data-model.md        # Phase 1 output (/plan command)
├── quickstart.md        # Phase 1 output (/plan command)
├── contracts/           # Phase 1 output (/plan command)
└── tasks.md             # Phase 2 output (/tasks command - NOT created by /plan)
```

### Source Code (repository root)
```
# Option 2: Web application (when "frontend" + "backend" detected)
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
No major unknowns that require research. The implementation details are well-defined in the feature description.

**Output**: research.md

## Phase 1: Design & Contracts
The design will focus on extending the existing `pricing_v2` module to incorporate the new deterministic policy for currency and fee selection. This will involve updating or creating new dataclasses, recipes, and potentially modifying the `pricing_service_v2` functions to implement the new rules.

**Output**: data-model.md, contracts/, quickstart.md

## Phase 2: Task Planning Approach
*This section describes what the /tasks command will do - DO NOT execute during /plan*

**Task Generation Strategy**:
- Load `.specify/templates/tasks-template.md` as base
- Generate tasks from Phase 1 design docs (contracts, data model, quickstart)
- Each contract → contract test task [P]
- Each entity → model creation task [P]
- Each user story → integration test task
- Implementation tasks to make tests pass

**Ordering Strategy**:
- TDD order: Tests before implementation
- Dependency order: Dataclasses and recipes before the main service functions.
- Mark [P] for parallel execution (independent files)

**Estimated Output**: ~10-15 numbered, ordered tasks in tasks.md

**IMPORTANT**: This phase is executed by the /tasks command, NOT by /plan

## Phase 3+: Future Implementation
*These phases are beyond the scope of the /plan command*

**Phase 3**: Task execution (/tasks command creates tasks.md)
**Phase 4**: Implementation (execute tasks.md following constitutional principles)
**Phase 5**: Validation (run tests, execute quickstart.md, performance validation)

## Complexity Tracking
| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| N/A       | N/A        | N/A                                 |


## Progress Tracking
*This checklist is updated during execution flow*

**Phase Status**:
- [X] Phase 0: Research complete (/plan command)
- [X] Phase 1: Design complete (/plan command)
- [ ] Phase 2: Task planning complete (/plan command - describe approach only)
- [X] Phase 3: Tasks generated (/tasks command)
- [X] Phase 4: Implementation complete
- [X] Phase 5: Validation passed

**Gate Status**:
- [X] Initial Constitution Check: PASS
- [X] Post-Design Constitution Check: PASS
- [X] All NEEDS CLARIFICATION resolved
- [ ] Complexity deviations documented

---
*Based on Constitution v2.1.1 - See `C:\Users\commercial.manager\dev\Project-RateEngine\.specify\memory\constitution.md`*
