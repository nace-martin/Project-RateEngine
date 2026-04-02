# SPOT Intake Deterministic Alias Mapping Plan

**Date:** 2026-04-03
**Branch:** `codex-spot-alias-mapping-plan`

## Goal

Standardize messy agent charge labels like `DOC`, `CUS`, `CMD`, and `A/F` without letting the LLM silently guess billable internal codes.

The design target is:

- AI extracts rows and structured amounts from messy source text.
- Deterministic rules map extracted labels to canonical internal codes.
- Unknown or ambiguous labels fail closed.
- Users see both the original agent label and the resolved internal description.

## Why This Change Is Needed

The current intake pipeline in [ai_intake_service.py](/C:/Users/commercial.manager/dev/Project-RateEngine/backend/quotes/ai_intake_service.py) already has the right high-level shape:

- extractor: `_extract_raw_charges(...)`
- normalizer: `_normalize_charges(...)`
- critic: `_audit_extraction(...)`
- final shaping: `_build_final_spot_charge_lines(...)`

But the normalizer still asks the LLM to map raw labels directly to `v4_product_code` and `v4_bucket`. That is acceptable for extraction assistance, but it is too soft for financial classification. A wrong mapping is materially worse than an unmapped line.

The current contract already supports safe failure:

- `NormalizedCharge.v4_product_code` can be `UNMAPPED`
- `NormalizedCharge.confidence` is `HIGH` or `LOW`
- downstream warnings already surface unmapped and low-confidence lines

The missing piece is a deterministic alias registry that becomes the authoritative mapping step between extracted labels and canonical codes.

## Design Principles

1. AI extracts, rules classify.
2. Mapping must be deterministic, auditable, and versionable.
3. Unknown terms must never auto-map.
4. Ambiguous matches must never auto-pick.
5. Preserve both original and resolved labels.
6. Bucket and shipment context are guardrails, not optional hints.
7. Admin-approved aliases should improve future imports without changing historical audit trails.

## Current Integration Points

The implementation should attach to the existing SPOT intake seam, not create a second parallel pipeline.

### Existing flow

1. `parse_rate_quote_text(...)` in [ai_intake_service.py](/C:/Users/commercial.manager/dev/Project-RateEngine/backend/quotes/ai_intake_service.py)
2. `RawExtractedCharge` and `NormalizedCharge` in [ai_intake_schemas.py](/C:/Users/commercial.manager/dev/Project-RateEngine/backend/quotes/ai_intake_schemas.py)
3. `SpotChargeLine` final contract in [ai_intake_schemas.py](/C:/Users/commercial.manager/dev/Project-RateEngine/backend/quotes/ai_intake_schemas.py)
4. SPOT review and import safety in [spot_services.py](/C:/Users/commercial.manager/dev/Project-RateEngine/backend/quotes/spot_services.py)
5. SPE persistence in [spot_models.py](/C:/Users/commercial.manager/dev/Project-RateEngine/backend/quotes/spot_models.py)

### Recommended change to the seam

Keep the extractor and critic largely intact. Narrow the normalizer's job.

New responsibility split:

- LLM extractor:
  - produce `raw_label`
  - produce `raw_amount_string`
  - detect `is_conditional`
  - optionally suggest a bucket
- deterministic alias resolver:
  - normalize label text
  - resolve bucket and canonical code
  - return `MAPPED`, `UNMAPPED`, or `AMBIGUOUS`
- value parser:
  - parse amount, currency, unit basis, percentage, min/max
- critic:
  - continue checking for missed rows and hallucinations

## Proposed Data Model

### 1. Alias registry

Add a new model in the `quotes` app, for example `SpotChargeAliasDB`.

Suggested fields:

- `normalized_alias`
- `raw_alias_example`
- `bucket`
- `shipment_type`
- `service_scope`
- `source_kind`
- `agent_id`
- `origin_country`
- `destination_country`
- `target_v4_product_code`
- `target_description`
- `match_type`
- `pattern`
- `priority`
- `is_active`
- `notes`
- `created_by`
- `updated_by`
- `created_at`
- `updated_at`

Notes:

- `target_v4_product_code` should remain the authoritative machine target because the current intake contract already uses `v4_product_code`.
- `target_description` should mirror the canonical description users should see, usually derived from the linked product or service component at resolution time.
- Specific rules must outrank generic rules.

### 2. Mapping outcome metadata

Persist mapping audit metadata with each imported SPE line or source batch. The simplest version is to extend `analysis_summary_json` on [spot_models.py](/C:/Users/commercial.manager/dev/Project-RateEngine/backend/quotes/spot_models.py). If line-level review becomes important, add explicit columns later.

Minimum metadata to preserve:

- `raw_label`
- `normalized_alias`
- `mapping_status`
- `matched_rule_id`
- `matched_rule_scope`
- `resolved_v4_product_code`
- `resolved_description`
- `candidate_codes`
- `mapping_reason`

### 3. Preserve both labels

Do not overwrite the original agent text.

Every imported line should preserve:

- original label: what the agent actually sent
- resolved label: the approved canonical description

Recommended UI rendering:

- primary text: resolved description when mapped
- secondary text: original agent label
- status badge: `Mapped`, `Unmapped`, or `Needs Review`

## Deterministic Resolution Rules

Resolution should run in this order:

1. Normalize the raw label.
   - uppercase
   - trim
   - strip punctuation
   - collapse whitespace
