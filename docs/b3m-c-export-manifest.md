# Pilot Gate B3M-C: export manifests and export shadow proof

Status: manifests prepared and dry-run verified; read-only shadow built. **Nothing is applied, no Rate Matrix
tariff is live, and no production path reads the Rate Matrix.** Scope: AIR / EXPORT / direct / General Cargo,
POM to BNE and POM to SYD.

## Locked commercial rules (Commercial Manager, 2026-10-12)

| Rule | Value |
|---|---|
| BUY freight | Existing `ExportCOGS` for BNE and SYD, PGK, approved 2026-10-12 until superseded; supplier Air Niugini (PX) |
| SELL freight | Current EFM PGK export rate card; continuation approved 2026-10-12 despite the printed 2025 expiry; PGK tariffs only, no AUD SELL tariff |
| AUD quote | `AUD SELL = (PGK SELL / TT BUY) x 1.10` from `FxMarketRate`; export CAF 10% applies only when a conversion occurs; no conversion means no FX and no CAF |
| Margin | An explicit SELL tariff receives no additional margin |

Export CAF 10% is approved by this instruction for the AUD conversion of explicit PGK SELL only. It is not a
margin and is not a rate adjustment.

## Manifests (`backend/pricing_v4/rate_matrix_manifests/`)

| File | Loader | Dry run on the local database |
|---|---|---|
| `export-pilot-master-data-2026-10-12.json` | `load_rate_matrix_master_data` | CREATE 1 (party), BLOCKED 12 (GST and category approval pending) |
| `export-pilot-tariffs-2026-10-12.json` | `load_rate_matrix_manifest` | FAIL until master data exists (`PRODUCT_CODE_UNRESOLVED`, `PARTY_UNRESOLVED`); READY once it does (7 sheets, 20 lines, 16 tiers) |

Both are strict JSON, dry-run by default, and apply only with `--operator` and the reviewed sha256 the dry run
prints. `.gitattributes` pins them `-text` so the hash cannot change on checkout.

Master data carries `gst_approval.approved = false`. The loader therefore reports BLOCKED, and an apply is refused
until the Commercial Manager approves the categories and GST treatments and the file is re-reviewed (its hash
changes). The proof below used an approved-flag copy on a copy of the local database only.

### Sheets

| Sheet | Side | Validity | Supplier |
|---|---|---|---|
| Air freight POM-BNE POM-SYD (`EXP-FRT-AIR`) | BUY | 2026-10-12, open | Air Niugini (PX) |
| Terminal charges POM: DOC 35, AWB 35, TERM 35, SCREEN 0.17/kg + 35 | BUY | 2026-10-12, open | Air Niugini (PX) |
| `EXP-HANDLE` 35 (database value only) | BUY | 2026-10-12, open | Air Niugini (PX) |
| Air freight POM-BNE POM-SYD | SELL | 2026-01-01..2026-12-31 | none |
| Origin charges POM: DOC 50, AWB 50, SCREEN 0.20/kg + 45, TERM 50, BUILDUP 0.20/kg min 50, CLEAR 300, AGENCY 250, PICKUP 1.50/kg min 95 cap 500, FSC-PICKUP 10% of PICKUP | SELL | 2026-01-01..2026-12-31 | none |
| `EXP-HANDLE` 50 (database value only) | SELL | 2026-01-01..2026-12-31 | none |
| `EXP-FSC-AIR` 0.80/kg (database value only) | SELL | 2025-01-01..2030-12-31 | none |

Freight BUY tiers (PGK per kg, minimum K160): BNE 6.30 / 5.90 / 5.70 / 5.40; SYD 8.00 / 7.50 / 7.10 / 6.80 at
0 / 100 / 200 / 500 kg. Freight SELL (minimum K200): BNE 7.90 / 7.40 / 7.15 / 6.75; SYD 10.00 / 9.40 / 8.90 / 8.50.
Payment term is blank (ANY) on every line.

## ProductCode mapping

All twelve already exist as legacy `ProductCode` rows; none has a `CommercialProductCode` mirror yet.

| Code | Id | Category (proposed) | Basis | GST (equals legacy) |
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

