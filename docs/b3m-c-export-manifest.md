# Pilot Gate B3M-C: export manifests and export shadow proof

Status: manifests prepared and dry-run verified; read-only shadow built; per-tier minimum added to the Rate
Matrix contract. **Nothing is applied, no Rate Matrix tariff is live, and no production path reads the Rate
Matrix.** Scope: AIR / EXPORT / direct / General Cargo, POM to BNE and POM to SYD.

## Locked commercial rules (Commercial Manager, 2026-10-12)

| Rule | Value |
|---|---|
| BUY freight | Existing `ExportCOGS` for BNE and SYD, PGK, approved 2026-10-12 until superseded; supplier Air Niugini (PX) |
| SELL freight | **Current EFM PGK Export Rate Card**; Commercial Manager continuation approved 2026-10-12 until superseded despite the printed 2025 expiry; PGK tariffs only, no AUD SELL tariff |
| Validity | Every SELL and BUY sheet is `valid_from = 2026-10-12`, `valid_until = null`. Printed and stored legacy dates are kept in `source_reference` as provenance, not as authority |
| Database-only carry-forward | `EXP-HANDLE` (SELL 50, BUY 35) and `EXP-FSC-AIR` (SELL 0.80/kg) are Commercial Manager-approved Pilot carry-forward as at 2026-10-12. They are labelled `DATABASE-ONLY, no external document`; no documentary evidence is implied |
| AUD quote | `AUD SELL = (PGK SELL / TT BUY) x 1.10` from `FxMarketRate`; export CAF 10% applies only when a conversion occurs; no conversion means no FX and no CAF |
| Margin | An explicit SELL tariff receives no additional margin |

Export CAF 10% is approved by this instruction for the AUD conversion of explicit PGK SELL only. It is not a
margin and is not a rate adjustment.

### Current export freight SELL (PGK per kg, minimum K180)

| Break | POM-BNE | POM-SYD |
|---|---|---|
| under 45 kg | 7.20 | 9.15 |
| 45 kg | 7.20 | 9.15 |
| 100 kg | 6.75 | 8.60 |
| 200 kg | 6.50 | 8.20 |
| 500 kg and over | 6.15 | 7.70 |

The legacy `ExportSellRate` rows (#307 and #319: minimum K200; BNE 7.90 / 7.40 / 7.15 / 6.75; SYD 10.00 / 9.40 /
8.90 / 8.50) were a stale transcription and are **superseded**. They are not promoted and not forced to match.

## Manifests (`backend/pricing_v4/rate_matrix_manifests/`)

| File | Loader / tool | Role |
|---|---|---|
| `export-pilot-master-data-2026-10-12.json` | `load_rate_matrix_master_data` | PX carrier party (legal name **Air Niugini Limited**, trade name Air Niugini, PG, CARRIER; evidence: existing General Sales Agency) and 12 mirrors; GST and category approval flags false, so the loader reports BLOCKED |
| `export-pilot-tariffs-2026-10-12.json` | `load_rate_matrix_manifest` | 3 BUY and 4 SELL sheets, 21 lines, 21 tiers, native PGK |
| `export-approved-differences-2026-10-12.json` | `shadow_price_rate_matrix_export --approved-differences` | Approved-authority evidence for the differences between legacy rows and the manifest |

All are strict JSON, dry-run by default, and apply only with `--operator` and the reviewed sha256 the dry run
prints. `.gitattributes` pins them `-text` so the hash cannot change on checkout. The master data stays BLOCKED
until the Commercial Manager approves the categories and GST treatments and the file is re-reviewed (its hash
changes).

### Sheets

All sheets: AIR, EXPORT, native PGK, `valid_from` 2026-10-12, `valid_until` null.

| Sheet | Side | Supplier |
|---|---|---|
| Air freight POM-BNE POM-SYD (`EXP-FRT-AIR`), min K160 | BUY | Air Niugini Limited (PX) |
| Terminal charges POM: DOC 35, AWB 35, TERM 35, SCREEN 0.17/kg + 35, BUILDUP per-tier | BUY | Air Niugini Limited (PX) |
| `EXP-HANDLE` 35 (database-only carry-forward) | BUY | Air Niugini Limited (PX) |
| Air freight POM-BNE POM-SYD, min K180, tiers above | SELL | none |
| Origin charges POM: DOC 50, AWB 50, SCREEN 0.20/kg + 45, TERM 50, BUILDUP 0.20/kg min 50, CLEAR 300, AGENCY 250, PICKUP 1.50/kg min 95 cap 500, FSC-PICKUP 10% of PICKUP | SELL | none |
| `EXP-HANDLE` 50 (database-only carry-forward) | SELL | none |
| `EXP-FSC-AIR` 0.80/kg (database-only carry-forward) | SELL | none |

