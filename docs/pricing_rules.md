# Pricing Rules Reference

Quick reference for RateEngine pricing logic.

## Core Parameters

| Parameter | Value |
|-----------|-------|
| Margin | 20% |
| CAF Import | 5% |
| CAF Export | 10% |

## Scenario Quick Reference

| Scenario | Direction | Payment | Scope | Currency | CAF |
|----------|-----------|---------|-------|----------|-----|
| Import Collect D2D | IMPORT | COLLECT | D2D | PGK | 5% |
| Import Collect A2D | IMPORT | COLLECT | A2D | PGK | 5% |
| Import Prepaid A2D | IMPORT | PREPAID | A2D | AUD/USD* | 5% |
| Export Prepaid D2A | EXPORT | PREPAID | D2A | PGK | 10% |
| Export Prepaid D2D | EXPORT | PREPAID | D2D | PGK | 10% |
| Export Collect D2A | EXPORT | COLLECT | D2A | FCY | 10% |

*AU origin → AUD, else → USD

## FX Pipeline

```
FCY Cost → × FX_BUY → × (1 + CAF) → × (1 + Margin) → PGK Sell
```

## Currency Decision

- **COLLECT** (local payer) → Quote in **PGK**
- **PREPAID** by overseas party:
  - Import A2D → **AUD** (AU) or **USD** (else)
  - Export D2A → **FCY** (destination currency)
