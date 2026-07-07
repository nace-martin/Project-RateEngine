# Air Freight Pilot Operational Runbook

This runbook guides operators through the end-to-end workflow of the SPOT Exception Workspace during the initial Air Freight pilot phase.

## 1. Spot Quotation Ingestion (AI Intake)

1. **Receive Quotation**: Operators receive a spot rate quote from a carrier or co-loader (e.g., Qantas Air Cargo, Air Niugini) via email or PDF.
2. **Submit to Intake**: 
   - Upload the PDF or paste the email body text in the Intake UI or POST to `/api/v3/spot/analyze-reply/` with `use_ai=True`.
   - The backend runs extraction through the `ReplyAnalysisService`, generating draft `SPEChargeLineDB` records.
3. **Verify Generation**: Ensure a `SpotPricingEnvelopeDB` (SPE) record has been successfully created with status `in_review` or `draft`.

## 2. Accessing the Exception Workspace

1. Log in to the RateEngine UI.
2. Navigate to `/quotes/spot/<envelope_id>/`.
3. The workspace will fetch the payload from `/api/v3/spot/envelopes/<envelope_id>/draft-quote/`.

## 3. Resolving Exceptions and Discrepancies

Operators must review all charges in the review queue:

### 3.1 Mapping ProductCodes
- For charges marked `needs_review` or having product code conflicts (e.g., "Fuel Surcharge" maps to multiple candidates):
  - Click **Map Product Code**.
  - Select the correct available ProductCode (e.g. `FSC-AIR`).
  - Submit the resolution to update `SPEChargeLineDB.manual_resolved_product_code`.

### 3.2 Requesting New ProductCodes
- If a charge requires a billing code that does not exist in the catalog:
  - Click **Request Product Code**.
  - Fill in the required metadata (suggested code, description, reason).
  - Submit the request. The Exception Workspace submits this ProductCode request through the Draft Quote resolve API endpoint (`/api/v3/spot/envelopes/<uuid:id>/draft-quote/resolve/`) using the `request_product_code` action, which registers the request and transitions the charge line's status to pending.

### 3.3 Ignoring/Excluding Items
- For lines containing disclaimers, text fragments, or duplicate listings:
  - Click **Ignore Charge** or **Ignore Item**.
  - Specify the reason.
  - This marks the line as `exclude_from_totals = True` or transitions the unclassified item to `ignored_items` in the DB.

### 3.4 Editing Details
- For charges needing currency, rate, or calculation unit adjustments:
  - Click **Edit Charge**.
  - Update values (only alphanumeric 3-letter currency, positive numeric values for rate/amount, and valid units are accepted).
  - Submit changes.

## 4. Totals and Math Verification

1. Review the `totals_validation` section.
2. If `math_balances` is `false`, review the difference between the calculated total (sum of active charge lines) and the extracted total (extracted from raw PDF text).
3. Adjust charge lines or exclude irrelevant lines until the totals balance or warnings are acknowledged.

## 5. Finalizing the Review

1. Once all items in the review queue are resolved (or pending admin code request review):
   - Click **Finalize Review**.
   - This sends a POST request to `/api/v3/spot/envelopes/<envelope_id>/draft-quote/finalize/`.
   - On success, the review status changes to `finalized` and the workspace locks.
2. If critical unresolved blockers exist, finalization will fail with a `400 Bad Request` listing the blockers.

## 6. Promotion to Quote (Deterministic V4 calculation)

1. Promoted quotes will consume the resolved SPOT charges.
2. Spot freight charges replace standard freight charges for the same leg/route.
3. The deterministic V4 pricing engine processes final rating.
