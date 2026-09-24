# Pricing Rules Reference

Quick reference for RateEngine pricing logic.

## Core Parameters

| Parameter | Value | Method / Semantics |
|-----------|-------|--------------------|
| Margin | 20% | MARKUP_ON_COST (`Cost × (1 + Margin)`) |
| CAF Import | 5% | Bank TT BUY deduction |
| CAF Export | 10% | Bank TT SELL addition |
| Standard GST | 10% | Domestic / taxable scope |

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

```
FCY Cost → × FX_BUY → × (1 + CAF) → apply_margin(Cost) → PGK Sell
```

## Quote Currency Authority

Quote output currency is determined by `backend/quotes/currency_rules.py::determine_quote_currency()` and verified by `backend/quotes/tests/test_currency_rules.py`. Do not define a separate payment-term/currency matrix here or in downstream schemas.
