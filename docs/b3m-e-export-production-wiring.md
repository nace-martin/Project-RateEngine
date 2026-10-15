# Pilot Gate B3M-E: Rate Matrix export pricing in production, behind a flag

Status: implemented, **OFF by default**, local DB only. Hosted DB, import pricing, SPOT and corridor
automation are untouched. This file records behaviour, the operating runbook and the known limits.

## Scope (exact)

Rate Matrix export pricing is selected only for **AIR / EXPORT / General Cargo**, lane **POM to BNE** or
**POM to SYD**, service scope **A2A** or **D2A**, and one of:

| Payment term | Quote currency |
|---|---|
| PREPAID | PGK |
| COLLECT | AUD |

Anything else prices on the unchanged legacy export engine, with the reason recorded in the quote audit
metadata (`export_pricing_path`). Also legacy: dangerous goods, a non-GCR commodity, a SPOT envelope, a
preferred agent or carrier, a non-PGK BUY currency, manual overrides or spot rates.

## Feature flag

| | |
|---|---|
| Setting / environment variable | `RATE_MATRIX_EXPORT_PRICING_ENABLED` |
| Default | OFF (unset, empty or anything other than the literal `true`) |
| Flag OFF | The legacy path runs; the new module is not reached and no new metadata is recorded. |
| Flag ON, in scope | Rate Matrix mode. **No fallback to legacy rates**: an unresolved lookup raises and the quote fails closed. |
| Flag ON, out of scope | Legacy path, with `export_pricing_path.reason = OUT_OF_SCOPE: ...`. |

Selection is made once, before pricing, in `pricing_v4/services/rate_matrix_export_pricing.py`
(`select_rate_matrix_export_pricing`). The adapter hook is `PricingServiceV4Adapter._calculate_rate_matrix_export`.

## Architecture

```
PricingServiceV4Adapter._calculate_standard_lines (EXPORT)
  -> select_rate_matrix_export_pricing(...)             flag + exact lane/scope guard
       not selected -> legacy ExportPricingEngine (unchanged)
       selected     -> RateMatrixExportPricingEngine    (subclass of ExportPricingEngine)
                         BUY / SELL: Rate Matrix resolver (exact match only; native PGK)
                         rules: production rate rules (core.charge_rules)
                         AUD: PGK / TT SELL, rounded, then x (1 + export CAF), rounded
                         audit_metadata: conversions, commercial_convention, rate_matrix_export
       -> ServiceComponent twin check (missing twin = failure, never a dropped line)
       -> existing line conversion (approved-convention path, as import already uses)
```

Locked rules enforced: SELL is PGK only and receives no margin; AUD is `(PGK SELL / TT SELL) x 1.10`
(= PGK x published BSP TT Sell x 1.10; BSP converts PGK to FCY at TT Sell) with the CAF as a separate
uplift applied only on an actual conversion; FX is the stored AUD/PGK TT SELL
from `FxMarketRate` under the policy source priority with a hard 5-day maximum age (stricter of policy and
5 days); missing, stale, ambiguous, inverse-only and cross-only FX fails closed; GST is the
CommercialProductCode treatment (must equal the ProductCode the classifier reads) at the policy
`gst_standard_percent`; percentage-of-product dependants are computed in PGK, then converted.

Supported mechanics: TIERED_WEIGHT with selected-tier `min_charge`, line minimum and maximum, PER_KG,
FLAT, additive flat (security), percentage-of-product, pickup cap and pickup FSC dependency. An unknown
basis, a non-PGK tariff, a CPC/GST mismatch or a missing CPC raises.

## BSP FX-side correction (amendment to this PR)

BSP's published rates and calculator (2026-10-14, AUD TT Buy 0.3215 / TT Sell 0.3065 per PGK) show that
PGK to FCY uses **TT Sell** and FCY to PGK uses **TT Buy**. The first version of this PR, and Pilot Gate
B3L-B before it, had the sides reversed. Corrected here:

| Conversion | Side | Stored formula (PGK per FCY) | CAF |
|---|---|---|---|
| PGK to FCY (export, and import PREPAID) | TT SELL | FCY = PGK ÷ TT SELL | + CAF after pure conversion |
| FCY to PGK (import cost) | TT BUY | PGK = FCY × TT BUY ÷ (1 − import CAF) | reduces the published TT Buy |

Worked: PGK 1,000 to AUD = 1000 × 0.3065 = 306.50 × 1.10 = **AUD 337.15**; AUD 100 to PGK =
100 ÷ (0.3215 × 0.95) = **K 327.41**.

- `pricing_v4/services/fx_conventions.py` is the single definition of the sides and CAF operations.
- `ImportPricingEngine._convert_with_caf` now converts FCY to PGK at TT BUY with the CAF as a rate
  reduction, PGK to FCY at TT SELL with the CAF as an uplift, and fails closed on FCY to FCY.
- `RateMatrixExportPricingEngine` and the export shadow convert PGK to AUD at TT SELL.
- Evidence: every conversion records `legs[].side` (`TT_BUY` / `TT_SELL`), `caf_operation`
  (`PUBLISHED_RATE_REDUCED` / `UPLIFTED_AFTER_FX`) and, for FCY to PGK, `effective_rate_after_caf`; the
  adapter's `fx_audit` reports them.
