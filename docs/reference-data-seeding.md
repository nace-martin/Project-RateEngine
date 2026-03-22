# Reference Data Seeding

This document covers step 3 of the production preparation flow:

- currencies
- countries
- cities
- airports
- optional location overrides/additions

The repository now includes an idempotent management command for importing this data:

```bash
python manage.py import_reference_data \
  --currencies docs/templates/reference-data-hub/currencies.csv \
  --countries docs/templates/reference-data-hub/countries.csv \
  --cities docs/templates/reference-data-hub/cities.csv \
  --airports docs/templates/reference-data-hub/airports.csv \
  --locations docs/templates/reference-data-hub/locations.csv \
  --dry-run
```

Then apply it for real:

```bash
python manage.py import_reference_data \
  --currencies docs/templates/reference-data-hub/currencies.csv \
  --countries docs/templates/reference-data-hub/countries.csv \
  --cities docs/templates/reference-data-hub/cities.csv \
  --airports docs/templates/reference-data-hub/airports.csv \
  --locations docs/templates/reference-data-hub/locations.csv
```

After import:

```bash
python manage.py normalize_locations
```

## Recommended Launch Pack

The recommended launch pack lives in `docs/templates/reference-data-hub/`.

Current generated pack:

- `24` currencies (`PGK` plus the currently scraped BSP FX currencies)
- `32` countries
- `86` major commercial cities
- `95` international airports
- `0` explicit location overrides

Notes:

- this pack is intentionally lean and operational, not geographically exhaustive
- airports import into `Airport` and also create airport `Location` rows automatically
- `locations.csv` stays empty so quote routing remains airport-based until you intentionally add city aliases later

## Other Generated Packs

The repo also has broader generated packs for future expansion.

The generator script at `scripts/build_reference_data_csvs.py` can rebuild:

- `docs/templates/reference-data-hub/` using `--profile hub`
- `docs/templates/reference-data-regional/` using `--profile regional`
- `docs/templates/reference-data/` using `--profile global`

The global pack is still useful as a source dataset, but it is not the recommended production seed for launch.

Notes:

- `locations.csv` is intentionally empty in all generated packs because airport imports already create airport `Location` rows.
- truly global `CITY` / `ADDRESS` location rows are not safe with the current `Location.code` design because it expects short codes, not globally unique city identifiers.

## Import Order

Import order matters:

1. `Currency`
2. `Country`
3. `City`
4. `Airport`
5. `Location`

`Airport` imports automatically create or update canonical airport `Location` rows via signals.
Use the `locations` CSV for:

- city alias locations
- address-style locations
- airport location overrides such as `is_active=false`
- metadata or naming cleanup

## CSV Formats

### currencies.csv

Required columns:

- `code`
- `name`

Optional columns:

- `minor_units`

### countries.csv

Required columns:

- `code`
- `name`

Optional columns:

- `currency_code`

### cities.csv

Required columns:

- `country_code`
- `name`

### airports.csv

Required columns:

- `iata_code`
- `name`
- `city_name`
- `country_code`

Notes:

- `city_name` must already exist in the `cities` import for the given `country_code`.
- importing an airport will create or update its airport `Location`

### locations.csv

Required columns:

- `kind`
- `code`
- `name`

Optional columns:

- `country_code`
- `city_name`
- `airport_iata`
- `is_active`
- `address_line`
- `metadata_json`

Supported `kind` values:

- `AIRPORT`
- `CITY`
- `ADDRESS`
- `PORT`

Notes:

- for `AIRPORT`, `airport_iata` is optional if `code` already matches an existing airport code
- if `city_name` is provided, `country_code` must also be valid
- `metadata_json` must be valid JSON

## Recommended Launch Minimum

At minimum, seed:

- `PGK`, `AUD`, `USD`
- all countries used by launch corridors
- all cities needed by launch customers
- all launch airports
- active `Location` rows for every quoted origin and destination

## Verification Checklist

After import, verify:

- customer forms return countries and cities
- quote location search returns launch stations
- all launch airports exist as active `Location` rows
- import/export rate seed commands reference only active locations that now exist
