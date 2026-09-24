# Pricing Rules Reference

Quick reference for RateEngine pricing logic.

## Core Parameters

| Parameter | Value | Method / Semantics |
|-----------|-------|--------------------|
| Margin | 20% | MARKUP_ON_COST (`Cost × (1 + Margin)`) |
| CAF Import | 5% | Bank TT BUY / SELL deduction as applicable to Import conversion |
| CAF Export | 10% | Bank TT SELL addition for Export customer-currency conversion |
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

## FX Market Authority

`core.FxMarketRate` is the sole market-FX authority for new quote calculations.
`FxSnapshot` is retained as historical quote evidence and is not the source of current market rates.

Canonical market facts are stored as **FCY/PGK**:

- `base_currency = FCY`
- `quote_currency = PGK`
- the numeric rate means **PGK per 1 FCY**

Example: `AUD/PGK TT SELL = 2.5200` means K2.5200 per AUD 1.

Resolution rules:

1. Use the latest published market fact whose `effective_date <= quote_date`.
2. Never use a future-dated rate.
3. If the inverse pair is used, invert mathematically and swap BUY/SELL sides:
   - inverse BUY = `1 / original SELL`
   - inverse SELL = `1 / original BUY`
4. Cross-currency conversion resolves through PGK.
5. PGK → PGK (or any same-currency conversion) is identity and requires no FX row.
6. If multiple sources compete for the same latest pair/date and no source priority is approved, fail closed rather than selecting arbitrarily.
7. Missing required foreign-currency FX fails closed. There are no fabricated `0.35`, `0.36`, `2.50`, `2.78`, or foreign-currency `1.0` defaults.
8. The current 24-hour age check is an operational warning only. No hard maximum staleness cutoff is assumed until explicitly approved.

Pure market FX and CAF are separate facts. CAF is applied only in the pricing layer after the market rate resolves.

### Import conversion

For FCY cost → PGK using TT BUY:

`PGK = FCY × (TT_BUY × (1 - Import CAF))`

For PGK → FCY using TT SELL:

`FCY = PGK ÷ (TT_SELL × (1 - Import CAF))`

### Export conversion

For PGK → customer FCY using TT SELL:

`FCY = PGK ÷ (TT_SELL × (1 + Export CAF))`

## Quote Currency Authority

Quote output currency is determined by `backend/quotes/currency_rules.py::determine_quote_currency()` and verified by `backend/quotes/tests/test_currency_rules.py`. Do not define a separate payment-term/currency matrix here or in downstream schemas.
