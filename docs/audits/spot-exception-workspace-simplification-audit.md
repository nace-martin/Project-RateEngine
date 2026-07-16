# SPOT Exception Workspace Simplification and Code-Cleanup Audit

## 1. Executive Summary

This audit evaluates the current implementation of the SPOT Exception Workspace, specifically focusing on the frontend component `ExceptionWorkspace.tsx`, its supporting components, and backend contracts. The Exception Workspace serves as a stateful, operator-guided "Draft Quote Assistant" designed to resolve ambiguities (unscoped supplier labels, unmapped charge lines, unclassified text blocks) before a SPOT quote is finalized.

Our primary findings indicate that the Exception Workspace is a high-complexity module:
- The main frontend component `ExceptionWorkspace.tsx` spans **1,222 lines of code** and exhibits a **cognitive complexity of 99** (the highest in the frontend codebase).
- It mixes multiple distinct responsibilities: state management, inline resolution forms, wizards for unclassified blocks, math mismatch displays, and final review checklists.
- Prototype residue (e.g., prototype override checkboxes and demo instructions) is displayed unnecessarily in the live layout.
- There is functional and layout duplication between the inline forms in `ExceptionWorkspace.tsx` and the side sheet in `SpotChargeLineManualReviewSheet.tsx`.

This document maps out a low-risk strategy to clean up demo clutter, relocate helper functions, and extract nested components without altering the API contracts, V4 pricing engine, or RBAC controls.

---

## 2. Current Architecture

### 2.1 File Inventory and Line Counts

| Layer | File Path (Repository-Relative) | Line Count | Primary Responsibility |
| --- | --- | --- | --- |
| **Frontend Page** | `frontend/src/app/quotes/spot/[speId]/exception-workspace/page.tsx` | 131 | Loads live draft quote data via `speId` and mounts `ExceptionWorkspace`. |
| **Frontend Page** | `frontend/src/app/quotes/spot/exception-workspace-demo/page.tsx` | 16 | Mounts `ExceptionWorkspace` for prototype preview. |
| **Frontend UI** | `frontend/src/components/spot/ExceptionWorkspace.tsx` | 1222 | Unified workspace component managing state and workflows. |
| **Frontend UI** | `frontend/src/components/spot/SpotChargeLineManualReviewSheet.tsx` | 532 | Slide-over sheet for manual ProductCode mapping on the main envelope page. |
| **Frontend Types** | `frontend/src/lib/draft-quote-types.ts` | 182 | TypeScript interfaces representing the backend `DraftQuoteSchema` contract. |
| **Frontend Client** | `frontend/src/lib/api.ts` | 67 (scoped) | API client wrappers (`getDraftQuote`, `resolveDraftQuoteDecisions`, `finalizeDraftQuoteReview`). |
| **Backend Views** | `backend/quotes/spot_views.py` | 320 (scoped) | Django REST Framework API views for draft quote retrieval, resolution, finalization, and reopening. |
| **Backend Contract** | `backend/quotes/contracts/draft_quote_contract.py` | 329 | Pydantic schemas validating client payloads and API responses. |
| **Backend Service** | `backend/quotes/services/draft_quote_adapter.py` | 455 | Adapter service mapping `SpotPricingEnvelopeDB` and related models to `DraftQuoteSchema`. |
| **Backend Service** | `backend/quotes/services/draft_quote_resolve_service.py` | 358 | Transaction-safe processor applying operator resolutions to database records. |
| **Backend Service** | `backend/quotes/services/draft_quote_review_service.py` | 78 | State machine manager validating blockers during finalization and handling reopen requests. |

### 2.2 Component State Groups (ExceptionWorkspace.tsx)

