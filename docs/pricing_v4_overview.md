# Pricing V4 Overview "Greenfield"

## Introduction
`pricing_v4` is the current standard pricing engine for RateEngine. It replaces the V3 "Resolver" pattern with a strict, database-driven "Greenfield" architecture designed for auditability and commercial clarity.

## Core Design Principles (The "Non-Negotiables")

1.  **No Shared Rate Tables**: COGS (Buying) and Sell Rates must stay in separate tables.
2.  **COGS and Sell Never Touch**: The cost logic is completely decoupled from the sell logic. We do not apply a "mark-up" to a cost to get a price; we look up a market price separately.
3.  **One ProductCode = One Commercial Truth**: Every line item on a quote must map to a single `ProductCode` that defines its GL codes, Tax treatment, and Category.
4.  **Direction-Specific Definitions**: Import and Export schemas are separate (e.g., `ImportCOGS` vs `ExportCOGS`) to reflect the physical reality of freight movement.
5.  **Duplication > Ambiguity**: It is better to duplicate data (e.g., repeating a surcharge for multiple lanes) than to have ambiguous "magic" rules.
6.  **No Magic Flags**: Rate tables should not have hidden boolean flags that alter logic. Logic should be explicit.
7.  **ProductCode Before Rates**: You cannot create a rate without a pre-existing `ProductCode`.

## Core Components

### 1. Master Registry (`ProductCode`)
The `ProductCode` model is the single source of truth for what we sell.
*   **IDs**: Manually assigned (1xxx=Export, 2xxx=Import, 3xxx=Domestic).
*   **Attributes**: GL Codes, GST Treatment (Standard, Zero-Rated, Exempt), Category (Freight, Handling, etc.).

### 2. Entity Management
*   **Carrier**: Airlines and Shipping Lines (e.g., Air Niugini, Qantas). Used for Freight Linehaul COGS.
*   **Agent**: Freight Forwarders and Partners (e.g., EFM AU). Used for Origin/Destination/Clearing services.

### 3. Rate Architecture
Rates are split into **COGS** (what we pay) and **Sell Rates** (what we charge).

#### Export
*   `ExportCOGS`: Links to `Carrier` (Freight) or `Agent` (Services).
*   `ExportSellRate`: The market rate provided to the customer.

#### Import
*   `ImportCOGS`: Links to `Carrier` or `Agent`.
*   `ImportSellRate`: The market rate provided to the customer.

#### Domestic
*   `DomesticCOGS` & `DomesticSellRate`: Zone-to-Zone pricing (e.g., POM->LAE).

### 4. Global Surcharges
The `Surcharge` model handles fees that apply broadly across service types, reducing the need to duplicate rates for every single route.
*   **Scopes**: `DOMESTIC_AIR`, `EXPORT_AIR`, `IMPORT_AIR`, etc.
*   **Types**: Flat Fee, Per KG, or Percentage.

## Integration
The V4 engine exposes computation via the `pricing_v4.engine` module. It is integrated into the API via `/api/v4/`.

## Migration from V3
V3 is deprecated. New development should focus exclusively on V4 models and logic.
