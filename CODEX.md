# CODEX.md

## Codex Operating Rules

Codex must follow `AGENTS.md`. This file is Codex-specific operating guidance only and must not duplicate the full constitution.

## Branch and Scope

- Work from a clean branch unless the user explicitly says otherwise.
- If the current worktree is dirty, isolate the requested work before editing or report the blocker.
- Keep one PR focused on one concern.
- Do not expand scope silently.

## Investigation Before Fixing

- Explain the root cause before implementing a fix.
- Do not patch symptoms while leaving dead or deprecated paths alive.
- Do not reuse deprecated code, deleted code paths, or legacy Spot CRUD.
- Follow Cloud Run statelessness and security rules defined in `AGENTS.md`.
- Stop and report ambiguity instead of guessing.

## Delivery Report

Every Codex handoff must include:

- Files changed and why.
- Tests run and results.
- Manual workflow checks run and results, or why they were not applicable.
- Any intentionally unchanged areas.