Freight BUY tiers (PGK per kg, minimum K160): BNE 6.30 / 5.90 / 5.70 / 5.40; SYD 8.00 / 7.50 / 7.10 / 6.80 at
0 / 100 / 200 / 500 kg. Payment term is blank (ANY) on every line. Origin SELL charges are unchanged.

## ProductCode mapping

All twelve already exist as legacy `ProductCode` rows; none has a `CommercialProductCode` mirror yet. Categories
are proposals and need Commercial Manager approval; GST treatment equals the legacy ProductCode and the PNG
export rules (`quotes/tax_policy.py`, `enable_export_gst`). Special cargo is excluded.

| Code | Id | Category (proposed) | Basis | GST |
|---|---|---|---|---|
| `EXP-FRT-AIR` | 1001 | FREIGHT | TIERED_WEIGHT | ZERO_RATED |
| `EXP-FSC-AIR` | 1002 | ORIGIN | PER_KG | STANDARD |
| `EXP-DOC` | 1010 | ORIGIN | FLAT | STANDARD |
| `EXP-AWB` | 1011 | ORIGIN | FLAT | STANDARD |
| `EXP-CLEAR` | 1020 | CLEARANCE | FLAT | STANDARD |
| `EXP-AGENCY` | 1021 | ORIGIN | FLAT | STANDARD |
| `EXP-TERM` | 1030 | ORIGIN | FLAT | STANDARD |
| `EXP-BUILDUP` | 1031 | ORIGIN | PER_KG | STANDARD |
| `EXP-HANDLE` | 1032 | ORIGIN | FLAT | STANDARD |
| `EXP-SCREEN` | 1040 | ORIGIN | PER_KG | STANDARD |
| `EXP-PICKUP` | 1050 | ORIGIN | PER_KG | STANDARD |
| `EXP-FSC-PICKUP` | 1060 | ORIGIN | PERCENTAGE | STANDARD |

## Facts reported before inclusion

- **`EXP-HANDLE`**: `local_sell_rates#114` (ANY) and `#139` (PREPAID), POM EXPORT, PGK FIXED 50.00, stored validity
  2026-01-01..2026-12-31; BUY `local_cogs_rates#23` PGK FIXED 35.00, stored validity 2026-01-01..2026-12-31. The PX
  reference file has no handling line. Database-only; Commercial Manager-approved Pilot carry-forward 2026-10-12.
- **`EXP-FSC-AIR`**: `local_sell_rates#206`, POM EXPORT, PGK PER_KG 0.8000, payment term ANY, stored validity
  2025-01-01..2030-12-31 (kept as provenance only). No BUY row and no AUD row. Database-only; Commercial Manager-approved
  Pilot carry-forward 2026-10-12, valid from that date.

## Rate Matrix contract change: per-tier minimum

The locked BUY build-up has a tier-conditional minimum: nil at 0-99 kg, K0.10/kg from 100 kg to 2,000 kg and
K0.15/kg above, with a K30 minimum from 100 kg. A line carries one minimum for every tier, so it could not be
expressed without misstating either 30-45 kg or 100-299 kg. **`RateTier.min_charge` is added** (migration
`0046_rate_tier_minimum_charge`, nullable, non-negative):

- A tier minimum applies only when that tier prices the weight. NULL means the tier has no minimum.
- A line may not state both a line minimum and a tier minimum (`TIER_MINIMUM_WITH_LINE_MINIMUM`); the model
  enforces the same rule.
- Manifest tiers accept an optional `min_charge` string. Existing manifests are unchanged (the key is optional,
  and absent means NULL). Loader identity, reuse and conflict comparison include it. The resolver exposes it on
  `Tier.min_charge` and emits it in `as_dict()` only when present.
- The build-up is loaded as `[0,100)` rate 0.00; `[100,2000.0001)` rate 0.10 minimum 30.00; `[2000.0001,open)` rate
  0.15 minimum 30.00. Tier quantities carry four decimal places and the upper bound is exclusive, so ">2000 kg" is
  encoded as 2000.0001: 2000 kg prices at 0.10 and 2000.0001 kg at 0.15.
- **Precision fail-closed.** `RateTier` bounds hold four decimal places, so a weight with more precision could sit
  between two representable bounds and cross a break wrongly (2000.00005 kg is above 2000 but below 2000.0001). The
  resolver therefore returns `INVALID_CONTEXT` for any tiered resolution whose `chargeable_weight` has more than four
  decimal places (trailing zeros are fine). The shadow turns that into `BLOCKED`; nothing is priced. The check applies
  to every tiered tariff, not only build-up. The adapter does not round chargeable weight today, so production wiring must supply
  weights at tier precision or round them under an approved rule.