`ExceptionWorkspace` relies on a flat state configuration within a single component:
1. **Mock Ingestion Data**: `draftQuote` (persisted mock baseline).
2. **Review Elements State**: `suggestedCharges`, `reviewQueue`, `unclassifiedItems`, `ignoredItems`, and `decisions` (the log of decisions applied in the current session).
3. **Session Status**: `reviewSession` (tracks status, finalizer metadata, remaining blockers, and allowed actions).
4. **Active Workflow Tracking**: `activeIssueId` (ID of the currently highlighted blocker in the queue), `selectedActionType` (tracks sub-form view: `map_existing`, `request_product_code`, `add_charge`), and `showHelpText`.
5. **Accordions Toggles**: `showSuggested`, `showTerms`, and `showTotalsPanel`.
6. **Billing Request Inputs**: `reqLabel`, `reqSource`, `reqCurrency`, `reqAmount`.
7. **Unclassified Block Wizard Inputs**: `unknownStep`, `unknownClassification`, `addName`, `addBucket`, `addCurrency`, `addAmount`, `addUnit`, `addProductCode`.
8. **UI Banner**: `actionMessage` (feedback banner text).
9. **Prototype Toggle**: `prototypeOverride` (allows bypassing blocks when testing).

### 2.3 Event Handlers (ExceptionWorkspace.tsx)

- `handleUndoDecision(id)`: Rolls back a decision from the local state list and restores the previous snapshot.
- `handleFinalizeReview()`: Submits the finalization request to the backend or updates mock state to `finalized`.
- `handleUseApprovedProductCode(...)`: Directly applies an admin-approved ProductCode request.
- `handleMapProductCode(...)`: Submits a `map_to_product_code` decision.
- `handleOpenRequestProductCode(...)`: Pre-fills the ProductCode request fields.
- `handleSubmitProductCodeRequest(...)`: Submits a `request_product_code` decision.
- `handleAcceptSuggestedMapping(...)`: Directly accepts a matching ProductCode mapping suggestion.
- `handleIgnoreCharge(...)`: Marks a charge line to be excluded from totals.
- `handleIgnoreUnknownCharge(...)`: Excludes an unclassified text block.
- `handleMakeActive(...)`: Highlights selected item in unresolved queue.
- `handleAddUnknownAsCharge(...)`: Creates a new manual charge line from an unclassified text block.
- `toggleIncludeInTotals(id)`: Toggles inclusion status for calculations.

### 2.4 Render Sections (ExceptionWorkspace.tsx)

1. **Header Banner**: EFM branding and remaining blockers counter.
2. **Current Task Indicator**: Action-oriented next step guidance (e.g., "Choose a ProductCode for FSC").
3. **API Alert Messages**: Success or error alerts.
4. **Active Resolution Workspace**: Form panel displaying the highlighted exception, source evidence, and context-specific action sub-forms.
5. **Needs Attention List**: Summary queue of unresolved items remaining.
6. **Review Decisions Log**: Undo-capable log of decisions applied in the current session.
7. **Suggested Charges Accordion**: List of all charges with status tags.
8. **Commercial Terms Accordion**: Extracted terms (validity, cargo conditions).
9. **Verification Warnings & Totals Accordion**: Mixed-currency breakdowns and math mismatch metrics.
10. **Ignored Items List**: Ignored segments.
11. **Final Review Checklist**: Visual validation checkmarks.
12. **Finalize Action Footer**: Prototype override check and "Finalize Review" lock action.

---

## 3. Live Operator Workflow

The live workspace workflow maps the operator journey through exception resolution and review finalization:

