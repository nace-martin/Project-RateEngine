# RFC: Multi-Leg Air Freight Rating with Incoterms and COGS/Sell Separation

**Author:** Nason Martin  
**Date:** 2025-08-27  
**Status:** Draft (North Star Vision)  
**Target System:** RateEngine (Air Freight Module)

---

## 1. Problem

Our current MVP handles air freight as a **single cost component** (e.g., PGK rate × chargeable weight).  
In reality, air shipments consist of **multiple legs** (pickup, terminals, linehaul, clearance, delivery), often priced differently depending on the **service type** (Door↔Airport/Door) and **Incoterms** (EXW, FCA, CPT, DAP, DDP).  

We must evolve RateEngine into a system that:  
- Correctly selects the required legs,  
- Applies appropriate rating logic (per kg, per CBM, per shipment, per zone),  
- Manages mixed currencies and FX conversions,  
- Keeps **COGS (buy)** and **Sell (client-facing)** clearly separated,  
- Provides an auditable breakdown without overwhelming sales users.  

---

## 2. Goals

- Model shipments as **composed of legs**, each with its own costs and rules.  
- **Resolve legs** based on Service Type × Incoterm × country rules.  
- Rate each leg independently (respecting weight breaks, mins, and surcharges).  
- Support **multi-currency COGS**, FX + CAF adjustments, and unified Sell in client currency.  
- Apply margins at either overall or per-category level.  
- Return **simple Sell totals** to sales reps; expose full breakdown to finance.  
- Persist **FX snapshots and COGS/Sell separation** for auditability.  
- Provide fallbacks when leg rates are missing (e.g., auto-generate agent rate request).  

---

## 3. Non-Goals

- Automated airline/agent API integrations (future).  
- Full duty/tax calculations (beyond placeholders for DDP).  
- Transit time optimization.  

---

## 4. Leg Model

### Standard Legs
- **Pickup** – Shipper door → Origin terminal.  
- **Export Clearance** – Documentation, permits, customs lodge.  
- **Origin Terminal** – Handling, security screening, airline docs.  
- **Linehaul Air** – Main flight; rated by chargeable kg.  
- **Destination Terminal** – PSC, delivery order, handling.  
- **Import Clearance** – Broker fees, duties/taxes, inspections.  
- **Delivery** – Destination terminal → Consignee door.  

### Service Type → Base Legs
| Service Type | Included Legs |
|--------------|---------------|
| Door → Airport (D2A) | Pickup, Export Clearance, Origin Terminal, Linehaul Air |
| Airport → Airport (A2A) | Origin Terminal, Linehaul Air, Destination Terminal |
| Door → Door (D2D) | Pickup, Export Clearance, Origin Terminal, Linehaul Air, Destination Terminal, Import Clearance, Delivery |
| Airport → Door (A2D) | Linehaul Air, Destination Terminal, Import Clearance, Delivery |

### Incoterm Clamp
- **EXW**: ensure Pickup included.  
- **FCA**: from Origin Terminal onward.  
- **CPT/CIP**: exclude import clearance/delivery.  
- **DAP**: include delivery, exclude duties/taxes.  
- **DDP**: include delivery + duties/taxes.  

**Why:** Incoterms define the **legal and financial responsibility** for each shipment leg. Since they reflect the binding contract between buyer and seller, they must take precedence over the operational service type when determining which legs to include.  

---

## 5. Rating Logic

### Weight/Measure Basis
- **Linehaul Air**: Chargeable kg = max(gross kg, CBM × 167).  
- **Pickup/Delivery**: Per CBM, per ton, per zone, or flat.  
- **Terminals**: Per shipment or per kg with minimums.  
- **Clearance**: Flat per entry + add-ons (per line, DG, etc.).  