- **Production rule function unchanged.** `core.charge_rules.evaluate_tiered_break_rule` applies one minimum
  to the whole line. The shadow evaluates a tariff whose tiers carry minimums with that same production rule,
  passing the selected tier's minimum. Wiring the Rate Matrix into the production engine will need the same
  per-tier handling (a follow-up gate); no production calculation changed here.

## Export shadow (`rate_matrix_export_shadow.py`, `shadow_price_rate_matrix_export`)

Read-only, in a rolled-back read-only transaction, imported by nothing in a quote path.

- **Legacy**: the unmodified `ExportPricingEngine`, PREPAID, PGK, pricing from legacy rows.
- **Matrix**: `MatrixShadowExportEngine`, the same engine with its two rate lookups redirected to Rate Matrix PGK
  tariffs (BUY by supplier and lane, SELL for PGK), and the per-tier-minimum rule above.
- **AUD**: each explicit PGK SELL line is converted once, `pure = PGK / TT BUY` (rounded), then `CAF = pure x 10%`
  (rounded) as a separate uplift. FX comes through `resolve_market_fx_pair` (policy source priority, age limit,
  fail closed). Only a directly stored AUD/PGK fact is accepted; an inverse or cross result is BLOCKED. No margin is
  added. GST is computed on the converted amount with the production classification.
- **Differences are never forced to MATCH.** Native facts (basis, rate, minimum, maximum, tier table) of the legacy
  row and the Rate Matrix tariff are compared. A difference is `EXPECTED_DIFFERENCE` only when every differing fact
  matches an approved registry entry exactly (lane, side, ProductCode, aspect, legacy value, matrix value) and
  re-pricing with the legacy native facts for that charge reproduces the legacy amount. Totals are EXPECTED only
  when every contributing line is explained and the counterfactual total matches. Otherwise UNEXPLAINED. Unused
  registry entries are reported as stale.
- **Production note**: the production COLLECT engine does not implement the locked AUD rule (it uses native AUD
  rows where present, otherwise margin then `PGK / (TT SELL x (1 + CAF))`). That total is reported per AUD
  scenario as `NOT_COMPARABLE`; production wiring is a separate gate.
- **Scenarios**: both lanes, weights 30 / 45 / 100 / 200 / 500 / 999 / 1000 / 1001 kg, scopes A2A and D2A,
  currencies PGK and AUD (64 scenarios). D2D, A2D, special cargo and COLLECT PGK are not run.

## Proof on a copy of the local database

Master data (approved-flag copy), migration 0046 and tariffs were applied to a **copy** of the local database;
the real local database and the hosted database were not touched. Quote date 2026-10-12, 64 scenarios.

| Run | MATCH | EXPECTED | UNEXPLAINED | BLOCKED | NOT_COMPARABLE |
|---|---|---|---|---|---|
| Before correction (stale legacy SELL in the manifest) | 2,432 | 0 | 0 | 0 | 96 |
| Corrected SELL, **without** the approved registry | 2,192 | 0 | 304 | 0 | 32 |
| Corrected SELL, with the approved registry | 2,192 | 304 | 0 | 0 | 32 |

The 304 EXPECTED are the SELL freight amount and GST-inclusive amount (64 each) and the two sell totals they feed (64 each), plus the build-up BUY cost (24) and the cost total (24) that the locked BUY rule supersedes. The 32 NOT_COMPARABLE are the production AUD note.

## Still pending

Category and GST approval for the 12 mirrors (flags stay false), the PX legal name, evidence for the
database-only `EXP-HANDLE` and `EXP-FSC-AIR` values, production wiring of the locked AUD rule and of per-tier
minimums, and the export CAF being approved for AUD conversion of explicit SELL only.

## Not done

No manifest applied, no FX or policy change, no ServiceComponent twin, no Rate Matrix flag, no corridor
automation, no production wiring, and no import behaviour change.

## B3M-D: category/GST approval and local apply

Commercial Manager approved the 12 export categories and GST treatments on 2026-10-12 (FREIGHT/ZERO_RATED for
`EXP-FRT-AIR`; CLEARANCE/STANDARD for `EXP-CLEAR`; ORIGIN/STANDARD for the rest). Only the approval flags,
references and evidence in the master-data manifest changed; categories, treatments and every tariff value are
unchanged. Reviewed hashes: master data `d7d39aab031737a67e1752b376fbe4b7ef975aa2e4dd85464063df3b34d5b1b1`,
tariffs `c72d62900bf2e380030ed37c62e6cbd5a80e951db50d08d33b76f933d2988fad`.

Applied to the **local** development database only, with the reviewed hashes: migration 0046, 14 master-data rows (1 party, 1 party role, 12 mirrors) and
70 tariff rows (7 sheets, 21 lines, 21 applicabilities, 21 tiers). Re-running both dry runs and both applies writes
nothing (REUSE). Legacy rate tables are unchanged. The Rate Matrix remains unwired from production.
