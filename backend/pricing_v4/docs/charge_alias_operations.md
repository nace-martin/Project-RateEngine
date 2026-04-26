# Charge Alias Operations

## Baseline vs operational aliases

- `seed_charge_aliases` remains the bootstrap tool for trusted baseline aliases only.
- Pack A is the current baseline set.
- Pack B stays inactive until rows are explicitly reviewed and promoted.
- Ongoing agent- or lane-specific growth should be managed in the database, not by expanding the seed file indefinitely.

## Operational states

`ChargeAlias` now carries two operational fields:

- `alias_source`
  - `SEED`: baseline bootstrap alias
  - `ADMIN`: directly managed in Django admin
  - `MANUAL_REVIEW`: candidate derived from repeated manual review patterns
- `review_status`
  - `APPROVED`: eligible to be active
  - `CANDIDATE`: under review, should stay inactive
  - `REJECTED`: explicitly not approved for live matching

Guardrail:

- only `APPROVED` aliases may be active

## Promotion path

1. SPOT review accumulates recurring `UNMAPPED` and manual-resolution history on `SPEChargeLineDB`.
2. `summarize_charge_alias_activity` surfaces repeated manual mappings and recurring unmapped labels.
3. `create_charge_alias_candidates --dry-run` previews inactive candidate aliases from repeated, stable manual resolutions.
4. `create_charge_alias_candidates` writes inactive `MANUAL_REVIEW` / `CANDIDATE` aliases only when no equivalent or conflicting alias already exists.
5. Ops reviews the candidate in Django admin.
4. If the alias is safe:
   - create or edit the alias in admin
   - set `review_status=APPROVED`
   - keep priority explicit
   - activate only after review
6. If the alias is risky or overly broad:
   - keep it inactive with `review_status=CANDIDATE` or `REJECTED`

## Scope discipline

- Do not add broad fallback aliases without explicit review.
- Prefer exact aliases before pattern aliases.
- Keep priority semantics intact: lower number wins.
- Agent- or origin-specific patterns should be justified by repeated observed labels, not preloaded speculatively.
