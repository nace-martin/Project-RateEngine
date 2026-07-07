# Air Freight Pilot Known Limitations

This document lists the scope boundaries, known limitations, and fallback/error recovery behaviors for the initial Air Freight pilot.

## 1. Scope Constraints

1. **Air Freight Only**: The pilot is strictly limited to Air Freight import and export quotes. Sea Freight, Customs-only, and domestic transport-only quotes must continue to use legacy workflows or standard V4 routing.
2. **Entity Restrictions**: Only branches and departments belonging to the `Express Freight Management` organization and EFM operating entities (`EFM PNG`, `EFM Australia`, `EFM Fiji`, `EFM Solomon Islands`) are supported.
3. **No Automatic CRM Sync**: Resolved and finalized spot quotes do not automatically write back to legacy CRM databases. Quote-derived CRM logging must be triggered via explicit user action or manual verification.

## 2. Platform Boundaries

1. **AI Extraction Imperfections**: The AI parser may occasionally fail to classify multi-line tables or complex footnotes. Operators must always use the Exception Workspace to review all "unclassified items" and "needs_review" queues.
2. **Numeric Restrictions**:
   - Charge amount, rate, and minimum charge must be non-negative.
   - Currency must be a valid 3-letter ISO code.
3. **Idempotency Lifetime**: Idempotency keys on resolution (`/resolve/`) and finalization (`/finalize/`) prevent duplicate submissions but are unique to each operator session. If a session is refreshed or opened in multiple tabs, verify the latest state before resolving.

## 3. Error Recovery and Support Fallbacks

1. **Lockout on Finalize**: Once finalized, a Draft Quote review is locked. If updates are needed, a Manager or Admin must use the **Reopen** action to unlock the workspace.
2. **Missing ProductCodes**: When a needed code is missing, operators should submit a ProductCodeRequest. While pending, the charge line remains in a temporary unresolved state but does not block finalization if the code request is successfully registered.
3. **Draft Quote Generation Failure**: If the workspace displays a load error:
   - Ensure the associated PDF or text was ingested correctly.
   - Verify the operator has the `CanUseAIIntake` / `CanEditQuotes` permissions.
   - Check application logs for detailed validation errors.