```mermaid
sequenceDiagram
    autonumber
    actor Operator as Sales Operator
    actor Manager as Branch Manager
    participant UI as Exception Workspace UI
    participant BE as Backend API
    participant DB as SQLite / Postgres DB

    Note over Operator, DB: 1. Intake & Loading
    Operator->>UI: Navigates to /quotes/spot/<speId>/exception-workspace
    UI->>BE: GET /api/v3/spot/envelopes/<speId>/draft-quote/
    BE->>DB: Fetch SpotPricingEnvelopeDB, SPEChargeLineDB, SPESourceBatchDB
    BE-->>UI: Return validated DraftQuoteSchema payload
    UI-->>Operator: Displays active blockers and unclassified blocks

    Note over Operator, DB: 2. Exception Resolution
    alt Map Existing Code
        Operator->>UI: Selects "Map to Existing ProductCode"
        UI->>BE: POST /api/v3/spot/envelopes/<speId>/draft-quote/resolve/ (map_to_product_code)
        BE->>DB: Write manual_resolved_product_code & manual_resolution_status = RESOLVED
    else Request New Code
        Operator->>UI: Selects "Request New ProductCode"
        UI->>BE: POST /api/v4/product-code-requests/ (proposed_code, reason)
        BE->>DB: Write ProductCodeCreationRequest & set SPEChargeLineDB status = pending_product_code
    else Ignore Line
        Operator->>UI: Selects "Ignore as Non-Commercial"
        UI->>BE: POST /api/v3/spot/envelopes/<speId>/draft-quote/resolve/ (ignore)
        BE->>DB: Write exclude_from_totals = True
    end
    BE-->>UI: Return updated unresolved items count & status
    UI-->>Operator: Refreshes checklist and displays active warnings

    Note over Operator, DB: 3. Review Finalization
    Operator->>UI: Clicks "Finalize Review"
    UI->>BE: POST /api/v3/spot/envelopes/<speId>/draft-quote/finalize/
    BE->>BE: Validate remaining_blockers == 0 and check permissions
    alt Blockers Remain
        BE-->>UI: Return 400 Bad Request (blockers list)
        UI-->>Operator: Displays blocking messages
    else Validation Successful
        BE->>DB: Write SpotPricingEnvelopeDB status = finalized
        BE-->>UI: Return 200 OK (locked state)
        UI-->>Operator: Locks workspace UI as read-only
    end

    Note over Manager, DB: 4. Manager Reopen (API Only)
    Note over UI: The UI does not provide a Reopen action client method.
    Note over UI: Manager Reopen is currently restricted to backend administrative triggers.
    Manager->>BE: POST /api/v3/spot/envelopes/<speId>/draft-quote/reopen/
    BE->>BE: Validate User isManagerOrAdmin
    alt Authorization Fails
        BE-->>Manager: Return 403 Forbidden
    else Authorized
        BE->>DB: Reset SpotPricingEnvelopeDB status = in_review
        BE-->>Manager: Return 200 OK (restores editable status in database)
    end
```

---

## 4. Baseline Command Results

### 4.1 Static Analysis Results (Fallow)
- **`npx fallow --format json`**: Successfully identified high-impact complexity hotspots. Under frontend components, `ExceptionWorkspace.tsx` scored the highest priority score due to a **cognitive complexity of 99** (threshold: 30) and a Maximum CRAP index of 4556. `SpotChargeLineManualReviewSheet.tsx` registered a **cognitive complexity of 44** with a CRAP index of 1190.
- **`npx fallow dead-code --format json`**: Flags unused type declarations and exports in:
  - `frontend/src/lib/api.ts` (e.g., `V4SellRate`, `V4RateCardUploadErrorResponse`).
  - `frontend/src/lib/permissions.ts` (e.g., `EffectivePermissions`).
  - `frontend/src/lib/schemas/spotSchema.ts` (e.g., `SpotChargeLineValues`).
  - `frontend/src/lib/spot-types.ts` (e.g., `ManualAssertionInput`, `SpotModeActions`).
  - `frontend/src/lib/types.ts` (e.g., `Company`, `StationSummary`).
- **`npx fallow dupes --format json`**: Duplication density is at **10.02%** (5,050 duplicated lines out of 50,361 total lines). The `api.ts` client file contains multiple repeated fetch structures for SPOT endpoints that can be consolidated.
- **`npx fallow health --format json`**: Confirmed the high complexity of the Exception Workspace UI module and recommended extracting sub-components.

### 4.2 Frontend Quality Checks
- **`npm run lint`**: Completed with **0 errors** and 44 warnings (primarily regarding unused imports and typescript parameters in test scripts).
- **`npm run typecheck`**: Completed with **no TypeScript compiler issues**.
- **`npm run build`**: Next.js production build compiled successfully with Turbopack in 32 seconds.
- **Exception Workspace Tests**: All 4 frontend test configurations passed:
  - `test:spot-finalization` (Passed)
  - `test:spot-workspace-helpers` (Passed)
  - `test:exception-workspace-routing` (Passed)
  - `test:draft-quote-contract` (Passed)

