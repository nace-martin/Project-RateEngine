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
                         AUD: PGK / TT BUY, rounded, then x (1 + export CAF), rounded
                         audit_metadata: conversions, commercial_convention, rate_matrix_export
       -> ServiceComponent twin check (missing twin = failure, never a dropped line)
       -> existing line conversion (approved-convention path, as import already uses)
```

Locked rules enforced: SELL is PGK only and receives no margin; AUD is `(PGK SELL / TT BUY) x 1.10`
with the CAF as a separate uplift applied only on an actual conversion; FX is the stored AUD/PGK TT BUY
from `FxMarketRate` under the policy source priority with a hard 5-day maximum age (stricter of policy and
5 days); missing, stale, ambiguous, inverse-only and cross-only FX fails closed; GST is the
CommercialProductCode treatment (must equal the ProductCode the classifier reads) at the policy
`gst_standard_percent`; percentage-of-product dependants are computed in PGK, then converted.

Supported mechanics: TIERED_WEIGHT with selected-tier `min_charge`, line minimum and maximum, PER_KG,
FLAT, additive flat (security), percentage-of-product, pickup cap and pickup FSC dependency. An unknown
basis, a non-PGK tariff, a CPC/GST mismatch or a missing CPC raises.

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
