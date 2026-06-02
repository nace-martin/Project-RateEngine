# Audit Report: PNG Domestic On-Forwarding & Special Cargo Hybrid SPOT Workflow

## 1. Executive Summary & Risk Level

* **Risk Level:** **High**. 
* **Primary Concern:** 
  1. The international engines (`ImportPricingEngine`, `ExportPricingEngine`) assume a single direct international leg and lack any concept of domestic on-forwarding or pre-carriage inside PNG (e.g., `BNE → LAE` routed as `BNE → POM` + `POM → LAE`).
  2. The `DomesticPricingEngine` enforces door service restrictions at initialisation, throwing a hard `ValueError` if a door scope is requested for non-office PNG locations (e.g., `HGU`), causing the quote flow to crash instead of triggering a SPOT/manual review workflow or falling back to airport collection/lodge.
  3. Special cargo hybrid SPOT merges currently use a strict **bucket-level override** strategy in the `PricingServiceV4Adapter`. While this prevents appending spot freight charges, it is a blunt instrument that completely wipes out standard local charges in the same bucket if any spot charge is present in that bucket.

---

## 2. Current Behaviour & Gaps

### A. PNG Domestic On-Forwarding / Pre-Carriage in International Quotes

#### Current Behaviour:
1. **Direction Classification (`backend/core/business_rules.py`):**
   * Enforces strict PG-to-PG (`DOMESTIC`), PG-to-non-PG (`EXPORT`), and non-PG-to-PG (`IMPORT`) classification.
   * Cross-border lanes with no PG origin or destination throw a `ValueError` immediately.
2. **Scope Rules (`A2A`, `D2A`, `A2D`, `D2D`):**
   * In `DomesticPricingEngine`, door cartage service is strictly locked to `POM` and `LAE` (`self.DOOR_PORTS = ['POM', 'LAE']`).
   * A hard `ValueError` is thrown at initialisation if a door pickup/delivery is requested for any other PNG location (e.g., `D2D` to `HGU`).
3. **Leg Processing (`backend/pricing_v4/engine/`):**
   * `ImportPricingEngine` and `ExportPricingEngine` only calculate `ORIGIN`, `FREIGHT`, and `DESTINATION` legs for the primary international lane. They cannot dispatch to `DomesticPricingEngine` or load domestic rate cards for internal PNG legs.
   * `A2A` is treated as a default fallback scope, but true domestic `A2A` is rare in real operations, where door service or airport lodge/collection is preferred.

#### Gaps Identified:
* **No Multi-Leg Routing Engine:** There is no routing coordinator or multi-leg dispatcher to split `BNE → LAE` into `BNE → POM` (International Import) and `POM → LAE` (Domestic On-forwarding).
* **Cartage Crash vs. SPOT Trigger:** Requests for door services at unserviceable PNG locations (e.g., door delivery to `HGU`) crash the pricing adapter with a `ValueError` instead of gracefully routing to the SPOT manual-sourcing workflow.
* **No Airport Lodge/Collection Rules:** There is no programmatic distinction between door delivery (which EFM does not offer outside `POM`/`LAE`) and airport-lodge/collection (where the customer retrieves cargo from the local airport).

#### Corrected Business Rules (Clarification):
* **Serviceability to Airport:** Non-POM/LAE PNG airports (like `HGU` or `RAB`) can still be serviceable to the airport.
* **Standard Rates Coverage:** If airport-to-airport (A2A) domestic rates exist, they must **not** trigger SPOT.
* **Office Coverage Boundary:** POM/LAE office coverage only affects true door pickup/delivery (cartage legs), not airport-to-airport freight.
* **D2A Imports Standard Path:** D2A imports to airports like `HGU` or `RAB` (where destination is the airport and consignee collects) should remain standard if all rates exist in the database.

---

### B. Special Cargo Hybrid SPOT Workflow

#### Current Behaviour:
1. **SPOT Trigger Logic (`backend/quotes/spot_services.py`):**
   * `SpotTriggerEvaluator.evaluate` determines if a quote must enter SPOT mode based on rate availability or commodity rules.
   * Database rules in `CommodityChargeRule` can trigger SPOT or manual entry via `requires_spot` or `requires_manual` modes.
2. **Merge Strategy (`backend/pricing_v4/adapter.py`):**
   * The `_merge_charge_lines` method performs a bucket-level replacement:
     ```python
     spot_buckets = {l.bucket for l in spot_lines}
     final_lines = [l for l in standard_lines if l.bucket not in spot_buckets]
     final_lines.extend(spot_lines)
     ```
   * If a SPOT envelope contains charges in the `airfreight` bucket, all standard `airfreight` charges are discarded, and only the spot lines are kept.