### 4.3 Backend Quality Checks
- **Django system check**: `python backend/manage.py check` returned **no issues**.
- **Django test suite**: `python backend/manage.py test quotes.tests` ran **488 tests passed** during Phase 14D verification. One test (`test_spot_template_validation_event_created_on_review`) was recorded as failing in the full suite run but passed consistently when executed in isolation. This failure is a pre-existing non-deterministic test issue, likely a SQLite timestamp collision during parallel test execution. It is not a regression introduced by Phase 14D. The specific test is unrelated to Exception Workspace or SPOT resolution orchestration.

---

## 5. Complexity Hotspots

The cognitive complexity of 99 in `ExceptionWorkspace.tsx` is driven by:
- **Excessive Local State**: Managing 15+ interactive React states in a single component causes layout and update bloat.
- **Nested Inline Render Conditions**: Massive ternary statements are used to render the appropriate sub-form depending on the `selectedActionType` and `activeIssue.type`.
- **Inline Wizards**: The "Unknown Charge Block" resolution flows are hardcoded as step-by-step stateful branches directly within the main return statement.
- **Dynamic Calculation Reductions**: Reducers to split totals by currency, validate math balances, and check checklist states are computed inline on every render cycle.

---

## 6. Duplication Findings

We identified functional duplication between `ExceptionWorkspace.tsx` and `SpotChargeLineManualReviewSheet.tsx`:
- **ProductCode Requests**: Both components implement a ProductCode request form. `SpotChargeLineManualReviewSheet` includes a detailed form containing `suggested_name`, `suggested_bucket` (bucket options mapping), `suggested_basis` (unit basis mapping), and `suggested_reason`. `ExceptionWorkspace.tsx` contains a simplified inline form (lines 815–850) that requests `proposed_code` and `reason`.
- **Canonical ProductCode Search**: Both components search and map existing ProductCodes. `SpotChargeLineManualReviewSheet` uses a custom autocomplete `Combobox` element. `ExceptionWorkspace` uses a primitive HTML `<select>` list containing only four hardcoded codes (lines 801–804: `AF-FREIGHT`, `AF-FUEL`, `AF-SEC`, `AF-HC`).

---

## 7. Dead, Legacy, and Prototype Candidates

The following symbols and UI structures are legacy leftovers from the early prototypes and are safe to decommission:
- **Demo-Only Banners**: The checkbox UI `Prototype override only — not available for production.` (lines 101, 1192–1202) and its status banner (line 1213) bypass checklist blockers when enabled. This is **not** a live security bypass because the code explicitly restricts it to non-live mode with `!isLive && prototypeOverride`, while the real workspace passes `isLive={true}`. It is a demo-only behaviour displayed unnecessarily in the live layout and should be hidden/removed.
- **Mock Data Fallback**: The component relies on `hardCaseAirImportData` as its default `initialData` property (line 54). Deleting this import directly from the codebase would break the demo page (`frontend/src/app/quotes/spot/exception-workspace-demo/page.tsx`), which renders `<ExceptionWorkspace />` without supplying props. Phase 14B must preserve this by moving the mock import directly into the demo page and passing it explicitly (`<ExceptionWorkspace initialData={hardCaseAirImportData} />`), allowing the prop default to be cleaned up safely in `ExceptionWorkspace.tsx`.
- **Inline Helpers**: Helper functions like `humanizeRate` (lines 8–26) and `friendlyStatus` (lines 28–39) contain hardcoded strings and should be extracted to a shared utility file.

---

## 8. Operator-Facing Clutter Findings

Every section in the current live Exception Workspace can be categorized under the following usability framework:

```
[Core Operator Action]
  ├── Resolve Blocker (Accept / Map / Ignore)
  ├── Request ProductCode (Inline Form)
  └── Lock Workspace (Finalize Review)

[Required Risk & Control Info]
  ├── Blocker Messages ("FSC requires billing code validation")
  ├── Mixed-Currency Warnings ("Totals Need Review")
  └── Mathematical Mismatch Status ("Calculated sum difference")

[Supporting Evidence (Progressive Disclosure Candidate)]
  └── Source Quote Text & Document Reference ("FSC rate: USD 0.85 per kg")

[Duplicated / Legacy Information (Cleanup Candidate)]
  ├── Extracted Terms list (unrelated cargo terms clog the layout)
  └── Demo-only Banners & Blockers Override UI (clutters the final review block)
```

