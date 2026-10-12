# Pilot Gate B3L-F: Stage-2 converted-fallback attribution

Status: diagnostic-only fix to the Stage-2 shadow classifier. No tariff, approval, FX, policy or Rate Matrix
data changed, and nothing is written.

## Problem

Legacy PREPAID AUD pricing can select a **PGK** `ANY` destination SELL row and convert it to AUD. Stage-1
compares native rows in each context's own currency, so the approved native difference for that tariff fact
(for example B3E decision 8: `IMP-LOADING-DEST` presence) is recorded only under `COLLECT/PGK`. Stage-2 looked
for evidence under `PREPAID/AUD`, found none, and reported the line and its TOTAL roll-ups as UNEXPLAINED
(224 records across 32 scenarios on the real local data) although the underlying difference was approved.

## Fix (`rate_matrix_stage2_shadow.py`)

Stage-2 now carries the legacy line's native-source provenance. The legacy engine is wrapped in
`LegacyRecordingImportEngine`, a pure pass-through that records which `LocalSellRate` row it chose for each
destination charge. `_converted_fallback_evidence` inherits an approved Stage-1 difference only when all hold:

1. the engine reports exactly one legacy source row for the charge (same ProductCode, lane, side, scenario
   weight);
2. the line was converted from that row's currency to the quote currency (explicit lineage; any conversion
   evidence the engine recorded for the charge must agree on product code, role and currencies);
3. the Rate Matrix side prices nothing for the charge in the same scenario;
4. a Stage-1 context in the source row's native currency compared a legacy row with **identical native
   facts** (the ANY row and the COLLECT row are distinct rows, so equality is of facts, not row id; both ids
   are named in the reason);
5. every pricing-relevant Stage-1 record there is the approved `presence` difference (legacy present, Rate
   Matrix absent) carrying registry evidence;
6. the existing counterfactual repricing reproduces the legacy converted amount, and TOTALs are EXPECTED only
   when every contributing line is explained and the counterfactual total matches.

Anything missing, ambiguous or different leaves the line UNEXPLAINED. PREPAID/AUD is never mapped to
COLLECT/PGK by name, and no PREPAID/AUD registry entry is needed or accepted.

## Result on the real local data (2026-10-12, 64 scenarios, approved registry)

| | Before | After |
|---|---|---|
| MATCH | 1819 | 1819 |
| EXPECTED_DIFFERENCE | 709 | 933 |
| UNEXPLAINED_DIFFERENCE | 224 | 0 |
| BLOCKED | 0 | 0 |

Tests: `pricing_v4/tests/test_b3lf_stage2_converted_fallback.py`.