#### Gaps Identified:
* **All-or-Nothing Bucket Wipeout:** If a spot charge overrides a bucket (e.g., `origin_charges`), it discards all other standard local charges in that same bucket, even if those standard charges (like documentation fees or regulatory fees) are still valid and required.
* **Crash Discards Local Charges:** If the standard engine crashes (due to the domestic door scope validation), `calculate_charges` falls back to a SPOT-only overlay where standard lines are completely empty. This discards valid local charges that the standard engine *could* have resolved.

---

## 3. Files Reviewed

1. `backend/core/business_rules.py` (Shipment classification logic)
2. `backend/pricing_v4/engine/domestic_engine.py` (Domestic pricing engine & cartage validation)
3. `backend/pricing_v4/engine/import_engine.py` (Import engine active legs & scope handling)
4. `backend/pricing_v4/engine/export_engine.py` (Export engine structure)
5. `backend/pricing_v4/adapter.py` (Standard & SPOT merge/calculation coordinator)
6. `backend/pricing_v4/category_rules.py` (ProductCode category classification)
7. `backend/quotes/spot_services.py` (SPOT trigger & scope validation)

---

## 4. Proposed Safe Implementation Phases

### Phase 1: Graceful Scope Fallback & SPOT Promotion (No Crash)
* **Goal:** Prevent the pricing engine from throwing hard `ValueError` crashes for unserviceable door scopes.
* **Action:** 
  * Modify `DomesticPricingEngine` to set a custom warning flag (e.g., `is_unserviceable_door = True`) instead of raising `ValueError` in `_validate_service_scope()`.
  * Update `PricingServiceV4Adapter` and `SpotTriggerEvaluator` to catch unserviceable scopes and cleanly trigger the SPOT / manual review workflow with `SpotTriggerReason.REQUIRES_ASSUMPTIONS` or a new reason `UNSERVICEABLE_DOOR_CARRIAGE`.
  * Expose an "Airport Collection/Lodge" flag on the quote so users know the shipment must be collected by the consignee at the local PNG airport instead of expecting door delivery.

### Phase 2: Refined Hybrid SPOT Merging (Granular Overrides)
* **Goal:** Stop bucket-level wipeouts of standard local charges.
* **Action:**
  * Refine `_merge_charge_lines` in the adapter to merge charges at the **ProductCode category level** or **line-by-line** rather than wiping out whole buckets.
  * Ensure known local charges (like regulatory surcharges, screening fees, or documentation fees) are preserved, while replacing only the specific freight or cartage lines that are overridden by the SPOT envelope.

### Phase 3: Multi-Leg Routing Dispatcher
* **Goal:** Enable PNG domestic on-forwarding within international quotes.
* **Action:**
  * Implement a `MultiLegPricingDispatcher` that detects when an international shipment destination or origin requires internal PNG transit (e.g., `LAE` via `POM`).
  * Programmatically split the quote into:
    1. International Leg (`BNE → POM` via `ImportPricingEngine`).
    2. Domestic Leg (`POM → LAE` via `DomesticPricingEngine`).
  * Consolidate the line items from both engines into a unified `QuoteCharges` response, maintaining proper leg separation (`ORIGIN`, `MAIN`, `DOMESTIC_ONFORWARDING`, `DESTINATION`).

---

## 5. Test Scenarios Needed

### A. Domestic Scope Restrictions
* **Test 1 (POM/LAE Door Service):** Verify `POM` and `LAE` support `D2D`, `D2A`, `A2D` without warnings.
* **Test 2 (Non-Office Location Door Service):** Verify `HGU` with `D2D` does not crash, but correctly triggers a SPOT workflow.
* **Test 3 (Non-Office Airport Collection):** Verify `HGU` with `A2A` prints a clear instruction note regarding airport collection.

### B. Hybrid SPOT Merging
* **Test 4 (Preservation of Local Surcharges):** Verify that when a SPOT envelope overrides `airfreight` charges, local charges in `origin_charges` or `destination_charges` (such as documentation fees) are preserved and not discarded.
* **Test 5 (Specific Surcharge Replacement):** Verify that if a SPOT envelope contains a specific cartage charge, only the standard cartage charge is replaced, leaving other local handling charges intact.
