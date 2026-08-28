---
name: structural-audit
description: Audit RateEngine structure for major refactors, module-boundary changes, dead code, duplication, dependency issues, or cross-domain architecture work. Do not use for routine edits or narrow bug fixes.
---

# Structural Audit

## Purpose

Establish structural evidence before genuinely structural RateEngine work without turning repository-wide analysis into routine pre-flight.

## Trigger

Use for major refactors, module-boundary or shared-state changes, cross-domain contracts, dead-code removal, duplication cleanup, dependency restructuring, or an explicitly requested structural audit.

Do not use solely because a session is new, a single file changed, a test failed, or ordinary implementation touches an existing module.

## Required Context

Confirm the branch, working-tree ownership, requested scope, affected domains, and applicable `AGENTS.md`. Inspect relevant source and configuration before interpreting tool findings.

## Workflow

1. Run the relevant baseline from the repository root:

   ```bash
   npx fallow --format json
   npx fallow dead-code --format json
   npx fallow dupes --format json
   npx fallow health --format json
   ruff check backend
   vulture backend
   ```

   Use Fallow for JavaScript/TypeScript structure, dead code, duplication, and health; Ruff for Python lint and static checks; Vulture for Python dead-code candidates; and Graphify for graph-relevant architecture relationships.

2. Narrow or omit a tool when the scoped language/domain makes it irrelevant; report the reason.
3. Treat findings as evidence, not permission to edit or delete.
4. Verify candidates through source, callers, tests, runtime registration, framework conventions, and generated-file rules.
5. Classify findings as confirmed, false positive, historical debt, or out of scope.
6. Propose or implement only the approved structural concern. Do not absorb unrelated findings.
7. After graph-relevant code structure changes, run `graphify update .` once before final handoff. Do not update Graphify for documentation-only or nonstructural edits.

## Stop Conditions

Stop and report if a required tool is unavailable, findings cross an unapproved commercial/RBAC/deployment boundary, ownership of existing changes is unclear, or safe removal cannot be proven.

## Output

Report commands and exact outcomes, verified findings with locations, false positives, scope decisions, changes made, targeted validation, and residual structural risk.