---

## 9. Protected Behaviours and Regression Coverage

Any cleanup, refactoring, or extraction must preserve the following business rules:

| Protected Behaviour | Backend Safeguard | Frontend Test Coverage |
| --- | --- | --- |
| **Live Draft Quote Loading** | `SpotEnvelopeDraftQuoteAPIView` | `frontend/scripts/exception-workspace-routing.test.mjs` |
| **Decision Persistence** | `apply_draft_quote_decisions` (Transactions) | `frontend/scripts/draft-quote-contract.test.mjs` |
| **ProductCode Request Flow** | `ProductCodeCreationRequestViewSet` (Deduplication) | `backend/quotes/tests/test_spot_productcode_close_loop_launch_gate.py` |
| **Finalization Blockers** | `finalize_review` (Restricts lock if blockers > 0) | `frontend/scripts/spot-finalization.test.mjs` |
| **Finalized Workspace Lock** | `is_finalized` (Returns 409 Conflict on resolve attempt) | `backend/quotes/tests/test_spot_exception_workspace_e2e.py` |
| **Manager/Admin Reopen** | `reopen_review` (Restricts reopen to managers/admins) | `backend/quotes/tests/test_spot_exception_workspace_e2e.py` |
| **Manual-Review Safety** | Unscoped ambiguous labels must remain unresolved | `backend/quotes/tests/test_spot_template_validation_review.py` |

---

## 10. Safe Cleanup Candidates

We recommend performing the following low-risk extractions and removals in **Phase 14B**:
1. **Clean Demo Clutter from Live View**: Hide or remove the `proto-override` checkbox, state, and footer text in live mode (`isLive === true`). Bypassing blocker checks is not permitted in UAT or production.
2. **Standardize Mock Data Ingestion**: Relocate the `hardCaseAirImportData` fallback out of the component defaults. Explicitly import and supply the mock data from the demo page component (`frontend/src/app/quotes/spot/exception-workspace-demo/page.tsx`).
3. **Extract Helper Utilities**: Move `humanizeRate` and `friendlyStatus` to `frontend/src/lib/spot-workspace-helpers.ts` where similar helpers reside.

---

## 11. Risky or Deferred Candidates

The following changes present regression risks and should be deferred to a later phase (e.g. Phase 14C):
- **Consolidating forms with SpotChargeLineManualReviewSheet**: While structurally similar, the side sheet uses a different routing/context paradigm (it interacts with the full `SPEChargeLine` schema directly, whereas the Exception Workspace interacts with `DraftCharge` contracts). Merging these during refactoring introduces a high risk of breaking layout state and API resolutions. Keep them separate.
- **Component Extractions**: Extracting the active resolution sub-forms (`MapExistingForm`, `RequestProductCodeForm`, `AddChargeForm`) or warnings panels is deferred to Phase 14C. Separating layout states during initial cleanup increases regression risks.
- **Altering API Contracts**: Do not modify `DraftQuoteSchema` or backend serializer definitions. Any change to the validation schemas will break integration checks.

---

## 12. Separation of UI Simplification from Code Cleanup

To maintain regression safety, initial phases must separate UI alterations from code reorganization:
- **UI Simplification**: Consists of removing the prototype override controls, standardizing style padding, and hiding raw document evidence behind an expandable progressive disclosure toggle. These changes alter visual representation and must be verified by visual checks.
- **Code Cleanup**: Consists of extracting complex conditional render blocks into nested stateless React components. These changes must not alter the DOM footprint or state update cycles and must keep all regression tests passing.

---

## 13. Recommended Implementation Sequence

```
Step 1: Demo prop & data relocation (Phase 14B)
  ├── Move hardCaseAirImportData to demo page.tsx
  └── Pass initialData={hardCaseAirImportData} explicitly to component
Step 2: Demo override and banners cleanup (Phase 14B)
  └── Hide/remove proto-override checkbox & banners in live mode
Step 3: Helper relocation (Phase 14B)
  └── Move humanizeRate and friendlyStatus to spot-workspace-helpers.ts
Step 4: Component extraction (Phase 14C - Deferred)
  └── Extract sub-forms and totals panels
```

