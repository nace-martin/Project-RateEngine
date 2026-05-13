# GEMINI.md

## Gemini CLI Operating Rules

Gemini CLI must follow `AGENTS.md`. This file is Gemini-specific operating guidance only and must not duplicate the full constitution.

## Scope Control

- Do not perform broad rewrites unless explicitly requested.
- Do not refactor unrelated files.
- Do not hide backend, frontend, UI, cleanup, or formatting changes inside an unrelated task.
- Keep one PR focused on one concern.

## Investigation Before Fixing

- Explain the root cause before implementing a fix.
- Do not revive deprecated, deleted, or legacy logic.
- Do not reuse legacy Spot CRUD paths.
- Stop and report ambiguity instead of guessing.

## Delivery Report

Every Gemini CLI handoff must include:

- Files changed and why.
- Tests run and results.
- Manual workflow checks run and results, or why they were not applicable.
- Any intentionally unchanged areas.

