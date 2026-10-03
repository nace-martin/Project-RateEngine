# Rate Matrix Manifest Dry-Run

Status: implemented in Pilot Gate B3C. Dry run only. There is no apply mode, no loader, and no
resolver; the Rate Matrix tables remain empty and no pricing path reads them.

Contract authority: `docs/architecture/clean-database-architecture-v2.1.md` §3.5.1.

## Command

```bash
python manage.py validate_rate_matrix_manifest path/to/manifest.json
python manage.py validate_rate_matrix_manifest path/to/manifest.json --format json
```

- Prints a report and exits 0 on `PASS`.
- Prints the same report and exits non-zero on `FAIL`.
- Never writes. Validation runs inside a transaction that is always rolled back, on a connection
  set read-only for the duration (`SET LOCAL transaction_read_only` on PostgreSQL,
  `PRAGMA query_only` on SQLite), so an accidental write raises instead of persisting.
- The report carries no timestamps or generated ids. The same manifest against the same database
  produces the same output.

Running it is an inspection. A `PASS` is not approval to load anything; see
`.codex/skills/seed-data-change/SKILL.md`.

## Manifest format

Strict JSON, UTF-8, `manifest_version` 1. Rules that apply everywhere:

- Every field listed below must be present. Use `null`, `""`, or `[]` to say "none"; nothing is
  defaulted or inferred.
- Unknown fields are rejected. There is no field for an FX rate, a converted amount, or a GST
  percentage.
- Duplicate keys, `NaN`, and `Infinity` are rejected.
- Amounts and quantities are decimal strings such as `"12.50"`. JSON numbers are rejected so no
  value passes through floating point. Negative values are rejected.
- Strings must not have leading or trailing whitespace.

```json
{
  "manifest_version": 1,
  "product_codes": [
    {
      "code": "EXP-SYNTH-SCREEN",
      "name": "Synthetic screening",
      "category": "ORIGIN",
      "sub_category": "",
      "gst_treatment": "STANDARD",
      "charge_basis_default": "PER_KG",
      "is_active": true,
      "legacy_product_code": {"id": 1902, "code": "EXP-SYNTH-SCREEN"}
    }
  ],
  "rate_sheets": [
    {
      "name": "Synthetic SELL Sheet",
      "version": 1,
      "rate_type": "SELL",
      "transport_mode": "AIR",
      "currency_code": "XTS",
      "valid_from": "2030-01-01",
      "valid_until": "2030-12-31",
      "is_active": true,
      "source_reference": "SYNTHETIC-TEST-TARIFF",
      "supplier": null,
      "customer": null,
      "lines": [
        {
          "product_code": "EXP-SYNTH-SCREEN",
          "rate_basis": "PER_KG",
          "unit_rate": "0.22",
          "additive_flat_amount": "4.50",
          "min_charge": null,
          "max_charge": null,
          "percentage_rate": null,
          "percentage_basis_product_code": null,
          "applicability": {
            "direction": "EXPORT",
            "origin_iata": "XAA",
            "destination_iata": null,
            "payment_term": "PREPAID",
            "service_level": "",
            "commodity_category": "",
            "equipment_type": ""
          },
          "tiers": []
        }
      ]
    }
  ]
}
```

The values above are synthetic. A party reference, where one is given, has the form
`{"legal_name": "...", "country_code": "ZZ", "role": "CARRIER"}`. A tier has the form
`{"min_quantity": "0", "max_quantity": "100", "unit_rate": "1.11"}`, with `max_quantity` `null`
for the open-ended final tier.

`origin_iata` and `destination_iata` are manifest references only. They are resolved to
`GeoLocation` rows; no airport-code column exists or is added in the Rate Matrix.

## Validation rules

### Product codes

Each entry proposes a `CommercialProductCode` that mirrors one legacy `ProductCode`.