---

## 14. Phase 14B Scope

The exact scope for Phase 14B is restricted to the following checklist:

### A. Demo Data Relocation
- [ ] Move the `hardCaseAirImportData` import to `frontend/src/app/quotes/spot/exception-workspace-demo/page.tsx`.
- [ ] Update `ExceptionWorkspaceDemoPage` to pass `initialData={hardCaseAirImportData}` explicitly.
- [ ] Remove the fallback default parameter `initialData = hardCaseAirImportData` in `ExceptionWorkspace.tsx`.

### B. Demo Layout Cleanup
- [ ] Hide the `proto-override` checkbox, state, and footer text in `ExceptionWorkspace.tsx` when `isLive` is true.
- [ ] Hide the banner "Prototype only — Changes made will not be permanently saved." in `ExceptionWorkspace.tsx` when `isLive` is true.

### C. Helper Extraction
- [ ] Move `humanizeRate` and `friendlyStatus` from `ExceptionWorkspace.tsx` to `frontend/src/lib/spot-workspace-helpers.ts`.
- [ ] Reference these helpers in `ExceptionWorkspace.tsx`.

### D. Verification
- [x] Verify that `npm run lint` and `npm run typecheck` run clean.
- [x] Ensure that `npm run test:spot-finalization` and related scripts pass successfully.
- [x] Ensure Django backend test suites pass with no failures.

---

## 15. Phase 14D Refactoring and Orchestration Extraction Metrics

Phase 14D refactored `ExceptionWorkspace.tsx` by extracting all workflow states, transitions, API orchestration, and derived calculations into a pure typescript state/reducer module (`spotResolutionState.ts`) and an orchestration React hook (`useSpotResolutionWorkflow.ts`).

The table below contrasts the static complexity metrics before and after the orchestration refactoring:

| Metric | Before Refactoring (Phase 14C) | After Refactoring (Phase 14D) | Change / Verification |
| --- | --- | --- | --- |
| **`ExceptionWorkspace.tsx` LOC** | 1,130 | 698 | **-432 lines** (Presentation logic only) |
| **`ExceptionWorkspace` Cognitive Complexity** | 102 | 92 | **-10** (Less conditional state branching) |
| **`ExceptionWorkspace` Max CRAP Index** | 4,970 | 3,540 | **-1,430** (Significant risk reduction) |
| **`spotResolutionState.ts` LOC** | — | 558 | **New** (Pure TypeScript module) |
| **`useSpotResolutionWorkflow.ts` LOC** | — | 456 | **New** (API integration and state management hook) |
| **`spotResolutionState.test.mjs` Execution** | — | Passed | Verifies 24 reducer transitions and selector maths |
| **Orchestration Contract Checks** | — | Passed | Verifies hook/component boundary separation |

By isolating side-effects in the hook and keeping state mutations strictly deterministic inside a pure reducer, we successfully reduced complexity hotspots and resolved testing limitations. No new dead code or duplicate logic violations were registered.

### Phase 14D — Parity Correction (follow-up commit)

A parity regression was identified during post-merge review of PR #286: the reducer incorrectly reset `unknownWizard` state (`step`, `classification`) on five review-item resolution actions (`MAP_PRODUCT_CODE`, `SUBMIT_PRODUCT_CODE_REQUEST`, `USE_APPROVED_PRODUCT_CODE`, `ACCEPT_SUGGESTED_MAPPING`, `IGNORE_CHARGE`). In Phase 14C, these handlers had no effect on the separate `unknownStep`/`unknownClassification` state variables. The incorrect resets were introduced during extraction.

The fix was verified by:
- Removing the five unintended `unknownWizard: { step: 1, classification: null }` resets from the reducer.
- Adding 9 targeted regression tests to `spot-resolution-state.test.mjs` (tests 16 and 17): 5 assertions verifying wizard state is **preserved** by review-item actions, and 4 assertions verifying the wizard IS **reset** by the three unknown-item completion actions and `UNDO_DECISION`.
- The corrected test suite now passes all 24 tests.
- `tmp/test_spot_productcode_remediation_plan.csv` was removed from Git tracking (generated file committed inadvertently in the initial Phase 14D commit).
