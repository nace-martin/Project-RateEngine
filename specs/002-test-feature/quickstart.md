# Quickstart

This quickstart guide explains how to test the new deterministic policy for AIR Import A2D quotes.

## Prerequisites

- The `QUOTER_V2_ENABLED` feature flag must be enabled in the settings.
- Ensure relevant BUY lane and break data is seeded for AU->PG routes.

## Test Scenarios

To test the new policy, send POST requests to the `/api/quote/compute2` endpoint with the appropriate `payment_term`.

### Scenario 1: PREPAID A2D Import (Invoice Currency: Origin Country Currency - AUD)

**Request:**

```bash
curl -X POST http://localhost:8000/api/quote/compute2 \
  -H "Content-Type: application/json" \
  -d 
  '{ 
    "mode": "AIR",
    "scope": "A2D",
    "payment_term": "PREPAID",
    "origin_iata": "BNE",
    "dest_iata": "POM",
    "pieces": [{"weight_kg": 81}],
    "commodity": "GCR"
  }'
```

**Expected Response:**

- `totals.invoice_ccy` should be "AUD".
- Sell lines should only include destination-side services.

### Scenario 2: COLLECT A2D Import (Invoice Currency: Destination Country Currency - PGK)

**Request:**

```bash
curl -X POST http://localhost:8000/api/quote/compute2 \
  -H "Content-Type: application/json" \
  -d 
  '{ 
    "mode": "AIR",
    "scope": "A2D",
    "payment_term": "COLLECT",
    "origin_iata": "BNE",
    "dest_iata": "POM",
    "pieces": [{"weight_kg": 81}],
    "commodity": "GCR"
  }'
```

**Expected Response:**

- `totals.invoice_ccy` should be "PGK".
- Sell lines should only include destination-side services.

### Scenario 3: Missing BUY Data (is_incomplete = true)

**Request:**

```bash
# Example request that would trigger missing BUY data, e.g., an unsupported lane or break
# (This would require specific input that is known to lack BUY data)
```

**Expected Response:**

- `is_incomplete` should be `true`.
- A clear reason for manual rate required should be present.
- No server error (500).


