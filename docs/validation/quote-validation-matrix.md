# Quote Validation Matrix

This matrix maps every supported lane, service scope, and payment term combination to its expected core engine behavior.

## Core Rules & Definitions

1. **Shipment Classification (Direction)**:
   - PG → PG = `DOMESTIC`
   - PG → non-PG = `EXPORT`
   - non-PG → PG = `IMPORT`
   - non-PG → non-PG = Out of scope (Unsupported, raises `ValueError`)

2. **Required Components per Service Scope**:
   - `A2A` (or `P2P`): `{FREIGHT}`
   - `D2A`: `{ORIGIN_LOCAL, FREIGHT}`
   - `A2D`: `{DESTINATION_LOCAL}`
   - `D2D`: `{ORIGIN_LOCAL, FREIGHT, DESTINATION_LOCAL}`
   - `DOMESTIC` (Regardless of Scope): `{FREIGHT}` (As per domestic engine spec)

3. **Quote Type & SPOT Sourcing**:
   - **Standard Quote**: Generated when all required component rates exist in the database (`SPOT = False`).
   - **SPOT Quote**: Triggered when any required component rate is missing (`SPOT = True`).

---

## 24-Scenario Matrix

| # | Direction | Scope | Payment Term | Expected Charge Groups | Expected Quote Type | Expected SPOT Behavior | Notes |
|---|-----------|-------|--------------|------------------------|---------------------|------------------------|-------|
| 1 | IMPORT | A2A | PREPAID | Freight | Standard / SPOT | Spot if Freight missing | Standard rate is buy/sell air freight |
| 2 | IMPORT | A2A | COLLECT | Freight | Standard / SPOT | Spot if Freight missing | Standard rate is buy/sell air freight |
| 3 | IMPORT | D2A | PREPAID | Origin Local + Freight | Standard / SPOT | Spot if Origin or Freight missing | Origin charges mapped to non-PNG agent |
| 4 | IMPORT | D2A | COLLECT | Origin Local + Freight | Standard / SPOT | Spot if Origin or Freight missing | Origin charges mapped to non-PNG agent |
| 5 | IMPORT | A2D | PREPAID | Destination Local | Standard / SPOT | Spot if Dest missing | Destination charges mapped to PNG location |
| 6 | IMPORT | A2D | COLLECT | Destination Local | Standard / SPOT | Spot if Dest missing | Destination charges mapped to PNG location |
| 7 | IMPORT | D2D | PREPAID | Origin + Freight + Dest | Standard / SPOT | Spot if any component missing | Full door-to-door import workflow |
| 8 | IMPORT | D2D | COLLECT | Origin + Freight + Dest | Standard / SPOT | Spot if any component missing | Full door-to-door import workflow |
| 9 | EXPORT | A2A | PREPAID | Freight | Standard / SPOT | Spot if Freight missing | Standard rate is buy/sell air freight |
| 10| EXPORT | A2A | COLLECT | Freight | Standard / SPOT | Spot if Freight missing | Standard rate is buy/sell air freight |
| 11| EXPORT | D2A | PREPAID | Origin Local + Freight | Standard / SPOT | Spot if Origin or Freight missing | Origin charges mapped to PNG agent |
| 12| EXPORT | D2A | COLLECT | Origin Local + Freight | Standard / SPOT | Spot if Origin or Freight missing | Origin charges mapped to PNG agent |
| 13| EXPORT | A2D | PREPAID | Destination Local | Standard / SPOT | Spot if Dest missing | Destination charges mapped to non-PNG location |
| 14| EXPORT | A2D | COLLECT | Destination Local | Standard / SPOT | Spot if Dest missing | Destination charges mapped to non-PNG location |
| 15| EXPORT | D2D | PREPAID | Origin + Freight + Dest | Standard / SPOT | Spot if any component missing | Full door-to-door export workflow |
| 16| EXPORT | D2D | COLLECT | Origin + Freight + Dest | Standard / SPOT | Spot if any component missing | Full door-to-door export workflow |
| 17| DOMESTIC | A2A | PREPAID | Freight | Standard / SPOT | Spot if Freight missing | Domestic only requires Freight |
| 18| DOMESTIC | A2A | COLLECT | Freight | Standard / SPOT | Spot if Freight missing | Domestic only requires Freight |
| 19| DOMESTIC | D2A | PREPAID | Freight | Standard / SPOT | Spot if Freight missing | Domestic scope overrides ignore locals |
| 20| DOMESTIC | D2A | COLLECT | Freight | Standard / SPOT | Spot if Freight missing | Domestic scope overrides ignore locals |
| 21| DOMESTIC | A2D | PREPAID | Freight | Standard / SPOT | Spot if Freight missing | Domestic scope overrides ignore locals |
| 22| DOMESTIC | A2D | COLLECT | Freight | Standard / SPOT | Spot if Freight missing | Domestic scope overrides ignore locals |
| 23| DOMESTIC | D2D | PREPAID | Freight | Standard / SPOT | Spot if Freight missing | Domestic scope overrides ignore locals |
| 24| DOMESTIC | D2D | COLLECT | Freight | Standard / SPOT | Spot if Freight missing | Domestic scope overrides ignore locals |
