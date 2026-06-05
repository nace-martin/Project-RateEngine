# Audit Report: Legacy "Incomplete" Quote Status

## Executive Summary
This audit analyzes the usage and role of the `INCOMPLETE` status in the RateEngine codebase. While labeled as "legacy" in the audit request, the `INCOMPLETE` status is currently **actively integrated** into both the V4 deterministic pricing engine and the frontend SPOT/manual review workflow. It is triggered when required rates are missing for a given route/scope/payment term. 

As a result, removing or refactoring it requires a coordinated backend and frontend migration rather than a simple code cleanup.

---

## 1. Where `Incomplete` is Defined

### Backend Code
1. **Model Definition**: Defined as a status choice on the `Quote` model:
   - File: [models.py](file:///c:/Users/commercial.manager/dev/Project-RateEngine/backend/quotes/models.py#L40)
     ```python
     class Status(models.TextChoices):
         ...
         INCOMPLETE = 'INCOMPLETE', _('Incomplete (Missing Data)')
     ```
2. **Migrations**: Persisted in the database schema:
   - File: [0001_initial.py](file:///c:/Users/commercial.manager/dev/Project-RateEngine/backend/quotes/migrations/0001_initial.py#L27)
   - File: [0008_quote_lifecycle_timestamps.py](file:///c:/Users/commercial.manager/dev/Project-RateEngine/backend/quotes/migrations/0008_quote_lifecycle_timestamps.py#L39)
3. **State Machine**: Regulated via state transition matrices and metadata helpers:
   - File: [state_machine.py](file:///c:/Users/commercial.manager/dev/Project-RateEngine/backend/quotes/state_machine.py#L27):
     ```python
     VALID_TRANSITIONS = {
         ...
         Quote.Status.INCOMPLETE: [Quote.Status.DRAFT],  # Must complete before finalizing
     }
     ```
   - Also listed in `ACTIVE_STATES` (mutable workflow states) and mapped in `get_status_display_info()`.

### Frontend Code
1. **Status Mapping**: Included in the frontend configuration for badges and dialog actions:
   - File: [QuoteStatusBadge.tsx](file:///c:/Users/commercial.manager/dev/Project-RateEngine/frontend/src/components/QuoteStatusBadge.tsx#L36-L41):
     ```typescript
     INCOMPLETE: {
         label: "Incomplete",
         bgColor: "bg-red-50",
         textColor: "text-red-700",
         borderColor: "border-red-200",
     }
     ```
2. **Helpers**: Parsed within quote utility functions:
   - File: `frontend/src/lib/quote-helpers.ts` (e.g. `getEffectiveQuoteStatus`).

---

## 2. Where it is Displayed

### Frontend UI
1. **Quote Status Badges**: Displayed as a red badge labeled "Incomplete" on quote list items and details headers.
2. **Quote Details Page**: 
   - File: [page.tsx](file:///c:/Users/commercial.manager/dev/Project-RateEngine/frontend/src/app/quotes/%5Bid%5D/page.tsx#L241-L290)
   - Renders custom action/warnings cards depending on the status of a live SPOT trigger check:
     - `SpotWorkflowRequiredCard`: Urging the user to open the SPOT workflow.
     - `IncompleteQuoteCard`: Directing the user to return to the editor to supply missing pricing parameters.
3. **Quote Action Panel**: In `QuoteStatusBadge.tsx`, incomplete quotes display the helper text `"Complete all required rates to finalize"`, blocking the finalize button.

### PDF & Customer Output
1. **Watermark Engine**: Prints draft watermarks for incomplete quotes:
   - File: [pdf_service.py](file:///c:/Users/commercial.manager/dev/Project-RateEngine/backend/quotes/pdf_service.py#L158):
     ```python
     show_watermark = quote.status in ['DRAFT', 'INCOMPLETE']
     ```
2. **Finalization Guard**: Blocks downloading finalized customer quotes unless the status is transitioned out of `INCOMPLETE` / `DRAFT`.

---

## 3. What Triggers it

`INCOMPLETE` status is dynamically triggered when a quote is computed but contains missing rates:
1. **Pricing Dispatcher Flow**:
   - File: [calculation.py](file:///c:/Users/commercial.manager/dev/Project-RateEngine/backend/quotes/views/calculation.py#L256-L260):
     ```python
     has_missing_rates = calculated_charges.totals.has_missing_rates
     quote_status = (
         Quote.Status.INCOMPLETE if has_missing_rates else Quote.Status.DRAFT
     )
     ```
2. **Rate Missing Rule**: The pricing engines (Domestic, Export, etc.) emit `is_rate_missing=True` when a required COGS/Sell line cannot be matched.

---

## 4. Whether it is Still Used by Active Quote Flow

**Yes, it is actively used.**
- Under `AGENTS.md` rules: "DOMESTIC FREIGHT MUST emit `is_rate_missing=True` if no COGS/Sell row is found...". 
- These missing-rate signals trigger the backend to label quotes as `INCOMPLETE`.
- The frontend relies on this status to fork users between the normal **Quote Detail** screen and the **SPOT/Live Negotiation** workflow.

---

## 5. Whether it Conflicts with SPOT/Manual Review

It does **not** conflict; it is the **gatekeeper** to the SPOT workflow:
1. If a quote is `INCOMPLETE` and has an associated spot envelope, the frontend automatically redirects the user to the SPOT interface.
2. If no spot envelope is present, the frontend evaluates whether the missing rate codes qualify for a SPOT trigger:
   - If yes: User is prompted to launch the SPOT workflow.
   - If no: User is requested to return to standard manual edit to resolve rate gaps.

---

## 6. Whether it is Dead/Legacy Code

**No, this is active core logic.** It cannot be deleted immediately because both backend calculations and frontend routing logic depend on this state.

---

## 7. Safe Removal Plan (If Deprecation is Desired)

If the product design requires consolidating all non-finalized states under `DRAFT`, follow this phased transition plan to avoid outages:

### Phase 1: Backend Storage Migration
1. Maintain `has_missing_rates` (boolean) on the database model (`Quote` and `QuoteVersion`/`QuoteTotal`).
2. Update the compute views to set `status = Quote.Status.DRAFT` instead of `INCOMPLETE`.
3. Create a database migration to update existing `INCOMPLETE` quotes to `DRAFT`.

### Phase 2: Serialization Backward Compatibility
1. Update API serializers to dynamically populate `status = "INCOMPLETE"` in JSON payloads when `status == "DRAFT"` AND `has_missing_rates == True`.
2. This protects the frontend from breaking while code adjustments are made.

### Phase 3: Frontend Refactoring
1. Search and replace frontend references to status `"INCOMPLETE"` to look up `has_missing_rates === true` on draft quotes:
   - e.g., `const isIncomplete = effectiveStatus === "DRAFT" && quote.latest_version?.totals?.has_missing_rates;`
2. Once the frontend is fully updated, release and verify.

### Phase 4: Backend Cleanup
1. Remove `Quote.Status.INCOMPLETE` from the choices enum and state transition schemas.
2. Clean up migration choices.

---

## 8. Tests Required Before Removal

If removal is executed, tests must be updated/added for:
1. **Completeness Unit Tests**:
   - Verify `evaluate_from_lines` behavior under `backend/quotes/tests/test_completeness.py`.
2. **Lifecycle Transitions**:
   - Verify transitions in `backend/quotes/tests/test_api_v3.py` (specifically tests referencing status `Quote.Status.INCOMPLETE`).
3. **Watermark / PDF Generation**:
   - Confirm draft watermarks are triggered correctly based on `has_missing_rates` instead of checking the status value.
4. **CRM Sync**:
   - Ensure CRM opportunity interactions are correctly mapped to quotes with missing rates.
