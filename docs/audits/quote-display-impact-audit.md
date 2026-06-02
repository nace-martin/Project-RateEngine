# Audit Report: Quote Display & Output Impact Analysis

## 1. Executive Summary & Risk Level

* **Risk Level:** **High**.
* **Primary Concern:** 
  1. The database models (`QuoteLine`), frontend display (`QuoteFinancialBreakdown.tsx`), and PDF generation service (`pdf_service.py`) are hardcoded to a rigid **three-bucket architecture**: `ORIGIN`, `FREIGHT`/`MAIN`, and `DESTINATION`.
  2. There is no structural representation, display capability, or layout layout in either the UI or the PDF to handle **multi-leg routes** (e.g., `BNE → POM → LAE` involving domestic on-forwarding, or `HGU → POM → SIN` involving pre-carriage).
  3. Hybrid SPOT display—where known local charges and SPOT charges appear together—is currently blocked by the bucket-level override strategy, which completely wipes out standard lines in any overridden bucket.

---

## 2. Structural & UI Audit Questions

### Can the Quote-Line Model show multiple legs?
* **No.** The `QuoteLine.leg` database field is designed around the choices: `ORIGIN`, `MAIN` (or `FREIGHT`), and `DESTINATION`. 
* There is no field to model a fourth leg like `DOMESTIC_ONFORWARDING` or `DOMESTIC_PRE_CARRIAGE`, nor is there a sequence index to represent multi-leg hops (e.g., leg 1, leg 2).

### Can the UI/PDF show leg-specific charges?
* **No.** Both the frontend summary and PDF generation group charges strictly by their `leg` or `bucket` value. 
* Any on-forwarding charges categorized as `DESTINATION` will simply merge with international destination local charges, concealing the fact that the cargo is moving via domestic air freight to a second airport inside PNG.

### Can they show airport collection/lodgement notes?
* **Partially.** Currently, notes can only be entered as general `calculation_notes` on individual lines or in the generic `totals.notes` field (which render as conditional footnotes at the bottom of the breakdown or PDF).
* There is no dedicated UI element, warning card, or prominent visual highlight to instruct the user or customer: *"Consignee must collect at airport (HGU) - Door service is unavailable."*

### Can they show door service restrictions for non-office PNG locations?
* **No.** Because the `DomesticPricingEngine` crashes immediately when requesting door service outside `POM`/`LAE`, the quote calculation never succeeds. 
* Consequently, the UI cannot display a quote with a warning banner or explain why door delivery was restricted.

### Can they show known charges + SPOT charges together?
* **No.** Because the `adapter.py` overrides charges at the entire bucket level, standard local charges (like documentation fees) are wiped out if a spot charge is introduced in the same bucket. 
* The UI and PDF will only show standard charges *or* spot charges, never both merged together within the same bucket.

---

## 3. Component-by-Component Impact

### A. Frontend Quote Summary & Financial Breakdown (`QuoteFinancialBreakdown.tsx`)
* **Current Behavior:** Hardcodes the buckets `ORIGIN`, `FREIGHT`, and `DESTINATION`. Inside the buckets, charges are sorted by predefined `SUBCATEGORY_ORDER` (e.g., "Customs / Regulatory", "Documentation", "Local Transport / Cartage").
* **Impact:** Domestic on-forwarding charges would get dumped into the generic `DESTINATION` bucket under "Local Transport / Cartage", mixing them with customs clearance and import agency fees. The customer cannot visually differentiate international destination handling from domestic air transit.

### B. PDF Quote Output (`pdf_service.py`)
* **Current Behavior:** Groups lines strictly into `Origin Charges`, `International Freight`, and `Destination Charges` sub-tables:
  ```python
  if leg == 'ORIGIN':
      bucket_name = 'Origin Charges'
  elif leg == 'MAIN':
      bucket_name = 'International Freight'
  elif leg == 'DESTINATION':
      bucket_name = 'Destination Charges'
  ```
* **Impact:** Multi-leg shipments cannot be printed with clear, separate cost breakdowns for domestic transit. The grand totals and sub-tables would be misleading for complex routes.

### C. Customer-Facing Public Quote Page
* **Current Behavior:** Reuses the same layout logic as `QuoteFinancialBreakdown.tsx` to render the customer's secure online view.
* **Impact:** High confusion risk: a customer receiving a quote for `BNE → POM → HGU` might assume they are receiving door delivery at `HGU` because there is no clear customer-facing explanation of the "Consignee Collects at Airport" restriction.

---

## 4. Files Reviewed

1. `backend/quotes/models.py` (Database model for `QuoteLine` and legs)
2. `backend/quotes/pdf_service.py` (PDF generation, buckets, layout)
3. `frontend/src/components/QuoteFinancialBreakdown.tsx` (UI financial card, buckets mapping)
4. `frontend/src/components/spot/ChargeBucketSection.tsx` (SPOT-specific UI components)
5. `frontend/src/lib/types.ts` (TypeScript types mapping quote lines)

---

## 5. Recommended Phased Implementation

### Phase 1: Support Merged Standard & Spot Charges (Data Model & Adapter)
* **Goal:** Enable hybrid SPOT quotes where standard local charges and spot charges coexist.
* **Action:**
  * Modify the merge strategy in `PricingServiceV4Adapter._merge_charge_lines` to operate at the **ProductCode category level** instead of the entire bucket.
  * Update `QuoteFinancialBreakdown.tsx` to display a distinct badge for `SPOT` sourced lines next to standard rate card lines in the same bucket section.

### Phase 2: Add Structural Warning Banners & Movement Explanations (UI/PDF)
* **Goal:** Visually communicate airport collection/lodgement rules and door service restrictions.
* **Action:**
  * Add a `RoutingWarning` banner to the top of `QuoteFinancialBreakdown.tsx` when a non-office PNG airport (e.g., `HGU`, `GKA`) is selected.
  * Inject explicit terms to the PDF generator via `_build_terms_and_conditions()`: *"Door service is unavailable at HGU. Consignee must collect cargo at the airport terminal."*

### Phase 3: Leg Refactoring for Multi-Leg Routes
* **Goal:** Seamlessly display domestic legs in the UI and PDF.
* **Action:**
  * Expand `QuoteLine.leg` choices (or add a separate sequence-based `leg_sequence` field) to model transit steps.
  * Update `QuoteFinancialBreakdown.tsx` and `pdf_service.py` to dynamically render a fourth sub-table/bucket (e.g., `PNG Domestic Transit`) if domestic on-forwarding or pre-carriage is active.

---

## 6. Required Test Scenarios

### A. UI Layout Integrity
* **Test 1 (Hybrid Spot Display):** Verify that standard documentation fees and spot airfreight charges appear together under `Origin Charges` in `QuoteFinancialBreakdown.tsx`.
* **Test 2 (Airport Collection Badge):** Verify that a shipment to `HGU` renders a clear warning icon indicating "Airport Collection Required" in the quote summary view.

### B. PDF Verification
* **Test 3 (PDF Bucket Subtotals):** Verify that injecting a custom `PNG Domestic Transit` line does not break PDF layout alignment or subtotal arithmetic.
* **Test 4 (Terms Formatting):** Verify that the custom terms and conditions note regarding airport collection is printed on the PDF when the destination is a non-office PNG airport.
