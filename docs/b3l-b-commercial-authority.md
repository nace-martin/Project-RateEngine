# Pilot Gate B3L-B: approved commercial authority and FX controls

Status: implemented behind a policy version. Nothing here changes any quote until the new policy
version is applied by an operator (see "Apply plan"). No FX rate was seeded and no tariff changed.

## Approved decisions (source: Gate B3L-A decision pack, operator-approved)

| Decision | Value |
|---|---|
| Policy effective from | 2026-10-11 |
| Import CAF | 5.00%, a separate uplift **after** pure FX, only when a currency conversion actually occurs |
| Margin | `TARGET_GROSS_MARGIN` 16.67%, cost-plus lines only, after FX and CAF; explicit Rate Matrix SELL is not margined. Replaces the launch 20% `MARKUP_ON_COST` |
| GST | 10.00% standard; classes STANDARD / ZERO_RATED / EXEMPT. Class authority `CommercialProductCode.gst_treatment`; rate authority `CommercialTermsPolicy.gst_standard_percent`. International ORIGIN and FREIGHT legs on imports are 0% |
| FX | `FxMarketRate` is the authority. BSP primary; MANUAL only when no suitable BSP rate; latest effective on or before the quote date; max age 5 calendar days; stale, conflicting or ambiguous fails closed; no extra spread |
| FX sides | FCY supplier cost to PGK: TT SELL. PGK amount to a customer FCY quote: TT BUY (PGK per FCY divided into the PGK amount). Sides are never silently swapped because a pair is stored inverted |

## How it is implemented

The calculation conventions are data on the policy row, not code constants:

| Field on `CommercialTermsPolicy` | Legacy default | Approved value |
|---|---|---|
| `caf_method` | `LEGACY_RATE_ADJUSTMENT` | `UPLIFT_AFTER_FX` |
| `fx_side_convention` | `LEGACY_COST_AT_TT_BUY` | `COST_AT_TT_SELL` |
| `fx_max_age_days` | null (no limit) | 5 |
| `fx_primary_source` / `fx_fallback_source` | blank | `bsp_html` / `MANUAL` |
| `margin_method` / `margin_percent` | `MARKUP_ON_COST` / 20.00 | `TARGET_GROSS_MARGIN` / 16.67 |

Migration `0045_b3lb_policy_calculation_conventions` adds the columns with the legacy defaults, so
merging it is behaviour-neutral: existing policy rows keep today's conventions until a new version is
applied.

- **Engine** (`import_engine.py`): `_convert_with_caf` is the single conversion path under the approved
  convention. It converts at the market rate, then applies CAF as a separate uplift, and records
  evidence (`audit_metadata["conversions"]`). An FCY *sell* amount to PGK has no approved side and fails
  closed. Per-line `cost_pgk` / `sell_pgk` / `sell_pgk_incl_gst` are the canonical PGK equivalents; they
  are `None` when no conversion happened.
- **Adapter**: no FX is resolved up front. FX is needed only when the engine converts. The persisted
  PGK equivalents and the FX audit come from the engine's own conversion evidence, so audit, lines and
  totals share one conversion result.
- **FX resolver**: policy-driven source priority and staleness, with provenance on every result
  (`source_role`, `age_days`, `max_age_days`, `policy_code`). Legacy policies resolve as before.
- **GST**: the standard rate is read from the resolved policy and fails closed if the policy is missing,
  ambiguous or incomplete. `quotes.tax_policy.PNG_GST_REFERENCE_RATE` is a named reference value only;
  the engines, adapter and PDF fallback no longer use a literal 10%.

Worked example (synthetic, AUD 100 supplier cost, TT SELL 2.60, CAF 5%, margin 16.67%):

```
pure FX      100.00 AUD x 2.60             = 260.00 PGK
CAF uplift   260.00 x 1.05                 = 273.00 PGK   (CAF 13.00, separate from the rate)
margin       273.00 / (1 - 0.1667)         = 327.61 PGK   (gross margin 16.67%)
GST          327.61 x 10% (STANDARD class) =  32.76
```

## Apply plan (not executed)

Controlled tooling: `python manage.py load_commercial_terms_policy <manifest.json>`.

1. Dry run (default, writes nothing). Review the planned supersede and note `manifest_sha256`:
   `python manage.py load_commercial_terms_policy policy.json`
2. Apply (atomic; requires an active operator and the reviewed hash):
   `python manage.py load_commercial_terms_policy policy.json --apply --operator <user> --reviewed-sha256 <sha>`

The manifest names a **new** policy code with `valid_from` 2026-10-11 and ends the old row
(`LAUNCH-POLICY-2026`, `expected_valid_until: null`) on 2026-10-10. The old row is never edited in place
beyond ending its open-ended validity. Applying twice writes nothing. After apply the loader proves that
exactly one policy resolves on 2026-10-10, 2026-10-11 and a year later.

Rollback (documented, not automated): in one transaction set the old policy's `valid_until` back to
null and delete the new policy row. Quotes already persisted keep their stored values.

Preconditions before applying: BSP rates loaded for the quote dates in use (the `fetch_fx` loader), and
business sign-off of the shadow report.

## Known limits

- Under legacy conventions a quote that needs no conversion still prices when no FX rate exists; its PGK
  equivalents are reported as unavailable (0.00, `pgk_equivalent_complete = false`) rather than invented.
  Downstream reporting that sums `total_sell_pgk` for FCY quotes needs a decision on how to report quotes
  with no PGK equivalent.
- A destination SELL tariff stored only in PGK on a PREPAID AUD quote genuinely converts and needs FX.
  In the local data this is `IMP-LOADING-DEST`, so real PREPAID AUD scenarios still need an AUD/PGK rate.
- **BSP side labelling (resolved in B3L-C).** The loader inverted the bank side, so `fetch_fx` rejected real
  BSP data with `TT SELL is below TT BUY`. See `docs/b3l-c-bsp-fx-mapping.md`: stored TT BUY is
  `1 / BSP TT Buy` and stored TT SELL is `1 / BSP TT Sell`, so supplier cost converts at the higher rate.
