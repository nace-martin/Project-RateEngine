# Quickstart for AIR · Import · A2D — Deterministic currency & destination-fee policy

This quickstart demonstrates how to use the new deterministic currency and destination-fee policy for AIR import A2D quotes.

## PREPAID Quote

To request a PREPAID quote, set the `payment_terms` to "PREPAID". The `invoice_ccy` will be in the origin country's currency.

```bash
curl -X POST \
  http://127.0.0.1:8000/api/v2/quotes/ \
  -H 'Content-Type: application/json' \
  -d {
    "mode": "AIR",
    "direction": "IMPORT",
    "service_scope": "A2D",
    "payment_terms": "PREPAID",
    "origin_airport_code": "BNE",
    "destination_airport_code": "POM",
    "weight": 81,
    "commodity": "GCR"
  }
```

### Expected Response

The response will have `invoice_ccy` set to "AUD" and will only include destination-side services.

## COLLECT Quote

To request a COLLECT quote, set the `payment_terms` to "COLLECT". The `invoice_ccy` will be in the destination country's currency.

```bash
curl -X POST \
  http://127.0.0.1:8000/api/v2/quotes/ \
  -H 'Content-Type: application/json' \
  -d {
    "mode": "AIR",
    "direction": "IMPORT",
    "service_scope": "A2D",
    "payment_terms": "COLLECT",
    "origin_airport_code": "BNE",
    "destination_airport_code": "POM",
    "weight": 81,
    "commodity": "GCR"
  }
```

### Expected Response

The response will have `invoice_ccy` set to "PGK" and will only include destination-side services.