### Calculation Steps
1. Compute shipment metrics: gross, CBM, volumetric kg, chargeable kg.  
2. Resolve applicable legs.  
3. For each leg, look up rate components and compute **COGS native** (with min/weight break logic).  
   - *Example:* A 60 kg shipment may rate cheaper at the **+100 kg tier** than the **+45 kg tier**. Always select the cheapest applicable break, not just the first valid tier.  
4. Convert each leg’s COGS to a **valuation currency (PGK)** with FX+CAF snapshot.  
5. Sum legs for total COGS (valuation currency).  
6. Convert to client currency (USD/AUD/PGK).  
7. Apply margin(s) + rounding + minimum fee rules.  
8. Return Sell totals (masked COGS for sales).  

---

## 6. COGS vs Sell Separation

- **COGS (internal)**: Carrier buy rates, surcharges, native currencies, FX snapshots.  
- **Sell (client-facing)**: Final quote in client currency after FX, CAF, margins, rounding.  

**Rule:** Sales reps **never see COGS**. Finance/Managers can access both via permissions.  

This ensures:  
- Sales quotes are consistent and safe.  
- Finance can track profitability.  
- Quotes are fully auditable.  

---

## 7. FX Handling

- Each leg may be in a different native currency (AUD, PGK, USD).  
- Convert each to PGK using **leg-specific FX snapshot + CAF**.  
- Sum for **total COGS (PGK)**.  
- Convert once more to client currency (AUD/USD/PGK) for Sell.  
- Persist snapshots for traceability.  

---

## 8. Margins

- **Option A (default)**: Apply one overall margin to total COGS.  
- **Option B (future)**: Apply per-category margins (e.g., Linehaul 10%, Pickup/Delivery 20%).  

---

## 9. Rounding & Minimums

- Enforce **per-leg minimums** first.  
- Apply **overall rounding** (nearest 10/up 1).  
- Enforce **overall minimum charge** in client currency.  

---

## 10. Fallbacks

If a required leg has no rate:  
- Mark the quote as `incomplete`.  
- Generate an agent rate-request draft (with shipment summary).  
- Allow the quote to be saved with placeholders.  

---

## 11. Security & Visibility

- **Sales**: See only Sell (client-facing).  
- **Finance/Managers**: Access both COGS and Sell.  
- Enforced via API masking + role-based permissions.  

---

## 12. Rollout Plan

1. **MVP-Lite**: Single-leg (linehaul air), chargeable weight, COGS vs Sell, PDF output.  
2. **Ancillary Charges**: Add DG, fuel, handling as flat line items.  
3. **Multi-Leg Prototype**: Add one extra leg (Delivery) to prove leg model works.  
4. **Full Rollout**: Implement leg resolution + Incoterm logic.  
5. **Advanced**: Per-category margins, fallbacks, duties/taxes, airline integrations.  

---

## 13. Acceptance Criteria

- Service Type + Incoterm → correct leg set.  
- Chargeable kg calculated correctly (167 factor).  
- Rates applied per leg with correct basis and minimums.  
- FX snapshots persisted.  
- Sales never exposed to COGS.  
- Finance sees both.  
- Incomplete quotes trigger fallback path.  

---

## 14. Open Questions

- Do we need per-airline overrides (e.g., screening per piece vs per shipment)?  
- How will cartage zones be defined (km or postcode tables)?  
- Default margin strategy: overall or per-category by client?  
- Should rounding rules be global or per-currency?  
- **Data Sources:** What will be the source of truth for leg-based COGS? Will this data be entered manually via Django Admin, imported from carrier spreadsheets, or synced from external systems?  

---

## 15. Summary

This RFC defines the **North Star architecture** for RateEngine’s Air Freight module.  
It moves from single-component quotes to a **multi-leg, Incoterm-aware rating engine**, with strict COGS/Sell separation, auditability, and future scalability.  

While too complex for immediate MVP, it provides the **blueprint for incremental growth**.  
Every new feature should align with this architecture to ensure RateEngine evolves into a professional-grade quoting system.  

---
