# Rate Matrix Tariff Loader and ServiceComponent Mirror

Status: implemented in Pilot Gate B3H. Neither command has been applied to any database by this
change. The Rate Matrix is not wired into live pricing and no pricing path reads what these
commands write. Legacy COGS/SELL pricing remains authoritative and route automation stays disabled.

Related: `rate_matrix_manifest.md` (the validation contract this loader reuses),
`rate_matrix_master_data.md` (prerequisites), spec
`docs/architecture/clean-database-architecture-v2.1.md` §3.5.1,
`.codex/skills/seed-data-change/SKILL.md`.

## 1. Tariff loader: `load_rate_matrix_manifest`

The apply counterpart of `validate_rate_matrix_manifest`. It parses and validates every manifest with
the unchanged B3C contract (strict JSON, no defaults, same codes and messages), then plans and, only
when asked, inserts:

```text
RateSheet -> RateLine -> RateApplicability
                      -> RateTier
```

It never creates a `CommercialProductCode`, party, location, or legacy `ProductCode`. A manifest that
would create a product code is refused (`PRODUCT_CODE_CREATE_NOT_SUPPORTED`); load master data first.

```bash
# Dry run (default): plans, writes nothing. Several files are checked together.
python manage.py load_rate_matrix_manifest a.json [b.json ...] [--format text|json]

# Apply: separately authorised, atomic
python manage.py load_rate_matrix_manifest a.json [b.json ...] \
    --apply --operator <username> --reviewed-sha256 <"Reviewed sha256" printed by the reviewed dry run>
```

### Contract

- Dry run is the default and runs in a read-only, rolled-back transaction.
- `--operator` must name an active user, who is recorded as `RateSheet.created_by`.
- `--reviewed-sha256` binds an apply to the reviewed input. For one manifest it is that manifest's
  sha256, computed on the text after newline normalisation (as every Pilot loader prints it, so it can
  differ from a raw file hash on CRLF files). For several it is the sha256 of the sorted per-manifest
  hashes, so it covers exactly that set in any order; a subset is refused.
- Apply is all-or-nothing in one transaction across every manifest. Any error, conflict, or ambiguity
  refuses the whole apply and writes nothing.
- Insert-only. A stored row is never updated or deleted.
- A sheet is identified by `(name, version)`:
  - not stored: `CREATE`;
  - stored and identical in every sheet field and every line, applicability, and tier: `REUSE`;
  - stored and different in anything: `CONFLICT`.

  A correction is a new version with its own validity window; an overlapping rival version is
  reported as ambiguous.
- A second apply of the same manifests creates zero rows.
- After writing, the loader re-plans inside the same transaction and requires every sheet to be
  `REUSE`, no ambiguity among active tariffs, and row counts equal to the plan. Any failure rolls the
  whole apply back.
- Conflicts are also detected **between** the supplied manifests, not only within one file or against
  stored rows: duplicate identity, blank-versus-specific payment term, BUY currency ambiguity, blank
  dimension overlapping a specific one, and the same sheet name and version supplied twice. No
  precedence is applied and nothing is converted.
- Pilot v1 rules are inherited: BUY names its supplier, SELL leaves customer blank, BUY payment term
  is blank, blank means ANY, native currency only, validity is inclusive.

## 2. ServiceComponent mirror: `load_service_component_mirror`

Why: the V4 adapter turns an engine charge into a quote line only when a `ServiceComponent` with the
same code exists; otherwise it logs a warning and skips the line. A new ProductCode such as
`IMP-TERM-DEST` therefore has no live effect until it has one. `sync_v4_components` is the only other
creator and it upserts every ProductCode and the SPOT defaults, which is too broad for one reviewed
charge.

```bash
python manage.py load_service_component_mirror path/to/component.json [--format text|json]
python manage.py load_service_component_mirror path/to/component.json \
    --apply --operator <username> --reviewed-sha256 <hash printed by the reviewed dry run>
```

Manifest: `manifest_version` 1 and `service_components` holding **exactly one** entry with `code`,
`description`, `mode`, `leg`, `category`, `cost_type`, `cost_source`, `unit`, `audience`, `is_active`
and `evidence`. Every field is explicit.

Rules:

- Dry run default; outcomes are `CREATE`, `REUSE`, `CONFLICT`; only `CREATE` writes.
- Apply is atomic, idempotent, insert-only and bound to the reviewed sha256; the operator and the
  manifest `evidence` appear in the output.
- The code must equal an existing active legacy `ProductCode` **and** an active
  `CommercialProductCode` mirroring it.
- The proposed fields must equal what `sync_v4_components` derives for that ProductCode (leg, category,
  description, unit, mode, cost type and source, active). A later broad sync is then a no-op for the
  row. A test runs the real command to keep that true.
- Columns the manifest does not state take model defaults and are compared on `REUSE`; a stored row
  with any other value is a `CONFLICT`, never updated.
- A description already used by another component is a `CONFLICT` (descriptions are unique).
- No other `ServiceComponent`, ProductCode, rate, FX, or pricing row is touched.

## 3. Runtime effect

None. Both commands are management commands that nothing calls. The B3C validator gained an opt-in
mode and shared conflict helpers; its default behaviour and output are unchanged. A created
`ServiceComponent` is looked up by code or id only for charges the engine already emits, and the
engine emits nothing for a ProductCode that has no legacy rate rows, so adding the row changes no
quote until a rate is wired to that ProductCode in a separate gate. It would appear in the read-only
`/api/v3/services/components` listing.
