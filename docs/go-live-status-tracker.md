# Go-Live Status Tracker

Last updated: 2026-03-19

This is the practical readiness view for launch.

Overall estimated readiness: `80%`

Go / no-go status today: `NOT READY FOR PRODUCTION YET`

Reason:
- core quoting logic is largely in place
- core reference/master data is seeded
- standard vs SPOT decisioning is materially stronger
- domestic tariff/routing coverage is now in place for the current launch sheet
- remaining work is mostly production setup, launch-data validation, and final UAT

## Summary

| Area | Status | Owner | Notes |
| --- | --- | --- | --- |
| Core geography/reference data | DONE | Customer Ops / Pricing | Scoped launch pack seeded and validated |
| Currency / FX currency scope | DONE | Finance / Pricing | Reduced to operational BSP-set currencies |
| Location display / quote UX | DONE | Product / Eng | Airport-backed locations render as city names |
| Import pricing base coverage | DONE | Pricing | Seeded and duplicate import COGS cleaned |
| Export pricing base coverage | DONE | Pricing | Launch export corridors seeded |
| Local rate architecture cleanup | DONE | Pricing / Eng | Local sell/cost rows moved out of lane tables |
| Commodity rule framework | DONE | Eng / Pricing | Standard quote now supports commodity-aware routing |
| Import A2D DG / AVI / HVC | DONE | Pricing / Eng | Standard Quote works when destination-local tariffs exist |
| SPOT fallback behavior | DONE | Eng | Triggering now depends on real missing coverage |
| Policy hygiene | DONE | Pricing | Single active launch policy |
| Local development readiness | DONE | Eng | Current local environment is launch-like |
| Domestic tariff/routing coverage | DONE | Pricing / Eng | Launch domestic tariff sheet seeded and verified locally |
| Production users on prod env | REMAINING | Admin / Security | Must verify on actual production DB |
| Production env vars / deploy config | REMAINING | Platform / DevOps | Must verify on actual server |
| Scheduler / cron jobs | REMAINING | Platform / DevOps | FX refresh and housekeeping still need prod wiring |
| Launch customer/contact completeness | IN PROGRESS | Customer Ops | Need final real production import verification |
| Launch corridor signoff | IN PROGRESS | Pricing / Business | Seeded coverage is now documented; explicit business approval still needed |
| PNG destination coverage beyond POM | IN PROGRESS | Pricing | Special local tariffs currently confirmed for `POM`; other stations only if in launch scope |
| UAT / business signoff | REMAINING | QA / Business | Final manual end-to-end checks still required |

## Detailed Tracker

| Item | Status | Priority | Owner | Blocker | Exit Criteria |
| --- | --- | --- | --- | --- | --- |
| Seed launch countries/cities/airports/locations | DONE | High | Customer Ops | None | Launch stations searchable and active |
| Seed launch currencies | DONE | High | Finance | None | Only operational FX currencies remain |
| Normalize location rendering in quotes/PDFs | DONE | Medium | Eng | None | Quotes show city names, not raw airport names |
| Seed import product/rate stack | DONE | High | Pricing | None | Import quotes compute without missing mandatory pricing |
| Seed export product/rate stack | DONE | High | Pricing | None | Export quotes compute without missing mandatory pricing |
| Remove legacy local duplication from lane tables | DONE | High | Eng / Pricing | None | Local charges live in `LocalSellRate` / `LocalCOGSRate` only |
| Add `SPOT_CHARGE` and safe SPOT component mapping | DONE | Medium | Eng | None | SPOT charges persist with stable component mapping |
| Add commodity support to standard quotes | DONE | High | Eng | None | Standard quotes carry and use `commodity_code` |
| Commodity-aware SPOT trigger | DONE | High | Eng | None | SPOT only when scope/commodity coverage is actually missing |
| Engine-side commodity AUTO pricing | DONE | High | Eng / Pricing | None | Commodity AUTO rules are priced in standard quotes |
| Remove manager-approval dependency from standard quoting | DONE | High | Product / Eng | None | Engine is autonomous; no routine approval bottleneck |
| Seed launch commodity matrix | DONE | High | Pricing | None | Initial rule set exists for `DG`, `AVI`, `HVC`, `PER` |
| Seed import special local tariffs for `DG` / `AVI` / `HVC` | DONE | High | Pricing | None | Import `A2D` standard quotes include special local lines |
| Verify import `A2D` `DG` / `AVI` / `HVC` live behavior | DONE | High | Eng / QA | None | `201` standard quote responses confirmed locally |
| Seed domestic launch tariffs and commodity uplifts | DONE | High | Pricing / Eng | None | Domestic tariff sheet is seeded and domestic special cargo routes correctly |
| Create/verify real prod admin + role users | REMAINING | High | Admin / Security | Needs prod env access | `admin`, `manager`, `finance`, `sales` log in on production |
| Verify customer/contact production seed | IN PROGRESS | High | Customer Ops | Need final customer seed files | Launch customers selectable, with real contacts |
| Verify launch corridor list | IN PROGRESS | High | Pricing / Business | Business confirmation needed | Written list of go-live lanes approved against `docs/launch-corridor-matrix.md` |
| Seed PNG destination-local special tariffs beyond `POM` if needed | REMAINING | Medium | Pricing | Need confirmed launch stations | Each non-`POM` PNG destination in scope has matching local tariffs |
| Verify production env vars | REMAINING | High | Platform / DevOps | Needs production deployment pass | App boots correctly in prod mode |
| Run prod migrations / static collection | REMAINING | High | Platform / DevOps | Needs deployment window | Migrations and static build succeed on prod |
| Configure FX refresh job | REMAINING | High | Platform / DevOps / Finance | Needs scheduler | Fresh FX snapshot appears daily |
| Configure housekeeping jobs | REMAINING | Medium | Platform / DevOps | Needs scheduler | Draft cleanup/archive jobs run cleanly |
| Final UAT: export standard quote | REMAINING | High | QA / Business | Needs staging/prod-like env | Quote computes, finalizes, PDF works |
| Final UAT: import standard quote | REMAINING | High | QA / Business | Needs staging/prod-like env | Quote computes, finalizes, PDF works |
| Final UAT: import `A2D` `DG` | REMAINING | High | QA / Business | Needs staging/prod-like env | Standard Quote, no unwanted SPOT |
| Final UAT: import `A2D` `AVI` / `HVC` | REMAINING | High | QA / Business | Needs staging/prod-like env | Standard Quote, no unwanted SPOT |
| Final UAT: one valid SPOT-required case | REMAINING | Medium | QA / Business | Needs staging/prod-like env | Correctly routes into SPOT only when intended |
| Production PDF verification | REMAINING | Medium | QA / Business | Needs deployed env | Final PDFs render correctly in prod |

## Stop-Ship Items Still Open

Do not launch until these are closed:

- production environment variables verified
- production users verified
- launch customers and contacts verified
- launch corridor list explicitly confirmed
- final UAT completed in deployed environment
- scheduler jobs configured

## Current Decision

Current recommendation: `GO-LIVE HOLD`

Why:
- the quoting engine is much healthier now
- the remaining risk is no longer core pricing design
- the remaining risk is operational readiness and final data validation

## Next Best Actions

1. Review and approve the actual seeded go-live lanes in `docs/launch-corridor-matrix.md`.
2. Confirm whether `POM` is the only import `A2D` destination at launch.
3. Import and validate final launch customers/contacts on the target environment.
4. Verify production env vars, migrations, static files, and scheduled jobs.
5. Run final UAT in the deployed environment and mark each stop-ship item done.
