# V4 Rate Admin API

Internal reference for manager/admin V4 pricing maintenance.

## Base Paths

- `GET|POST /api/v4/rates/export/`
- `GET|POST /api/v4/rates/import/`
- `GET|POST /api/v4/rates/export-cogs/`
- `GET|POST /api/v4/rates/import-cogs/`
- `GET|POST /api/v4/rates/domestic/`
- `GET|POST /api/v4/rates/domestic-cogs/`
- `GET|POST /api/v4/rates/local-sell/`
- `GET|POST /api/v4/rates/local-cogs/`

## Shared Row Actions

- `GET /api/v4/rates/<table>/<id>/`
- `PATCH /api/v4/rates/<table>/<id>/`
- `DELETE /api/v4/rates/<table>/<id>/`
  Active rows return `409` and must be retired instead.
- `POST /api/v4/rates/<table>/<id>/retire/`
  Active rows are shortened safely.
  Future rows are removed.
- `POST /api/v4/rates/<table>/<id>/revise/`
  Creates a new effective-dated revision.
  Supports `retire_previous=true|false`.
- `GET /api/v4/rates/<table>/<id>/history/`
  Returns row-level audit entries from `RateChangeLog`.

## Shared Filters

- `search`
- `status=active|scheduled|expired`
- `valid_on=YYYY-MM-DD`
- `product_code`
- `currency`

Route tables also support origin/destination fields:

- export/import/export-cogs/import-cogs:
  `origin_airport`, `destination_airport`
- domestic/domestic-cogs:
  `origin_zone`, `destination_zone`

Counterparty tables also support:

- `agent`
- `carrier`

Local tables also support:

- `location`
- `direction`
- `payment_term` for `local-sell`

## Revision Contract

`POST /api/v4/rates/<table>/<id>/revise/`

Body:

```json
{
  "product_code": 2101,
  "origin_airport": "SYD",
  "destination_airport": "POM",
  "currency": "AUD",
  "rate_per_kg": "4.2500",
  "valid_from": "2026-05-01",
  "valid_until": "2026-12-31",
  "retire_previous": true
}
```

Notes:

- payload shape matches normal create payload for the table
- `retire_previous=true` is the preferred mode
- revision validation still enforces overlap prevention against every row except the source row being replaced

## Audit Log Shape

`GET /api/v4/rates/<table>/<id>/history/`

Response entries contain:

- `table_name`
- `object_pk`
- `actor`
- `actor_username`
- `action`
- `before_snapshot`
- `after_snapshot`
- `created_at`

## Bulk Upload Preview

`POST /api/v4/rates/upload/`

Multipart fields:

- `file`
- optional `dry_run=true`

Preview responses include:

- `processed_rows`
- `created_rows`
- `updated_rows`
- `preview_rows[]` with row number, target table, planned action, coverage, and validity

Preview mode performs validation but does not write any rows.
