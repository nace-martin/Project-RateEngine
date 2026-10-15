# Pilot Gate B3L-C: BSP TT BUY / TT SELL mapping

Status: mapping confirmed from source evidence; loader and provider corrected. No rate was loaded.

> **Corrected in Pilot Gate B3M-E (2026-10-14).** The stored values below are right and unchanged. The
> *conversion sides* this page originally named were reversed. BSP's own calculator (screenshots dated
> 2026-10-14, AUD TT Buy 0.3215 / TT Sell 0.3065) converts **PGK to AUD at TT Sell** and **AUD to PGK at
> TT Buy**. See "Conversion sides (corrected)" below and `pricing_v4/services/fx_conventions.py`.

## What BSP publishes

The BSP exchange-rate page is headed "Exchange rates for Kina" and lists, per currency, five figures as
**foreign currency per 1 PGK**:

| Column | AUD, 2026-10-12 | Meaning (bank side) |
|---|---|---|
| Notes Buy | 0.3434 | bank buys banknotes |
| TT Buy | 0.3216 | bank buys FCY by telegraphic transfer |
| A/M Buy | 0.0000 | not published |
| TT Sell | 0.3066 | bank sells FCY by telegraphic transfer |
| Notes Sell | 0.2854 | bank sells banknotes |

## Why the sides are bank sides

The ordering Notes Buy > TT Buy > TT Sell > Notes Sell (AUD per PGK) is the bank's usual spread: it pays
least PGK per AUD for banknotes it buys, a little more for TT, charges a little more than that for TT it
sells, and most for banknotes it sells. Read from the customer's side the notes columns would be
favourable to the customer, which is not possible. The mapping therefore does not rest on the two TT
figures' numeric order alone.

## Normalized storage (PGK per 1 FCY)

Inverting FCY-per-PGK reverses the numeric order but not the bank side:

| Normalized | Source | AUD value | Used for (corrected B3M-E) |
|---|---|---|---|
| TT BUY (bank buys FCY) | 1 / TT Buy | 3.10945274 | FCY to PGK (× TT BUY, import CAF reduces the rate) |
| TT SELL (bank sells FCY) | 1 / TT Sell | 3.26157860 | PGK to FCY (÷ TT SELL, then export CAF uplift) |

`tt_sell >= tt_buy` therefore holds for genuine BSP data and the loader guard is correct.

## Root cause

Both loader paths flipped the side while inverting:

- `bsp_html` (FCY:PGK) labelled `1 / TT Sell` as BUY and `1 / TT Buy` as SELL (a customer-side view).
- `fetch_fx` (PGK:FCY, the orientation used by `/api/fx/refresh`) set `tt_buy = 1 / TT Sell` and
  `tt_sell = 1 / TT Buy`.

Either way the stored TT BUY was the higher figure, the `TT SELL is below TT BUY` guard rejected real
data, and no real BSP rate could be loaded. The guard did its job; the mapping was wrong.

## Changes

- `core/fx_providers/bsp_html.py`: FCY:PGK rows now keep the bank side (BUY = 1 / TT Buy, SELL = 1 / TT
  Sell) at 8 decimal places, so the two pair orientations yield identical canonical values; the page
  heading must read "for Kina" or the parse fails closed.
- `core/management/commands/fetch_fx.py`: PGK:FCY rows invert without swapping sides.
- Tests: `pricing_v4/tests/test_b3lc_bsp_fx_mapping.py`.

No schema change. The resolver was already correct for bank-side storage (inverse pairs swap sides
explicitly, so PGK/AUD TT BUY = 1 / stored AUD/PGK TT SELL and the economics of both orientations agree).

The original note here said the engine was correct with supplier cost at stored `tt_sell` and customer
quote at stored `tt_buy`. That was wrong; see the next section.

## Conversion sides (corrected, Pilot Gate B3M-E)

Source: BSP published AUD rates and the BSP calculator, 2026-10-14. Published: TT Buy 0.3215, TT Sell
0.3065 AUD per PGK. Stored (unchanged rule): TT BUY = 1 / 0.3215 = 3.11041991; TT SELL = 1 / 0.3065 =
3.26264274.

| Conversion | Side | Published orientation | Stored (PGK per FCY) | CAF |
|---|---|---|---|---|
| PGK to FCY | TT SELL | FCY = PGK × TT Sell | FCY = PGK ÷ TT SELL | export CAF +10% after conversion |
| FCY to PGK | TT BUY | PGK = FCY ÷ (TT Buy × 0.95) | PGK = FCY × TT BUY ÷ 0.95 | import CAF 5% reduces the published rate |

Worked examples (tested in `test_b3lc_bsp_fx_mapping.py::TestBspCalculatorWorkedExamples`):

- PGK 1,000 to AUD: 1000 × 0.3065 = 306.50; × 1.10 = **AUD 337.15**.
- AUD 100 to PGK: 0.3215 × 0.95 = 0.305425; 100 ÷ 0.305425 = **K 327.41**. This is a rate reduction; a
  pure conversion × 1.05 (K 326.59) is not equivalent.

The loader and stored values are unchanged; no side was swapped in storage. The policy convention that
encoded the reversed sides (`COST_AT_TT_SELL`) is superseded by `FCY_TO_PGK_AT_TT_BUY_PGK_TO_FCY_AT_TT_SELL`
through a new policy version (see `docs/b3m-e-export-production-wiring.md`).

## Residual points for human awareness

- The provider page has no written definition of "TT Buy / TT Sell". The mapping above is the standard
  bank-side reading, supported by the notes-column spread. A BSP-published definition would settle it
  beyond inference; the guards (heading, completeness, `tt_sell >= tt_buy`) fail closed if the page changes.
- Stored values previously loaded by the old mapping, if any exist in a hosted database, would be
  side-swapped. They were never loadable from real BSP data (the guard rejected it), so none are
  expected; verify before relying on any `bsp_html` row loaded before this change.
