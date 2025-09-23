# Tasks: DB Reform v1

**Branch**: `004-db-reform-v1` | **Date**: Tuesday 23 September 2025 | **Spec**: specs/004-db-reform-v1/spec.md
**Plan**: specs/004-db-reform-v1/plan.md

## Phase 0: Setup & Prerequisites

- [x] T001: Create feature branch `004-db-reform-v1` (already done)
- [ ] T002: Open draft PR with checklist below
- [x] T003: Protect behind `QUOTER_V2_ENABLED` in settings

## Phase 1: Pre-flight Data Audit (read-only, generate CSVs)

- [x] T004: **Script**: `backend/scripts/audit_overlaps.sql`
    - Detect overlapping ratecards per (provider_id, audience_id, name)
    - Detect overlapping `cartage_ladders` per ratecard (using numrange)
    - Detect overlapping `storage_tiers` per (ratecard_id, group_code) (using int4range)
- [x] T005: **Script**: `backend/scripts/audit_codes.sql`
    - List unknown currency, unit, audience codes used in tables vs seeds
- [x] T006: **Python harness**: `backend/tools/audit_dump.py` → outputs `/tmp/db_reform_audit/*.csv`
- [ ] T007: Review CSVs; mark any rows to deactivate/split before constraints land
- [ ] T008: Commit CSVs under `docs/db-reform/audit/`

## Phase 2: Migrations Pack A (contracts, no overlaps yet)

- [x] T009: **Migration 0101**: Create currencies, units; seed PGK/AUD/USD + KG/WM/CBM/EA; add FKs on `quotes.currency`, `quote_lines.currency`, `quote_lines.unit`
- [x] T010: **Migration 0102**: Add `audience_id` to `organizations`, `pricing_policy`; backfill via `audiences.code`; add FKs
- [x] T011: **Migration 0106**: Add `quotes.is_incomplete`, `quotes.incomplete_reason`
- [x] T012: **Migration 0107**: JSON GIN indexes + minimal JSON CHECKs
- [x] T013: **Migration 0108**: `route_legs` (`route_id`, `sequence`) unique constraint
- [x] T014: **Migration 0109**: Add currency FKs on `ratecard_fees.currency`, `service_items.currency`
- [x] T015: **Migration 0110**: `stations` IATA check + uppercase normalize
- [x] T016: Verify all Pack A migrations apply cleanly on dev DB; app boots; CRUD unaffected.

## Phase 3: Code Touches (behind flag)

- [x] T017: `pricing_v2/types.py`: Add `Currency`, `Unit`, `AudienceId` dataclasses/enums
- [x] T018: `pricing_v2/recipes/select_ratecard.py`: Ensure single active ratecard resolution (returns 0/1 only)
- [x] T019: `pricing_v2/service/compute_quote.py`: On missing BUY/rate elements → set `quote.is_incomplete=True` + human `incomplete_reason`; never raise 500
- [x] T020: `pricing_v2/service/compute_quote.py`: Aggregate multiple reasons if needed
- [x] T021: `pricing_v2/api/serializers.py`: Include `is_incomplete`, `incomplete_reason` in output
- [x] T022: `pricing_v2/models/quote_lines.py` usage sites: Prefer `side` not dual booleans (post-migration 0105)
- [x] T023: Verify that with flag on, API returns `is_incomplete` correctly when BUY gaps exist.

## Phase 4: Migrations Pack B (overlap enforcement)

- [x] T024: **Migration 0103**: Add `btree_gist` + `ratecards_no_overlap` exclusion constraint
- [x] T025: **Migration 0104**: Add `cartage_ladders_no_overlap` (numrange) and `storage_tiers_no_overlap` (int4range)
- [x] T026: **Migration 0105**: Add `quote_lines.side` with CHECK + precision normalize; backfill from `is_buy`/`is_sell`
- [x] T027: Verify constraints apply; pre-flight rerun shows zero conflicts; inserts that overlap now fail in tests.

## Phase 5: Tests (DB + API)

- [x] T028: Add `pricing_v2/tests/test_ratecards_overlap.py` (EXCLUDE constraint raises `IntegrityError`)
- [x] T029: Add `pricing_v2/tests/test_quotes_incomplete_flag.py` (defaults + settable)
- [x] T030: Add API test `pricing_v2/tests/test_quote_missing_buy_sets_incomplete.py` (service path)
- [x] T031: Ensure these tests are gated by `QUOTER_V2_ENABLED=true` in CI.

## Phase 6: Staging Dry-Run

- [x] T032: Restore anonymized prod snapshot to staging
- [x] T033: Run Pack A → smoke test admin + quotes
- [x] T034: Run Pack B → verify no constraint failures
- [x] T035: Measure JSON query times pre/post GIN (basic EXPLAIN ANALYZE notes)
- [x] T036: Verify no data blockers; performance neutral or better on JSON filters.

## Phase 7: Production Rollout

- [x] T037: Maintenance window (short): apply Pack A
- [x] T038: Verify app health; enable feature flag for staff only
- [x] T039: Apply Pack B
- [x] T040: Enable feature flag for all
- [x] T041: Monitor logs for `is_incomplete=true` spikes; track % metric
- [x] T042: Verify zero 500s from missing BUY; quotes with gaps are flagged, not crashed.

## Phase 8: Post-roll Cleanup (follow-up mini-spec)

- [x] T043: Drop legacy text columns: `organizations.audience`, `pricing_policy.audience`
- [x] T044: Add partial indexes (e.g., `ratecards(status='ACTIVE')`)
- [x] T045: Decide & implement deletion semantics (`is_active` vs cascade) for ratecard children
- [x] T046: Create dashboard tile: “Incomplete Quotes by Day/Reason”
- [x] T047: Verify no dual-truth columns; ops visibility in place.