Categories follow the runtime leg the export engine assigns; `EXP-CLEAR` follows the approved `IMP-CLEAR`
category. They are proposals and need Commercial Manager approval. Origin services in PNG carry 10% GST and
international freight is zero-rated (`quotes/tax_policy.py`, `enable_export_gst`). Special cargo is excluded.

## Facts reported before inclusion

- **`EXP-HANDLE`**: `local_sell_rates#114` (ANY) and `#139` (PREPAID), POM EXPORT, PGK FIXED 50.00, valid
  2026-01-01..2026-12-31; BUY `local_cogs_rates#23` PGK FIXED 35.00, valid 2026-01-01..2026-12-31. The PX reference
  file has no handling line, so the BUY value is database-only.
- **`EXP-FSC-AIR`**: `local_sell_rates#206`, POM EXPORT, PGK PER_KG 0.8000, payment term ANY, valid
  2025-01-01..2030-12-31. No BUY row and no AUD row. The five-year validity is the stored value.

## Representation gap

The locked BUY build-up has a tier-conditional minimum: nil below 100 kg, then K0.10/kg to 2,000 kg and K0.15/kg
above, with a K30 minimum. A Rate Matrix line (and a legacy rate row) carries one minimum for every tier. Any
line minimum that gives K30 from 100 kg also charges K30 at 30 kg and 45 kg; omitting it loses the minimum from
100 kg to 299 kg. No mechanic is invented: the BUY build-up line is **not loaded**, and the shadow reports its
cost as `NOT_COMPARABLE`. Resolution needs either a per-tier minimum in the contract or a ruling that accepts one
of the two misstatements. The legacy database row (0.15/kg, K30 at every weight) is superseded by the locked rule.

## Export shadow (`rate_matrix_export_shadow.py`, `shadow_price_rate_matrix_export`)

Read-only, in a rolled-back read-only transaction, imported by nothing in a quote path.

- **Legacy**: the unmodified `ExportPricingEngine`, PREPAID, PGK, pricing from legacy rows.
- **Matrix**: `MatrixShadowExportEngine`, the same engine overriding only `_get_cogs` and `_get_sell_rate` to
  Rate Matrix PGK tariffs (BUY by supplier and lane, SELL by PGK).
- **AUD**: each explicit PGK SELL line is converted once, `pure = PGK / TT BUY` (rounded), then
  `CAF = pure x 10%` (rounded) as a separate uplift. FX comes through `resolve_market_fx_pair` (policy source
  priority, age limit, fail closed). Only a directly stored AUD/PGK fact is accepted; an inverse or cross result
  is BLOCKED. No margin is added. GST is computed on the converted amount with the production classification.
- **Production note**: the production COLLECT engine does not implement the locked AUD rule (it uses native AUD
  rows where present, otherwise margin then `PGK / (TT SELL x (1 + CAF))`). That total is reported per AUD
  scenario as `NOT_COMPARABLE`; production wiring is a separate gate.
- **Scenarios**: both lanes, weights 30 / 45 / 100 / 200 / 500 / 999 / 1000 / 1001 kg, scopes A2A and D2A,
  currencies PGK and AUD (64 scenarios). D2D, A2D, special cargo and COLLECT PGK are not supported by the engine
  for these lanes and are not run.
- **Provenance**: each record names the Rate Matrix sheet, version and line; AUD records add policy code and the
  FX pair, side, source, effective date and age.

## Proof on a copy of the local database

Master data (approved-flag copy) and tariffs were applied to a **copy** of the local database; the real local
database and the hosted database were not touched.

| | MATCH | EXPECTED | UNEXPLAINED | BLOCKED | NOT_COMPARABLE |
|---|---|---|---|---|---|
| 64 scenarios, quote date 2026-10-12 | 2,432 | 0 | 0 | 0 | 96 |

The 96 are `EXP-BUILDUP` BUY cost (32), the cost total it feeds (32), and the production AUD note (32).

## Not done

No manifest applied, no FX or policy change, no ServiceComponent twin, no Rate Matrix flag, no corridor
automation, no production wiring, and no import behaviour change.