- Policy: migration `0047` adds `TO_PGK_RATE_REDUCTION_FROM_PGK_UPLIFT` and
  `FCY_TO_PGK_AT_TT_BUY_PGK_TO_FCY_AT_TT_SELL` and relabels the old values as superseded. The historical
  row `COMMERCIAL-POLICY-2026-10-11` is not edited; a conversion under it now fails closed
  (`SupersededFxConventionError`). The new version is the manifest
  `policy_manifests/commercial-policy-2026-10-14.json` (dry run READY, sha256
  `ff978d4192e88e4816002c8506b874c790bb81bdec72c8cb04d46001ad30456f`), **not applied** to any database.
- Legacy conventions (`LEGACY_RATE_ADJUSTMENT` / `LEGACY_COST_AT_TT_BUY`), the legacy export engine and the
  BSP loader are unchanged.

## Native SELL precedence (amendment to this PR)

Pricing precedence for an explicit SELL, in Rate Matrix mode:

1. Exact SELL tariff in the customer quote currency: used directly. No FX, no CAF, no margin.
2. Otherwise, only where an approved rule explicitly allows it, the PGK SELL converted PGK to FCY at TT
   SELL with the export CAF uplift (10%). Today the only such rule is the B3M-E export pilot (AUD COLLECT
   from the PGK export tariffs).
3. Otherwise the line is a visible missing rate (`is_rate_missing`); the quote is incomplete. Nothing is
   silently converted from PGK.

- Export (`RateMatrixExportPricingEngine`): a native quote-currency SELL is resolved first; lines priced
  from it carry no conversion, no PGK equivalent (`pgk_equivalent_complete = false`), and are listed in
  `rate_matrix_export.native_quote_currency_sell`. A percentage dependant whose base is in another
  currency fails closed (`NATIVE_CURRENCY_MIX`).
- Import (`MatrixShadowImportEngine`, the only import Rate Matrix path; shadow only): destination SELL is
  resolved in the quote currency only and never converted; a non-native tariff fails closed
  (`SELL_NOT_NATIVE`); a missing rate is a visible gap and the legacy PGK 300 customs-brokerage default is
  not inherited.
- Legacy production import pricing (LocalSellRate with the PREPAID PGK fallback) is unchanged.
- Real local data (B3I POM destination sheets, read-only check 2026-10-14): IMP-AGENCY-DEST,
  IMP-CARTAGE-DEST, IMP-CLEAR, IMP-DOC-DEST, IMP-FSC-CARTAGE-DEST, IMP-HANDLING-DEST and IMP-TERM-DEST each
  resolve an exact native SELL in PGK, AUD and USD for COLLECT and PREPAID, so none needs a conversion.
- Import PGK to FCY conversions (engine `_convert_with_caf`) now apply the export CAF (10%) as the uplift,
  per the approved rule; FCY to PGK keeps the import CAF 5% rate reduction.

## Weight precision

Tiered pricing accepts at most **four decimal places**. The resolver returns INVALID_CONTEXT above that and
the quote fails closed; nothing is rounded. **Operational consequence:** the adapter's chargeable weight is
the larger of actual weight and `L x W x H / 6000`, which is non-terminating for most dimensions
(for example 50 x 50 x 50 cm is 20.8333... kg). A quote whose volumetric weight is the chargeable weight
and has more than four decimals fails closed in Rate Matrix mode until the Commercial Manager approves a
rounding rule. That rule is deliberately not invented here.

## Provenance

Persisted with the quote totals (`audit_metadata_json`):

- `export_pricing_path`: path, flag state and the selection reason.
- `rate_matrix_export`: lane, scope, chargeable weight, policy code and, for every tariff used, the side,
  sheet name and version, line id, source reference, supplier, basis, rates, minimums, tiers and validity.
- `fx_audit`: the TT BUY leg (rate, source, role, effective date, age, policy) and each conversion
  (pure FX, CAF percent and amount, commercial amount).

Customer-facing error text never carries a charge code or sheet; `RateMatrixExportPricingError.code` and
`.message` hold the technical detail for logs.

## ServiceComponent twins

`python manage.py ensure_export_pilot_service_components` plans the twelve same-code twins (dry run by
default). `--apply --operator <user> --reviewed-sha256 <combined hash>` creates only the missing ones
atomically; stored rows are never updated and a conflict writes nothing. It reuses the single-component
loader and derives each row exactly as `sync_v4_components` would. Local result: `CREATE 0, REUSE 12`.

## Operating runbook

1. Confirm the master data and tariff manifests are applied and the twins are `REUSE 12`.
2. Confirm a usable AUD/PGK TT BUY row exists (it must be at most five days old on the quote date).
3. Set `RATE_MATRIX_EXPORT_PRICING_ENABLED=true` for the UAT environment only.
4. Quote POM to BNE/SYD, A2A/D2A, PREPAID and COLLECT; check `export_pricing_path` and `rate_matrix_export`.
5. Rollback: unset the variable. The legacy path is the default and is unchanged.

## Known limits (record, do not hide)

- Volumetric chargeable weights with more than four decimals fail closed (above).
- Legacy AUD COLLECT used native AUD origin tariffs where they existed; Rate Matrix mode has no AUD SELL
  tariff by rule, so those lines are the converted PGK SELL. AUD totals therefore change (see the PR).
- A preferred agent or carrier selection keeps the quote on the legacy engine.
- FX is usable only within five days of the quote date; the BSP rate dated 2026-10-12 is usable through
  2026-10-17.
- The shadow harness (`shadow_price_rate_matrix_export`) now also prices every scenario through the
  production Rate Matrix engine (`production_rate_matrix_parity`) and requires an exact match.
