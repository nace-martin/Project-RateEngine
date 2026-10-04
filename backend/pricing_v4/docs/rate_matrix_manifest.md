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

## Approved Pilot ingestion semantics

These were confirmed in the Pilot Gate B3C review (2026-10-04) and are what the validator
enforces. They do not change the Pilot Gate B3A payment-term contract.

1. Validity end dates are inclusive for overlap detection. A sheet ending on the day another starts
   overlaps it.
2. A blank applicability value means ANY.
3. There is no "specific beats general" precedence. A blank value overlapping a specific one is a
   conflict, not an ordering.
4. `direction` is required on every line.
5. A `PartyMaster` reference is the exact `legal_name` plus `country_code`.
6. A BUY sheet must name its supplier.
7. A Pilot v1 SELL sheet must leave `customer` blank.
8. A rate with neither origin nor destination is prohibited.
9. BUY currency alone cannot disambiguate competing costs.

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
- A rate line, or a percentage basis, may reference a code proposed in the manifest or an existing
  `CommercialProductCode`. In both cases the code must be active; an inactive code never resolves.
- An existing code used by a rate is re-checked against its legacy `ProductCode` on every run: the
  mapping must exist, the legacy code must be active and not retired, its code must still match,
  and its `gst_treatment` must still equal the commercial code's. Any drift is an error.

### Geography and parties

- IATA code → `GeoLocationIdentifier` (scheme `IATA`) → `GeoLocation`. Missing, non-unique, or
  inactive geography is an error. For `AIR` sheets the location must be an airport.
- A party is matched on exact `legal_name` and `country_code`, must be active, and must hold the
  stated active role. `supplier` accepts `CARRIER` or `AGENT`.
- Nothing is created. A missing or ambiguous party or location is an error.
- BUY sheet: `supplier` is required and `customer` is prohibited.
- SELL sheet: `supplier` is prohibited and, for Pilot v1, `customer` must be `null`. A named
  customer is rejected without being looked up.

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

### Locations

A line with neither origin nor destination is rejected. Beyond that, the rule depends on the
`category` of the resolved `CommercialProductCode`. The category is the one stated in the manifest
proposal or stored on the existing row; it is never derived from the code or its name.

| Category | Origin | Destination |
| :--- | :--- | :--- |
| `FREIGHT` | required | required |
| `ORIGIN` | required | must be blank |
| `DESTINATION` | must be blank | required |
| `CLEARANCE`, `SERVICE` | at least one of the two | at least one of the two |

No further meaning is attached to `CLEARANCE` or `SERVICE` yet.

### Tiers

Tiers are `[min_quantity, max_quantity)`: lower bound inclusive, upper bound exclusive. They must
start at 0, be contiguous with no gap or overlap, and end in exactly one open-ended tier. Anything
else is rejected as incomplete coverage. No price is calculated.

### Ambiguity and overlap

Each otherwise-valid line on an active sheet is compared with every other such line in the manifest
and with every line on an active sheet already in the database.

Two rates are compared only when `rate_type`, product code, and `transport_mode` are equal and
their validity windows overlap. End dates are inclusive, so a sheet ending on the day another
starts counts as overlapping.

Currency is handled by side. For SELL it is part of the rate identity: tariffs in different
currencies are different rates. For BUY it is not a selector: two otherwise-matching BUY rates in
different currencies are competing costs for the same charge and fail as ambiguous. Nothing is
converted and neither is chosen.

For supplier, customer, direction, origin, destination, service level, commodity category,
equipment type, and payment term, a blank value means "any". If every one of those is either equal
or blank on at least one side, both rates could match the same quote context, and the manifest
fails:

| Code | Meaning |
| :--- | :--- |
| `RATE_DUPLICATE_IDENTITY` | Every dimension is equal. |
| `RATE_PAYMENT_TERM_COEXISTENCE` | Identical except that one payment term is blank and the other specific. |
| `RATE_AMBIGUOUS_MATCH` | Some other dimension is blank on one side and specific on the other. |
| `RATE_BUY_CURRENCY_AMBIGUOUS` | BUY rates that match on every dimension but differ in currency. |

No precedence is applied in any of these cases. Two rates that differ on a dimension where both
sides are specific, such as `PREPAID` and `COLLECT`, or two different named suppliers, do not
conflict. Supplier remains a legitimate way for a future resolver to tell BUY rates apart.

Conflict checks run only on lines that passed every other check. Fix reported errors and run again.

## Not implemented

- Apply or write mode.
- A resolver, payment-term matching, or any pricing calculation.
- Customer-specific SELL tariffs. Pilot v1 rejects them.