- The legacy `ProductCode` must exist, by `id`, and its `code` must equal the stated legacy code.
- The proposed `code` must equal the legacy code exactly.
- The legacy `ProductCode` must be active and not retired.
- `gst_treatment` must equal the legacy `ProductCode`'s `gst_treatment`.
- `category` and `charge_basis_default` must be stated and must be allowed values. They are never
  derived from the code or its name.
- One legacy `ProductCode` maps to at most one `CommercialProductCode`, within the manifest and
  against existing rows.
- If a `CommercialProductCode` with that code already exists: identical and mapped to the same
  legacy code is reported as `REUSE`; anything else is an error. Existing rows are never updated.
- A rate line may reference a code proposed in the manifest, or an existing, active
  `CommercialProductCode` that already has a legacy mapping.

### Geography and parties

- IATA code → `GeoLocationIdentifier` (scheme `IATA`) → `GeoLocation`. Missing, non-unique, or
  inactive geography is an error. For `AIR` sheets the location must be an airport.
- A party is matched on exact `legal_name` and `country_code`, must be active, and must hold the
  stated active role. `supplier` accepts `CARRIER` or `AGENT`; `customer` accepts `CUSTOMER`.
- Nothing is created. A missing or ambiguous party or location is an error.
- A BUY sheet may not name a customer and a SELL sheet may not name a supplier. A BUY sheet with no
  supplier is reported as a warning.

### Sheets and lines

- `currency_code` must be three upper-case letters and a known `Currency`. Amounts stay in that
  currency; nothing is converted.
- `source_reference` is required.
- `valid_until` is `null` or later than `valid_from`.
- `version` is an integer of 1 or more. A `(name, version)` pair may appear once in the manifest and
  must not already exist; existing sheets are never updated.
- Basis fields: `FLAT`, `PER_KG`, `PER_CBM`, and `PER_UNIT` require `unit_rate` and forbid the
  percentage fields; `TIERED_WEIGHT` forbids `unit_rate` and the percentage fields and requires
  tiers; `PERCENTAGE` requires `percentage_rate` and a resolvable `percentage_basis_product_code`
  and forbids `unit_rate`.
- `additive_flat_amount` is allowed only with `PER_KG`.
- `min_charge` must not exceed `max_charge`.
- `direction` is required. `payment_term` is `PREPAID`, `COLLECT`, or blank; BUY lines must be blank.

### Tiers

Tiers are `[min_quantity, max_quantity)`: lower bound inclusive, upper bound exclusive. They must
start at 0, be contiguous with no gap or overlap, and end in exactly one open-ended tier. Anything
else is rejected as incomplete coverage. No price is calculated.

### Ambiguity and overlap

Each otherwise-valid line on an active sheet is compared with every other such line in the manifest
and with every line on an active sheet already in the database.

Two rates are compared only when `rate_type`, product code, `transport_mode`, and `currency_code`
are equal and their validity windows overlap. End dates are treated as inclusive, so a sheet ending
on the day another starts counts as overlapping.

For supplier, customer, direction, origin, destination, service level, commodity category,
equipment type, and payment term, a blank value means "any". If every one of those is either equal
or blank on at least one side, both rates could match the same quote context, and the manifest
fails:

| Code | Meaning |
| :--- | :--- |
| `RATE_DUPLICATE_IDENTITY` | Every dimension is equal. |
| `RATE_PAYMENT_TERM_COEXISTENCE` | Identical except that one payment term is blank and the other specific. |
| `RATE_AMBIGUOUS_MATCH` | Some other dimension is blank on one side and specific on the other. |

No precedence is applied in any of these cases. Two rates that differ on a dimension where both
sides are specific, such as `PREPAID` and `COLLECT`, do not conflict.

Conflict checks run only on lines that passed every other check. Fix reported errors and run again.

## Not implemented

- Apply or write mode.
- A resolver, payment-term matching, or any pricing calculation.
- Detection of BUY rates that differ only by currency or by two specific suppliers. These are
  distinct rates here; choosing between them is resolver behaviour.