2. Determine bucket candidates.
   - use explicit SPE missing components first
   - then explicit source batch target bucket
   - then LLM bucket suggestion if present
   - otherwise keep bucket unresolved
3. Query alias rules from most specific to least specific.
   - agent + bucket + shipment type + scope
   - bucket + shipment type + scope
   - bucket only
   - global
4. Apply only approved match types.
   - exact alias
   - approved regex or phrase rules
5. If exactly one active highest-priority rule matches, map it.
6. If zero rules match, return `UNMAPPED`.
7. If multiple rules remain tied, return `AMBIGUOUS`.

Forbidden behavior:

- no embedding similarity
- no fuzzy nearest-neighbor auto-pick
- no "best guess" fallback
- no bucket inference that contradicts explicit SPE context

## Integration Plan

### Phase 1. Deterministic registry and service

Add:

- `SpotChargeAliasDB` model and migration
- `DeterministicAliasResolver` service in `quotes`
- normalization helper for raw labels
- resolver tests for exact, scoped, unknown, and ambiguous matches

Update [ai_intake_service.py](/C:/Users/commercial.manager/dev/Project-RateEngine/backend/quotes/ai_intake_service.py):

- stop treating the LLM as the final authority on `v4_product_code`
- let the LLM keep suggesting structure and optional bucket hints
- run the deterministic resolver before building final `SpotChargeLine` values
- emit `UNMAPPED` when the resolver cannot safely classify a label

### Phase 2. Review-first intake UX

Update the SPOT review flow so imported lines clearly show:

- raw label
- resolved label
- mapping status
- matched canonical code
- whether the result came from an exact approved alias or needs manual review

Allow the user to:

- accept the mapping
- override the mapping
- save the override as a new alias rule if they have permission

### Phase 3. Admin workflow

Provide a lightweight admin surface for alias maintenance:

- create alias
- deactivate alias
- inspect top unmapped labels
- inspect ambiguous labels
- seed common abbreviations like `DOC`, `CUS`, `AWB`, `A/F`, `XRY`, `CTO`

### Phase 4. Observability

Add structured logging and counters for:

- mapped lines
- unmapped lines
- ambiguous lines
- top unmapped raw labels
- top alias hits by agent and bucket

This will tell us whether the registry is actually reducing manual review.

## Recommended Contract Changes

### `NormalizedCharge`

Keep `v4_product_code` for backward compatibility, but treat it as the resolver output, not the LLM's final answer.

Consider adding:

- `mapping_status: Literal["MAPPED", "UNMAPPED", "AMBIGUOUS"]`
- `resolved_description: Optional[str]`
- `candidate_v4_product_codes: list[str] = []`
- `resolver_rule_id: Optional[str]`

### `SpotChargeLine`

Retain:

- `description` as the human-visible label
- `original_raw_label` for traceability
- `v4_product_code` as the machine code

Recommended behavior:

- if mapped, `description` should be the resolved canonical description
- if unmapped, `description` can remain the raw label
- UI should always expose `original_raw_label`

## Test Plan

Add tests in the `quotes` suite for:

1. exact alias mapping inside the correct bucket
2. same alias mapping differently across origin and destination
3. agent-specific alias overriding a global alias
4. unknown alias returning `UNMAPPED`
5. ambiguous alias returning `AMBIGUOUS`
6. conditional charges staying conditional after mapping
7. imported lines preserving both raw and resolved labels
8. manual review warnings appearing in [spot_services.py](/C:/Users/commercial.manager/dev/Project-RateEngine/backend/quotes/spot_services.py)

Existing files that should gain coverage:

- [test_ai_intake_contract.py](/C:/Users/commercial.manager/dev/Project-RateEngine/backend/quotes/tests/test_ai_intake_contract.py)
- [test_spot_ai_autofill.py](/C:/Users/commercial.manager/dev/Project-RateEngine/backend/quotes/tests/test_spot_ai_autofill.py)

## Seed Data Strategy

Start with a small approved registry, not a giant dictionary.

First-pass candidates:

- `DOC` -> documentation charge by bucket
- `CUS` -> customs clearance by bucket
- `AWB` -> air waybill fee
- `A/F` and `AF` -> air freight
- `XRY` -> x-ray or screening
- `CTO` -> terminal or handling only if the business already has a single approved meaning

If a shorthand has more than one real meaning in the business, leave it unmapped until narrowed by bucket, agent, or route context.

## Risks and Controls

### Risk: Alias table becomes a junk drawer

Control:

- require bucket on every alias
- prefer specific rules over global rules
- add `is_active` and `priority`
- keep audit trail on who approved each alias

### Risk: Wrong auto-mapping becomes invisible

Control:

- preserve raw label beside resolved label
- show mapping status in review UI
- fail closed on unknown and ambiguous inputs

### Risk: Historical quote behavior changes after alias edits

Control:

- store resolved code and resolved description on the imported line at intake time
- treat alias registry as write-time resolution, not dynamic read-time lookup

## Implementation Order

1. Add alias registry model and admin.
2. Add deterministic resolver service and tests.
3. Narrow the LLM normalizer contract.
4. Persist mapping metadata in the SPE import path.
5. Update SPOT review UI to display mapping status and both labels.
6. Add top-unmapped reporting for operational feedback.

## Recommendation

Proceed with a fail-closed deterministic registry, not a smarter LLM prompt.

The LLM is already useful for extraction. It should stay in that role. Canonical charge mapping should become a rules engine with explicit approvals, scoped aliases, and visible review states.
