# Launch Corridor Matrix

Last updated: 2026-03-19

This document is the current practical view of corridor coverage based on what is seeded and verified in the local environment.

It is not the same thing as business approval.
Use this to decide:
- what can be tested now
- what is likely in launch scope already
- what still needs explicit commercial confirmation before go-live

## Current Position

- Export standard quoting has seeded freight coverage from `POM` to:
  - `BNE`
  - `CNS`
  - `HIR`
  - `HKG`
  - `MNL`
  - `NAN`
  - `SIN`
  - `SYD`
  - `VLI`
- Import quoting is currently strongest for destination-local `POM` flows, especially the special-cargo local handling path.
- Domestic launch tariffs are seeded for the `POM` and `LAE` origin tariff sheet now in the repo.

## Verified Standard Quote Flows

These are the flows that have been explicitly smoke-tested in the current local environment.

| Flow | Status | Notes |
| --- | --- | --- |
| Export standard `POM -> BNE` | Verified | Standard quote path works |
| Export standard `POM -> SYD` | Verified | Standard quote path works |
| Import `A2D` to `POM` | Verified | Standard quote path works |
| Import `A2D` `DG` to `POM` | Verified | Uses standard quote when local tariff exists |
| Import `A2D` `AVI` to `POM` | Verified | Uses standard quote when local tariff exists |
| Import `A2D` `HVC` to `POM` | Verified | Uses standard quote when local tariff exists |
| Domestic `POM -> LAE` `GCR` | Verified | `has_missing_rates = false` |
| Domestic `POM -> LAE` `SCR` | Verified | Includes `DOM-EXPRESS` only for `SCR` |
| Domestic `POM -> LAE` `AVI` | Verified | Includes `DOM-LIVE-ANIMAL` |
| Domestic `POM -> LAE` `HVC` | Verified | Includes `DOM-VALUABLE` |
| Domestic `POM -> LAE` `OOG` | Verified | Includes `DOM-OVERSIZE` |

## Export Coverage Seeded

Current seeded export freight lanes in the local DB:

- `POM -> BNE`
- `POM -> CNS`
- `POM -> HIR`
- `POM -> HKG`
- `POM -> MNL`
- `POM -> NAN`
- `POM -> SIN`
- `POM -> SYD`
- `POM -> VLI`

Launch recommendation:
- treat `POM -> BNE` and `POM -> SYD` as the confirmed base launch lanes unless the business explicitly approves the others

## Import Coverage Seeded

Current import special local tariff coverage is confirmed for `POM` destination handling on:

- `IMP-DG-SPECIAL`
- `IMP-AVI-SPECIAL`
- `IMP-HVC-SPECIAL`

Operational meaning:
- import `A2D` / `D2D` special-cargo quoting is currently reliable for `* -> POM`
- non-`POM` PNG import destinations still need explicit local tariff seeding before they should be treated as launch-ready

## Domestic Coverage Seeded

Domestic freight lanes currently seeded from the launch tariff sheet:

### Origin `POM`

- `POM -> BUA`
- `POM -> CMU`
- `POM -> DAU`
- `POM -> GKA`
- `POM -> GUR`
- `POM -> HGU`
- `POM -> HKN`
- `POM -> KIE`
- `POM -> KOM`
- `POM -> KVG`
- `POM -> LAE`
- `POM -> LNV`
- `POM -> LSA`
- `POM -> MAG`
- `POM -> MAS`
- `POM -> MDU`
- `POM -> PNP`
- `POM -> RAB`
- `POM -> TBG`
- `POM -> TFI`
- `POM -> TIZ`
- `POM -> UNG`
- `POM -> VAI`
- `POM -> WBM`
- `POM -> WWK`

### Origin `LAE`

- `LAE -> BUA`
- `LAE -> CMU`
- `LAE -> DAU`
- `LAE -> GKA`
- `LAE -> GUR`
- `LAE -> HGU`
- `LAE -> HKN`
- `LAE -> KIE`
- `LAE -> KVG`
- `LAE -> LNV`
- `LAE -> MAG`
- `LAE -> MAS`
- `LAE -> MDU`
- `LAE -> PNP`
- `LAE -> POM`
- `LAE -> RAB`
- `LAE -> TBG`
- `LAE -> TIZ`
- `LAE -> UNG`
- `LAE -> VAI`
- `LAE -> WBM`
- `LAE -> WWK`

### Return Lanes Present Via Existing Seed Data

The local DB also currently contains return-to-`POM` domestic freight rows for several stations, including:

- `BUA -> POM`
- `CMU -> POM`
- `DAU -> POM`
- `GKA -> POM`
- `GUR -> POM`
- `HGU -> POM`
- `HKN -> POM`
- `KIE -> POM`
- `KOM -> POM`
- `KVG -> POM`
- `LNV -> POM`
- `LSA -> POM`
- `MAG -> POM`
- `MAS -> POM`
- `MDU -> POM`
- `PNP -> POM`
- `RAB -> POM`
- `TBG -> POM`
- `TFI -> POM`
- `TIZ -> POM`
- `UNG -> POM`
- `VAI -> POM`
- `WBM -> POM`
- `WWK -> POM`

## Domestic Commodity Rules Seeded

Current domestic commodity behavior:

| Commodity | Trigger Mode | Product |
| --- | --- | --- |
| `SCR` | `AUTO` | `DOM-EXPRESS` |
| `AVI` | `AUTO` | `DOM-LIVE-ANIMAL` |
| `HVC` | `AUTO` | `DOM-VALUABLE` |
| `OOG` | `AUTO` | `DOM-OVERSIZE` |
| `DG` | `REQUIRES_SPOT` | `DOM-DG-SPECIAL` |
| `PER` | `REQUIRES_SPOT` | `DOM-PER-SPECIAL` |

## What Still Needs Business Confirmation

These are the remaining scope decisions before launch can be considered locked:

- Which export lanes beyond `POM -> BNE` and `POM -> SYD` are truly in go-live scope
- Whether import launch scope is `POM` only or includes other PNG destinations
- Which domestic stations are actually sellable on day one versus simply loaded as reference/rate data
- Whether domestic `DG` and `PER` should stay SPOT-only at launch

## Recommended Next Use

Use this matrix as the signoff sheet for:

1. pricing/business approval of the exact go-live lanes
2. UAT scenario selection
3. stop-ship validation before production deploy
