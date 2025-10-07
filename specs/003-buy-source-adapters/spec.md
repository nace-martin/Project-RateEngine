# Spec: BUY Source Adapters (“Universal Translator”) 
## 1) Problem 
Partner pricing arrives in many shapes (HTML rate cards, spreadsheets, emails). Manually interpreting these slows quoting and introduces errors. We lack a single, reliable way to normalize “buy” prices and apply our business rules consistently. 
## 2) Proposed Solution (what & why) 
Create **BUY Source Adapters** that translate any external price (rate card or spot email) into one internal format: **Adapters → BuyOffer/BuyMenu → Deterministic selection → Recipes → Totals**. 
Why this wins: 
- Core logic stays simple and testable. 
- New partners = new adapter, not a core rewrite. 
- We can compare sources, enforce currency/fee-scope rules, and never crash on gaps. 
## 3) Goals 
- **Speed:** Cut time-to-quote by auto-reading our cards and mapped spot quotes. 
- **Accuracy:** Apply weight breaks, mins/caps, percent-of fees correctly every time. 
- **Flexibility:** Plug in new sources without changing the engine. 
- **Reliability:** If data is missing, return a safe, clear **incomplete** result—no 500s. 
## 4) Non-Functional (from Constitution) 
- **No 500s on data gaps.** Return `is_incomplete=true` with one human reason. 
- **Performance budgets:** adapters ≤ **2s** each (run in parallel); total compute ≤ **3s prod / 5s dev**. 
- **Deterministic selection:** Contracted RateCard → Current RateCard → Pinned Spot; ties: newer `valid_from` → cheaper → carrier priority. 
- **Validity:** Offers must satisfy `valid_from ≤ compute_at ≤ valid_to` (or be excluded). 
- **Observability:** Snapshot per calc with `calc_id`, policy/version, adapter_versions, selection_rationale, included/skipped fees (+ reasons), `phase_timings_ms`. 
- **RBAC:** Sales = sell-only; Manager/Finance = full snapshot, BUY/FX. 
## 5) Policy Matrix (currency & fee-scope) 
| Flow | Audience (payer) | Invoice CCY | Fee Scope on Quote | 
|--------------------------|-----------------------------|-------------|-------------------------| 
| Import **A2D** – **PREPAID**| PNG customer (prepaid) | **AUD** | **Destination-side only** | 
| Import **A2D** – **COLLECT**| Overseas agent (collect) | **PGK** | **Destination-side only** | 
| Export – Overseas (**AU**) | Overseas agent (AU lanes) | **AUD** | **Origin-side only** | 
| Export – Overseas (non-AU) | Overseas agent (non-AU) | **USD** | **Origin-side only** | 
| Export – PNG shipper | PNG shipper | **PGK** | **Origin-side only** | 
Notes: 
- **Chargeable weight (air):** `max(actual_kg, CBM×167)`; round **up to whole kg**. 
- **Percent-of fees** (e.g., fuel%) apply to the **final base after min/cap, pre-tax**. 
- **Disbursement** only on **DDP** (5% with min/cap per card). 
## 6) Scope (this spec) 
- Mode: **AIR**. 
- Scopes supported: **Import A2D**, **Export (A2A/A2D)**. 
- Adapters MVP: 
- **RateCardAdapter v1**: reads our provided HTML cards (AUD/PGK/USD). 
- **SpotAdapter v1**: “Paste & Map” (manual field mapping from emails). No LLM parsing in v1. 
## 7) User Scenarios 
- **A2D PREPAID (AUD):** As Commercial Manager, I enter shipment details; the system auto-applies the AUD A2D card, shows destination-side lines only, and totals in AUD. 
- **A2D COLLECT (PGK):** Same flow; system uses PGK A2D card and totals in PGK. 
- **Compare sources:** After card pricing appears, I paste a spot email, map AF/kg + fees, and see both options to choose/pin. 
- **Door-to-Door assembly:** When a leg (D2A/A2A/A2D) is missing, the UI shows “Needs rate: [leg]” and generates a pre-filled partner request; when returned, I paste/map and recompute. 
## 8) Out of Scope (v1) 
- Automatic email text parsing (LLM/regex)—future phase. 
- Partner portal—future phase. 
- Full DB for rate cards—MVP reads our specific HTML cards; DB tables may come later. 
## 9) Success Metrics 
- **Speed:** Median quote compute ≤ **1.5s**; p95 ≤ **3s**. 
- **Quality:** Zero 500s in adapter path; <1% retries hit breaker. 
- **Accuracy:** Golden-case tests (A2D AUD/PGK; Export AUD/USD/PGK) pass with exact mins/caps/%/GST math. 
## 10) Acceptance Criteria 
- **AC1 – A2D PREPAID (AUD):** Given 100 kg BNE→POM, the engine returns destination-side lines from the **AUD** A2D card, applies cartage min/cap then fuel% (pre-tax), adds GST, totals in **AUD**. 
- **AC2 – A2D COLLECT (PGK):** Given 63 kg PVG→POM, same lines but priced off the **PGK** A2D card; totals in **PGK**. 
- **AC3 – Export (origin-side only):** Overseas agent (AU lane) totals in **AUD**; non-AU in **USD**; PNG shipper in **PGK**—only origin-side lines shown. 
- **AC4 – Spot compare:** After card pricing, a mapped spot email creates a second option; user can **pin** it; selection reflects our priority/tie-break rules and is explained in `snapshot.selection_rationale`. 
- **AC5 – Missing BUY:** If no valid offer exists, response is **HTTP 200** with `is_incomplete=true` and one human-readable reason (e.g., “BUY lane/break missing PVG→POM (+45kg)”). 
- **AC6 – Snapshot:** Response includes `calc_id`, `policy_key/version`, `adapter_versions`, `selection_rationale`, `included_fees`, `skipped_fees_with_reasons[]`, and `phase_timings_ms`. 
- **AC7 – RBAC:** Sales response excludes BUY/COGS/FX internals; Manager/Finance includes them. 
## 11) Dependencies & References 
- **Constitution:** governing principles (determinism, budgets, RBAC, snapshot). 
- **QuotingMatrix.md:** business rules for currency and fee scope. 
- **Rate cards:** 2025 A2D AUD/PGK/USD HTML files (source for RateCardAdapter v1).
