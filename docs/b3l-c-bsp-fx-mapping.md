# Pilot Gate B3L-C: BSP TT BUY / TT SELL mapping

Status: mapping confirmed from source evidence; loader and provider corrected. No rate was loaded.

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

| Normalized | Source | AUD value | Used for |
|---|---|---|---|
| TT BUY (bank buys FCY) | 1 / TT Buy | 3.10945274 | PGK amount to FCY customer quote (÷ TT BUY) |
| TT SELL (bank sells FCY) | 1 / TT Sell | 3.26157860 | FCY supplier cost to PGK (× TT SELL) |

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

No schema change. The pricing engine and resolver were already correct for bank-side storage (supplier
cost at stored `tt_sell`, customer quote at stored `tt_buy`; inverse pairs swap sides explicitly).

## Residual points for human awareness

- The provider page has no written definition of "TT Buy / TT Sell". The mapping above is the standard
  bank-side reading, supported by the notes-column spread. A BSP-published definition would settle it
  beyond inference; the guards (heading, completeness, `tt_sell >= tt_buy`) fail closed if the page changes.
- Stored values previously loaded by the old mapping, if any exist in a hosted database, would be
  side-swapped. They were never loadable from real BSP data (the guard rejected it), so none are
  expected; verify before relying on any `bsp_html` row loaded before this change.
