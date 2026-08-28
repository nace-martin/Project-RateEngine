---
name: seed-data-change
description: Plan and execute controlled RateEngine ProductCode, ChargeAlias, reference-data, remediation, or backfill changes using mandatory dry-run review and separately authorized apply mode.
---

# Seed Data Change

## Purpose

Keep commercial and production data changes inspectable, deterministic, reversible where practical, and explicitly authorized.

## Trigger

Use for ProductCode, ChargeAlias, rate/reference-data seeding, remediation, normalization, consolidation, backfill, or comparable commands that can write commercial or scoped records.

## Required Context

Identify the authoritative input, target environment, affected tables/models, existing command or management workflow, uniqueness and audit constraints, rollback approach, and applicable nested instructions. Confirm whether the request authorizes inspection, dry run, or apply; these are separate permissions.

## Workflow

1. Inspect current source, command help, input data, existing records or diagnostics, and maintained domain documentation.
2. Run or implement dry-run mode first. Dry run is the default and must not write.
3. Report proposed creates, updates, skips, conflicts, ambiguous mappings, duplicates, blockers, and commercial impact without exposing sensitive data.
4. Stop for human review. Dry-run approval does not imply apply approval.
5. Run apply mode only after explicit authorization for the reviewed scope and environment. Require an explicit apply flag; do not silently transition from reporting to writes.
6. Verify persisted counts, representative records, uniqueness/audit behavior, and affected quote or selector paths.
7. Report exact results and a safe rollback or compensating plan.

## Commercial Boundaries

- Do not invent ProductCode fields, ChargeAlias targets, units, currencies, coverage, hierarchy, or pricing meaning.
- Ambiguous mappings remain unresolved; do not use wildcards or label similarity to hide uncertainty.
- Do not overwrite base rates, mutate active SPE evidence, or change quote-calculation behavior unless separately scoped and approved.
- ProductCode request creation is not approval. Do not create duplicate active requests.
- Preserve who, what, when, why, and the reviewed input used for every applied decision.

## Stop Conditions

Stop when the input is incomplete, authoritative records conflict, a mapping requires commercial judgment, the environment is uncertain, dry run cannot prove scope, rollback is unsafe, or requested writes exceed the reviewed proposal.

## Output

Report environment, input/source, dry-run command and results, approval boundary, apply command and results if authorized, verification, commercial/data/audit impact, unresolved rows, and rollback.
