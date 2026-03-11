# Incoterms® Reference for Rate Engine

This document defines how Incoterms affect which charges are included in a quote and who bears the costs/risks at each stage of the shipment journey.

## Shipment Journey Stages

The complete logistics chain consists of these stages:

```
Origin → Inland Freight → Export Customs → Terminal Handling (Origin) → 
Ocean/Air Transport → Terminal Handling (Destination) → Import Customs → 
Inland Freight → Destination
```

## Incoterms for All Modes of Transport

### EXW - Ex Works (named place of delivery)
**Seller Responsibility:** Packing only  
**Buyer Responsibility:** Export, Freight, Import, Delivery

| Stage | Costs | Risks |
|-------|-------|-------|
| Origin | Seller | Seller |
| Inland Freight (Origin) | Buyer | Buyer |
| Export Customs | Buyer | Buyer |
| Terminal Handling (Origin) | Buyer | Buyer |
| Main Transport | Buyer | Buyer |
| Terminal Handling (Dest) | Buyer | Buyer |
| Import Customs | Buyer | Buyer |
| Inland Freight (Dest) | Buyer | Buyer |
| Destination | Buyer | Buyer |

**Rate Engine Logic:** 
- Quote includes: ALL charges (buyer pays everything for freight forward)
- For EXW Export D2A: Include pickup, terminal fees, freight, but NOT destination charges

---

### FCA - Free Carrier (named place of delivery)
**Seller Responsibility:** Transport to carrier/terminal  
**Buyer Responsibility:** Main freight onwards, import, delivery

| Stage | Costs | Risks |
|-------|-------|-------|
| Origin | Seller | Seller |
| Inland Freight (Origin) | Seller | Seller |
| Export Customs | Depends on named place | Seller |
| Terminal Handling (Origin) | Buyer | Buyer |
| Main Transport | Buyer | Buyer |
| Terminal Handling (Dest) | Buyer | Buyer |
| Import Customs | Buyer | Buyer |
| Inland Freight (Dest) | Buyer | Buyer |
| Destination | Buyer | Buyer |

**Rate Engine Logic:**
- Quote includes: Terminal handling (origin), freight, terminal handling (dest)
- Export customs depends on named place (if terminal = buyer, if seller's premises = seller)

---

### CPT - Carriage Paid To (named place of destination)
**Seller Responsibility:** Freight to destination  
**Buyer Responsibility:** Unloading, import duty, customs, delivery

| Stage | Costs | Risks |
|-------|-------|-------|
| Origin | Seller | Seller |
| Inland Freight (Origin) | Seller | Seller |
| Export Customs | Seller | Seller |
| Terminal Handling (Origin) | Seller | Seller |
| Main Transport | Seller | Buyer (from handover) |
| Terminal Handling (Dest) | Seller | Buyer |
| Import Customs | Buyer | Buyer |
| Inland Freight (Dest) | Buyer | Buyer |
| Destination | Buyer | Buyer |

**Rate Engine Logic:**
- Seller quotes: Origin + Freight + Terminal Handling through to destination airport
- Buyer pays: Import customs, inland delivery

---

### CIP - Carriage and Insurance Paid To (named place of destination)
**Same as CPT + Seller must provide cargo insurance**

**Rate Engine Logic:**
- Same as CPT
- Additionally: Seller must include cargo insurance premium

---

### DAP - Delivered at Place (named place of destination)
**Seller Responsibility:** Deliver to final destination  
**Buyer Responsibility:** Unloading, import duty, customs clearance

| Stage | Costs | Risks |
|-------|-------|-------|
| Origin | Seller | Seller |
| Inland Freight (Origin) | Seller | Seller |
| Export Customs | Seller | Seller |
| Terminal Handling (Origin) | Seller | Seller |
| Main Transport | Seller | Seller |
| Terminal Handling (Dest) | Seller | Seller |
| Import Customs | Buyer | Buyer |
| Inland Freight (Dest) | Seller | Seller |
| Destination | Seller | Seller |

**Rate Engine Logic:**
- Seller quotes: EVERYTHING except import duty/taxes/customs clearance
- For **Import A2D DAP**: Destination pricing comes from Pricing V4 local tariffs (`LocalSellRate`), not legacy A2D DAP tables
- Buyer pays: Import customs clearance, duties, taxes only

---

### DPU - Delivered at Place Unloaded (named place of destination)
**Seller Responsibility:** Deliver AND unload at destination  
**Buyer Responsibility:** Import duty, customs clearance

**Rate Engine Logic:**
- Same as DAP + unloading costs at destination

---

### DDP - Delivered Duty Paid (named place of destination)
**Seller Responsibility:** EVERYTHING including import duties  
**Buyer Responsibility:** None (just receive goods)

| Stage | Costs | Risks |
|-------|-------|-------|
| All Stages | Seller | Seller |

**Rate Engine Logic:**
- Seller quotes: ALL charges including import customs, duties, taxes
- This is the most comprehensive seller responsibility

---

## Incoterms for Sea/Inland Waterway Only

### FAS - Free Alongside Ship (named port of shipment)
**Seller Responsibility:** Deliver goods alongside vessel  
**Buyer Responsibility:** Loading, freight, import

---

### FOB - Free on Board (named port of shipment)
**Seller Responsibility:** Load goods onto vessel  
**Buyer Responsibility:** Freight, import, delivery

| Stage | Costs | Risks |
|-------|-------|-------|
| Origin | Seller | Seller |
| Inland Freight (Origin) | Seller | Seller |
| Export Customs | Seller | Seller |
| Terminal Handling (Origin) | Seller | Seller |
| Main Transport | Buyer | Buyer |
| All Destination Stages | Buyer | Buyer |

---

### CFR - Cost and Freight (named port of destination)
**Seller Responsibility:** Freight to buyer's port  
**Buyer Responsibility:** Unloading, import, delivery

---

### CIF - Cost, Insurance and Freight (named port of destination)
**Same as CFR + Seller provides cargo insurance**

---

## Rate Engine Implementation Notes

### Current Supported Incoterms
- **EXW** - Ex Works (Export default)
- **FCA** - Free Carrier (Export with pickup)
- **DAP** - Delivered at Place (Import A2D default)
- **DDP** - Delivered Duty Paid (Full service)

### Charge Buckets by Incoterm

| Incoterm | Origin Charges | Freight | Destination Charges |
|----------|----------------|---------|---------------------|
| EXW | Buyer | Buyer | Buyer |
| FCA | Seller (to carrier) | Buyer | Buyer |
| CPT | Seller | Seller | Buyer (import only) |
| DAP | Seller | Seller | Buyer (import customs only) |
| DDP | Seller | Seller | Seller |

### Service Scope Mapping

| Scope | Description | Typical Incoterms |
|-------|-------------|-------------------|
| D2D | Door to Door | DAP, DDP |
| D2A | Door to Airport | EXW, FCA |
| A2D | Airport to Door | DAP |
| A2A | Airport to Airport | EXW, FCA |

---

## References
- Maersk Incoterms Guide: https://www.maersk.com/
- ICC Official Incoterms® 2020: https://iccwbo.org/resources-for-business/incoterms-rules/

