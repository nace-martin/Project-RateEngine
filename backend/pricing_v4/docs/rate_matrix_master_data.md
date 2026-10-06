# Rate Matrix Master-Data Loader

Status: implemented in Pilot Gate B3F. Covers the master data a Rate Matrix manifest depends on. It loads no
tariff or rate, and no pricing path reads what it writes.

Related: `rate_matrix_manifest.md` (tariff dry-run validator), spec
`docs/architecture/clean-database-architecture-v2.1.md` §3.4 and §3.5.1,
`.codex/skills/seed-data-change/SKILL.md`.

## Scope

Controlled creation or reuse of:

1. `PartyMaster`, with `PartyRole` and `PartyRoleIdentifier` rows;
2. a legacy `ProductCode`, only where it is genuinely new;
3. a `CommercialProductCode` that mirrors one legacy `ProductCode`.

Existing rows are never updated or deleted. A difference from an existing row is a conflict.

## Command

```bash
# Dry run (default): plans, writes nothing
python manage.py load_rate_matrix_master_data path/to/master.json
python manage.py load_rate_matrix_master_data path/to/master.json --format json

# Apply: separately authorised, atomic
python manage.py load_rate_matrix_master_data path/to/master.json \
    --apply --operator <username> --reviewed-sha256 <hash printed by the reviewed dry run>
```

- The dry run executes inside a read-only transaction that is always rolled back.
- `--apply` needs an active operator account and the sha256 the reviewed dry run printed. If the file has
  changed since review, the hash differs and nothing is written.
- Apply writes only if every record is `CREATE` or `REUSE`. One `CONFLICT` or `BLOCKED` record refuses the
  whole manifest.
- All writes happen in one transaction. After writing, the manifest is planned again inside that transaction
  and must come back all `REUSE`; otherwise everything is rolled back.
- Re-running an applied manifest creates nothing.
- A dry-run `READY` is not approval to apply. Dry-run approval and apply approval are separate.

## Record states

| State | Meaning |
| :--- | :--- |
| `CREATE` | The row, or a role or identifier under it, does not exist and would be created. |
| `REUSE` | An identical row already exists. Nothing would be written. |
| `CONFLICT` | The proposal is incompatible with existing data or with model rules. |
| `BLOCKED` | The proposal is consistent but lacks an approval, or depends on a record that is not ready. |

## Manifest format

Strict JSON, `manifest_version` 1. Every field is required; unknown fields, duplicate keys and non-finite
numbers are rejected. Each record carries an `evidence` string that is shown in the report. The values below
are synthetic.

```json
{
  "manifest_version": 1,
  "parties": [
    {
      "legal_name": "Synthetic Agent Pty Ltd",
      "trade_name": "",
      "entity_type": "COMPANY",
      "country_code": "ZZ",
      "roles": ["AGENT"],
      "identifiers": [{"role": "AGENT", "scheme": "TAX_ID", "value": "SYNTH-000111"}],
      "evidence": "Synthetic register entry"
    }
  ],
  "legacy_product_codes": [
    {
      "id": 2990,
      "code": "IMP-SYNTH-NEW",
      "description": "Synthetic new destination fee",
      "domain": "IMPORT",
      "category": "HANDLING",
      "default_unit": "SHIPMENT",
      "is_gst_applicable": true,
      "gst_rate": "0.1000",
      "gst_treatment": "STANDARD",
      "gl_revenue_code": "4000",
      "gl_cost_code": "5000",
      "percent_of_product_code": null,
      "evidence": "Synthetic rate card line"
    }
  ],
  "commercial_product_codes": [
    {
      "code": "IMP-SYNTH-NEW",
      "name": "Synthetic new destination fee",
      "category": "DESTINATION",
      "sub_category": "",
      "gst_treatment": "STANDARD",
      "charge_basis_default": "FLAT",
      "is_active": true,
      "legacy_product_code": {"id": 2990, "code": "IMP-SYNTH-NEW"},
      "gst_approval": {"approved": true, "reference": "SYNTHETIC-APPROVAL-1"},
      "evidence": "Synthetic evidence for the mirror"
    }
  ]
}
```

## Rules

### Parties

- Identity is the exact `legal_name` plus `country_code`. A match is reused, never duplicated.
- An existing party that is inactive, or whose `trade_name` or `entity_type` differs, is a conflict.
- A requested role the existing party lacks is created under it. A requested role that exists but is
  inactive is a conflict.
- An identifier (`scheme`, `value`) already held by another party or role is a conflict.

### Legacy ProductCodes

The loader follows the existing creation convention and adds nothing to it:

- The `id` is assigned by hand and stated in the manifest. Nothing allocates or guesses one.
- The id must sit in the domain range the model enforces: 1xxx export, 2xxx import, 3xxx domestic.
- `category` and `default_unit` must be values the legacy model allows. `default_unit` is `SHIPMENT`, `KG`
  or `PERCENT`.
- Every required field is explicit, including GL codes and the GST fields. `STANDARD` requires
  `is_gst_applicable` true and the reverse.
- The row is validated with `full_clean()` and inserted, never upserted.
- If the code or id already exists, every field must be identical (reuse) or the record is a conflict.
  Legacy ProductCodes are never altered.

The loader does not create a `ServiceComponent`. Rate Matrix manifests do not need one. The live V4 adapter
does: it drops any priced line whose ProductCode has no `ServiceComponent` with the same code. A new code is
therefore invisible to live quoting until `sync_v4_components` (or an equivalent, separately approved step)
creates its twin. That is a live-pricing change and is outside this loader.

### CommercialProductCode mirrors

- The legacy ProductCode must exist, or be created earlier in the same manifest, and be active and not
  retired.
- The commercial `code` must equal the legacy code exactly, and `gst_treatment` must equal the legacy value.
- `category` and `charge_basis_default` are explicit. Neither is derived from the code.
- One legacy ProductCode maps to at most one CommercialProductCode, in the manifest and in the database.
- An identical existing mirror is reused. Any difference in category, basis, GST, name or mapping is a
  conflict.
- **GST approval.** `gst_approval.approved` must be `true`, with a non-blank `reference`, before a mirror can
  be created. A mirror whose GST treatment matches legacy but has not been commercially approved is
  `BLOCKED`, which stops any apply that includes it.
- A mirror that depends on a legacy record that is `CONFLICT` or `BLOCKED` in the same manifest is `BLOCKED`.

## Audit

The tables written have no "who" or "why" columns. The apply report is the record: it states the operator,
the manifest sha256, and every record with its evidence. Keep the reviewed manifest and that report together.
