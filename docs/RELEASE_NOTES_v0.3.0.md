Release v0.3.0

Highlights

- Chargeable weight rounding aligned to whole kilograms.
- PostgreSQL-safe tests and deterministic CAF behavior.
- Public compute endpoint moved under `api/` and legacy removed.
- Frontend and docs updated to reflect the new endpoint.
- Migrations squashed for a cleaner history.

API Changes

- New: `POST /api/quote/compute` (TokenAuth required).
- Removed: `POST /quote/compute`.

Backend

- `engine.calculate_chargeable_weight_per_piece` rounds to the next whole kg via ceiling.
- DRF view `QuoteComputeView` exposed under `/api/quote/compute`.
- Tests provision minimal unmanaged tables for Postgres to run engine logic.
- CAF on FX is direction-aware (subtract when converting to PGK; add from PGK); tests updated accordingly.

Frontend

- Compute call updated to use `${NEXT_PUBLIC_API_BASE}/quote/compute` with `NEXT_PUBLIC_API_BASE` including `/api`.

Testing

- Backend tests pass against Postgres. FX and multi-leg tests validate CAF directionality and SELL rounding to 0.05.

Migrations

- Squashed `rate_engine` migrations into `0001_initial.py`; removed superseded migration files.
- For fresh setups: `python manage.py migrate`.
- For existing DBs: consider resetting non-prod DBs or verify schema alignment before adopting the squashed baseline.

Upgrade Guide

- Backend: set `DATABASE_URL` (Postgres), run `migrate`, and use `POST /api/quote/compute`.
- Frontend: set `NEXT_PUBLIC_API_BASE=http://127.0.0.1:8000/api` and rebuild.

Smoke Test

```
curl -X POST http://127.0.0.1:8000/api/quote/compute \
  -H "Authorization: Token YOUR_TOKEN" -H "Content-Type: application/json" \
  -d '{"org_id":1,"origin_iata":"SYD","dest_iata":"POM","shipment_type":"EXPORT","service_scope":"AIRPORT_AIRPORT","pieces":[{"weight_kg":"10"}]}'
```

