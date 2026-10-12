# Pricing Rules Reference

Quick reference for RateEngine pricing logic.

## Core Parameters

Two calculation conventions exist, selected by the resolved `CommercialTermsPolicy` row. Which one is
in force on a date is decided by the policy, not by code. See
`docs/b3l-b-commercial-authority.md` for the approved convention, its effective date and how it is
introduced.

| Parameter | Legacy convention (`LAUNCH-POLICY-2026`) | Approved convention (new version, effective 2026-10-11) |
|-----------|-------|--------------------|
| Margin | 20% `MARKUP_ON_COST` (`Cost x (1 + Margin)`) | 16.67% `TARGET_GROSS_MARGIN` (`Cost / (1 - Margin)`), cost-plus only, after FX and CAF |
| CAF Import | 5%, deducted from the TT BUY rate | 5% uplift applied after pure FX conversion, only when a conversion occurs; never folded into the rate |
| CAF Export | 10%, TT SELL addition | unchanged by this gate |
| FX side, FCY supplier cost to PGK | TT BUY | TT SELL |
| FX side, PGK amount to FCY customer quote | TT SELL | TT BUY |
| Standard GST | 10% | 10%, read from `CommercialTermsPolicy.gst_standard_percent` |
| FX source / age | any `FxMarketRate`, no age limit | BSP primary, MANUAL only when BSP is unsuitable, max 5 calendar days, stale fails closed |

### Margin Semantics (`CommercialTermsPolicy`)

RateEngine explicitly separates margin percentage from calculation method:
- `margin_percent`: Numeric rate (e.g. 20.00%).
- `margin_method`:
  - `MARKUP_ON_COST` (Active canonical launch policy): $\text{SELL} = \text{Cost} \times (1 + \text{margin\_rate})$. A K100 cost at 20% markup yields K120 sell.
  - `TARGET_GROSS_MARGIN` (Supported target): $\text{SELL} = \frac{\text{Cost}}{1 - \text{margin\_rate}}$. A K100 cost at 20% target gross margin yields K125 sell.

RateEngine enforces:
- Approved direct `SELL` rates are never re-margined.
- Cost-derived pricing without an active commercial margin fails closed (no silent or hardcoded fallbacks).

## Scenario Quick Reference

| Scenario | Direction | Payment | Scope | Currency | CAF |
|----------|-----------|---------|-------|----------|-----|
| Import Collect D2D | IMPORT | COLLECT | D2D | PGK | 5% |
| Import Collect A2D | IMPORT | COLLECT | A2D | PGK | 5% |
| Import Prepaid A2D | IMPORT | PREPAID | A2D | AUD/USD* | 5% |
| Export Prepaid D2A | EXPORT | PREPAID | D2A | PGK | 10% |
| Export Prepaid D2D | EXPORT | PREPAID | D2D | PGK | 10% |
| Export Collect D2A | EXPORT | COLLECT | D2A | FCY | 10% |

*AU origin → AUD, else → USD for Import Prepaid. Export Collect uses the destination FCY (AUD for AU, otherwise USD under the current policy).

## FX Pipeline

Legacy convention:

```
FCY Cost -> x FX_BUY -> x (1 + CAF) -> apply_margin(Cost) -> PGK Sell
```

Approved convention (policy `caf_method = UPLIFT_AFTER_FX`):

```
native cost -> x market FX (only if a conversion is needed; TT SELL for FCY cost -> PGK)
            -> x (1 + CAF) (only if a conversion happened)
            -> / (1 - target gross margin) (cost-plus lines only; explicit SELL tariffs skip this)
            -> GST on the sell amount by tax class
```

A quote needs FX only when it actually converts a currency. A PREPAID AUD import whose costs and
destination SELL tariffs are all AUD prices without any AUD/PGK rate.

## Quote Currency Authority

Quote output currency is determined by `backend/quotes/currency_rules.py::determine_quote_currency()` and verified by `backend/quotes/tests/test_currency_rules.py`. Do not define a separate payment-term/currency matrix here or in downstream schemas.
