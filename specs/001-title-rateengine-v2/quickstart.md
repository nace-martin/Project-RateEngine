# Quickstart

This quickstart guide explains how to use the new V2 rating core endpoint.

## Prerequisites

- The `QUOTER_V2_ENABLED` feature flag must be enabled in the settings.

## Compute a Quote

To compute a quote, send a POST request to the `/api/quote/compute2` endpoint with the quote context in the request body.

**Request:**

```bash
curl -X POST http://localhost:8000/api/quote/compute2 \\
  -H "Content-Type: application/json" \\
  -d
  '{
    "mode": "AIR",
    "scope": "A2D",
    "payment_term": "PREPAID",
    "origin_iata": "BNE",
    "dest_iata": "POM",
    "pieces": [{"weight_kg": 81}],
    "audience": "PNG_CUSTOMER_PREPAID",
    "margins": {"FREIGHT": 10},
    "policy": {},
    "commodity": "GCR"
  }'
```

**Request (COLLECT):**

```bash
curl -X POST http://localhost:8000/api/quote/compute2 \\
  -H "Content-Type: application/json" \\
  -d
  '{
    "mode": "AIR",
    "scope": "A2D",
    "payment_term": "COLLECT",
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

**Response:**

The API will return the computed totals for the quote.

```
