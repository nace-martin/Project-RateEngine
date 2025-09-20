# Quickstart

This quickstart guide explains how to use the new V2 rating core endpoint.

## Prerequisites

- The `QUOTER_V2_ENABLED` feature flag must be enabled in the settings.

## Compute a Quote

To compute a quote, send a POST request to the `/api/quote/compute2` endpoint with the quote context in the request body.

**Request:**

```bash
curl -X POST http://localhost:8000/api/quote/compute2 \
  -H "Content-Type: application/json" \
  -d 
  {
    "customer_id": 123,
    "origin_address": { ... },
    "destination_address": { ... },
    "pieces": [ ... ]
  }
```

**Response:**

The API will return the computed totals for the quote.

```
