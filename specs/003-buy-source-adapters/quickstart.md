# Quickstart: BUY Source Adapters

This document provides a quick way to test the core user scenarios for the BUY Source Adapters feature.

## Scenario 1: A2D PREPAID (AUD)

**Goal**: Verify that an import shipment for a prepaid PNG customer is quoted correctly in AUD with destination-side fees.

1.  **Prepare the request** for the `POST /api/quote/compute2` endpoint with the following payload:
    ```json
    {
      "shipment_pieces": [
        { "weight_kg": 100, "length_cm": 50, "width_cm": 50, "height_cm": 50 }
      ],
      "audience": "PNG_CUSTOMER_PREPAID",
      "payment_term": "PREPAID",
      "origin": "BNE",
      "destination": "POM"
    }
    ```
2.  **Send the request** to the API.
3.  **Verify the response**:
    - The response is HTTP 200.
    - `is_incomplete` is `false`.
    - The final currency is `AUD`.
    - The quote includes destination-side fees (e.g., `CLEAR`, `CARTAGE`, `FUEL_PCT`).
    - The quote does *not* include origin-side fees (e.g., `DOC`, `SCREENING`).
    - The `selection_rationale` in the snapshot indicates the `RATE_CARD` was used.

## Scenario 2: Compare Rate Card vs. Spot

**Goal**: Verify that the system can compare a rate card offer with a manually entered spot offer and select the correct one.

1.  **Run Scenario 1** to get a baseline quote from the rate card.
2.  **Prepare a Spot Quote payload** representing a competing offer from a partner email:
    ```json
    {
      "ccy": "AUD",
      "af_per_kg": 5.50,
      "min_kg": 100,
      "fees": {"DOC": 25, "FUEL_PCT": 15, "CARTAGE": 150},
      "valid_from": "2025-10-01",
      "valid_to": "2025-10-31"
    }
    ```
3.  **Add the spot quote** to the request payload under a `spot_offers` key and resend.
4.  **Verify the response**:
    - The `selection_rationale` explains which offer was chosen based on the determinism rules (e.g., Pinned Spot > Rate Card).
    - The final pricing reflects the winning offer.

## Scenario 3: Missing BUY Offer

**Goal**: Verify that the system returns a safe, incomplete response when no pricing is available.

1.  **Prepare a request** for a lane that does not exist in any rate card:
    ```json
    {
      "shipment_pieces": [
        { "weight_kg": 100, "length_cm": 50, "width_cm": 50, "height_cm": 50 }
      ],
      "audience": "PNG_CUSTOMER_PREPAID",
      "payment_term": "PREPAID",
      "origin": "XXX",
      "destination": "YYY"
    }
    ```
2.  **Send the request**.
3.  **Verify the response**:
    - The response is HTTP 200.
    - `is_incomplete` is `true`.
    - `reason` contains a human-readable message like "BUY lane/break missing XXX→YYY (+100kg)".
