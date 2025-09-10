Release v0.3.1

Highlights

- Manual rating triggers: API returns `manual_rate_required` with reasons for non-GCR commodities, urgent shipments, or routes flagged for manual rating.
- Engine fix: safe fallback for `chargeable_kg` in manual scenarios to avoid errors.
- FX/rounding behaviors validated by tests (BUY/SELL CAF, SELL total rounding).
- Developer ergonomics: `.env` support via python-dotenv; example `.env` and README updates.
- Smoke tooling: management command `smoke_manual_triggers` to quickly verify manual-trigger paths via `/api/quote/compute`.

API

- `POST /api/quote/compute` accepts optional:
  - `commodity_code` (e.g., `GCR`, `DGR`, `LAR`, `PER`)
  - `is_urgent` (boolean)
  - Response `snapshot` includes `manual_rate_required` and `manual_reasons`.

Backend

- `engine.compute_quote` now falls back to per-piece chargeable weight when no FREIGHT lines are produced (e.g., manual cases).
- Added management command `smoke_manual_triggers` for API smoke testing without starting the server.
- Helper scripts under `scripts/` to align local unmanaged tables with current code.

Setup & Ops

- `.env` loading enabled: set `DATABASE_URL` and other envs in a root `.env`.
- Example file: `.env.example` (copy to `.env`).

Testing

- Full backend suite passes against PostgreSQL (`accounts`, `rate_engine`).
- Smoke command outputs manual reasons for non-GCR, urgent, and route-flagged cases.

Upgrade Notes

- Ensure `DATABASE_URL` (Postgres) is set; run `python manage.py migrate`.
- For local dev, copy `.env.example` to `.env` and adjust values as needed.

