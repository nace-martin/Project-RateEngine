# RateEngine V2 Architecture

This document outlines the architecture of the new RateEngine V2, designed for a more deterministic and auditable quoting process.

## Overview

The V2 rating core replaces the monolithic `compute_quote` function with a series of pure functions:

1.  **`normalize`**: Standardizes the input `QuoteContext`.
2.  **`rate_buy`**: Calculates the buy-side costs.
3.  **`map_to_sell`**: Translates buy-side costs to sell-side prices using `SellRecipe`.
4.  **`tax_fx_round`**: Applies taxes, foreign exchange conversions, and final rounding.

These functions are orchestrated by `compute_quote_v2` and exposed via the `/api/quote/compute2` endpoint.

## Architecture Diagram

```mermaid
graph TD
    A[API Request /api/quote/compute2] --> B{QUOTER_V2_ENABLED?}
    B -- Yes --> C[compute_quote_v2 Orchestrator]
    C --> D[normalize(QuoteContext)]
    D --> E[rate_buy(NormalizedContext)]
    E --> F[map_to_sell(BuyResult)]
    F --> G[tax_fx_round(SellResult)]
    G --> H[Totals Response]
    B -- No --> I[Return 404 Not Found]
```

## Tiny Rule Tables

Decisions in V2 are heavily driven by small, focused data tables. These tables are designed to be easily auditable and extendable.

### AUDIENCE Table

| Key                      | Description                               |
| :----------------------- | :---------------------------------------- |
| `PNG_CUSTOMER_PREPAID`   | Customer in PNG, payment prepaid          |
| ...                      | ...                                       |

### INVOICE_CCY Table

| Key | Description       |
| :-- | :---------------- |
| `PGK` | Papua New Guinean Kina |
| ... | ...               |

### SCOPE_SEGMENTS Table

| Scope | Segments                  |
| :---- | :------------------------ |
| `A2D` | `AIR`, `DOMESTIC`         |
| ...   | ...                       |

## Onboarding Notes for Sales/Finance

### What's New?

RateEngine V2 introduces a more transparent and predictable way to calculate air freight quotes. The new system is built on a series of clear steps, making it easier to understand how a final price is derived.

### Key Benefits

*   **Transparency**: Each step of the calculation is distinct, allowing for easier auditing and understanding of pricing components.
*   **Consistency**: The pure function approach ensures that the same inputs will always produce the same outputs, reducing discrepancies.
*   **Maintainability**: The modular design makes it simpler to update or add new pricing rules without affecting the entire system.

### New Policy: AIR · Import · A2D (Airport→Door) v2 rating policy — PREPAID & COLLECT

This new policy introduces deterministic currency and fee selection for AIR imports on A2D lanes, ensuring consistent and auditable quotes.

**Key Rules:**

*   **Audience & Invoice Currency**:
    *   **PREPAID (shipper pays)**: Invoice currency = ORIGIN country currency (e.g., AU→PG → AUD).
    *   **COLLECT (consignee pays)**: Invoice currency = DESTINATION country currency (e.g., AU→PG → PGK).
    *   Audience is derived from payment term and direction.
*   **Fee Menu (A2D import)**:
    *   Only DESTINATION-side services are included (e.g., customs clearance, delivery).
    *   ORIGIN-side services (e.g., pickup, export docs) are excluded.
    *   If a fee requires a base and it's absent, the fee is skipped, and a warning is recorded in the snapshot.
*   **Missing Rate Handling**:
    *   If BUY lane or required break data is missing, the quote is marked `is_incomplete = true` with a "Manual Rate Required" reason.
    *   Sell totals are still computed from available policy-driven items; the system will not crash.
*   **Totals & Reporting**:
    *   Response includes `totals.invoice_ccy`.
    *   Itemized sell lines have stable `code` identifiers and currencies aligned to the invoice currency.
    *   A machine-readable `snapshot` describes policy/recipe decisions.

**Impact:**

*   **Correct Quotes**: Sales will see only the correct destination service menu.
*   **Accurate Invoices**: Invoices will land in the right currency (AUD for PREPAID, PGK for COLLECT).
*   **Clear Fallbacks**: Missing data results in clear, actionable reasons, preventing 500 errors or silent fallbacks.

### How to Use (for testing/validation)

The new V2 endpoint is `/api/quote/compute2`. You can test it by sending a POST request with the quote context. Ensure the `QUOTER_V2_ENABLED` feature flag is active in the system settings.

**Example Request (cURL):**

```bash
curl -X POST http://localhost:8000/api/quote/compute2 \
  -H "Content-Type: application/json" \
  -d \
  '{
    "mode": "AIR",
    "scope": "A2D",
    "payment_term": "PREPAID",
    "origin_iata": "BNE",
    "dest_iata": "POM",
    "pieces": [{"weight_kg": 81}],
    "audience": "PNG_CUSTOMER_PREPAID",
    "invoice_ccy": "PGK",
    "margins": {"FREIGHT": 10},
    "policy": {},
    "commodity": "GCR"
  }'
```

### Where to find more information

*   `specs/001-title-rateengine-v2/spec.md`: Detailed feature specification.
*   `specs/001-title-rateengine-v2/data-model.md`: Data structures used in V2.
*   `backend/pricing_v2/`: The core implementation files.
