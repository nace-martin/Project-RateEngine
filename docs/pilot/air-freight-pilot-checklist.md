# Air Freight Pilot Checklists

This document contains checklists for UAT (User Acceptance Testing), Support Triage, and Launch Readiness.

## 1. User Acceptance Testing (UAT) Checklist

Before proceeding to live pilot production operations, verify the following workflows in the staging environment:

- [ ] **Intake Upload**: Upload an Air Freight spot quote PDF and verify it completes extraction without server errors.
- [ ] **Workspace Rendering**: Open the Exception Workspace for the uploaded envelope and confirm that suggested charges, unclassified items, and validation warnings render correctly.
- [ ] **ProductCode Mapping**: Map an ambiguous line item to an available ProductCode (e.g. `FSC-AIR`) and confirm it transitions from the review queue.
- [ ] **Edit Details**: Edit a charge's rate and currency, verifying that the values update and totals recalculate.
- [ ] **ProductCode Request**: Submit a request for a new ProductCode and check that the line status becomes "pending".
- [ ] **Ignore Line**: Ignore an unclassified item, verifying it is moved to the ignored list.
- [ ] **Finalization Blockers**: Try to finalize with unresolved items and confirm the request is rejected with a list of remaining blockers.
- [ ] **Successful Finalization**: Resolve all blockers, click finalize, and confirm the workspace enters a read-only locked state.
- [ ] **Manager Reopen**: Log in as a Manager, reopen the finalized workspace, and verify it becomes editable again.

## 2. Support Checklist

When an operator reports an issue during the pilot phase, follow this triage flow:

1. **Verify Authentication and RBAC**:
   - Check if the user is authenticated.
   - Confirm user has the `sales` or `manager` role.
   - Verify the user's Branch/Department matches the envelope's operating scope (cross-operating-entity rule).
2. **Retrieve Envelope State**:
   - Use the Django admin interface or GET `/api/v3/spot/envelopes/<uuid:id>/draft-quote/`.
   - Inspect the `conditions_json` field on the envelope to see the status under `draft_quote_review`.
3. **Verify DB Logs and Decisions**:
   - Query `DraftQuoteDecisionDB` filter by `envelope_id` to inspect the history of decisions applied by the operator.
   - Check for validation warnings in `metadata.user_audit_log`.
4. **Unlock Frozen Workspaces**:
   - If an operator accidentally finalized a quote that requires changes:
     - Ask a Manager to click "Reopen" in the workspace UI, or run `reopen_review(envelope, manager_user)` via a Django shell script.

## 3. Launch Readiness Criteria

Verify that the following infrastructure and configuration checks are completed:

- [ ] Production DB contains the necessary `ProductCode` seed rows for EFM Air Freight.
- [ ] Secret manager environment variables (`DJANGO_SECRET_KEY`, database connection strings) are loaded.
- [ ] Backend is running stateless with static assets routed via WhiteNoise and verify configured media/storage backend is available.
- [ ] Application logs are configured to capture structured logger metadata (`extra` dictionary parameters) in configured application log sink / platform logging.
