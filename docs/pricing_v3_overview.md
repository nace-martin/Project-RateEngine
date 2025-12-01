# Pricing V3 Overview

## Introduction
`pricing_v3` is a new Django app designed to modernize the rate resolution logic. It introduces a "Charge Engine + Resolver" pattern, separating the **finding** of rates from the **calculation** of charges.

## Core Concepts

### 1. Resolvers
Resolvers are responsible for fetching "Buy Rates" from different sources and normalizing them into a `BuyCharge` object.

- **SpotRateResolver**: 
  - Source: `QuoteSpotRate` / `QuoteSpotCharge`
  - Priority: 1 (Highest)
  - Use case: Ad-hoc rates entered specifically for a quote (e.g., email quotes).

- **ContractRateResolver**:
  - Source: `RateCard` / `RateLine`
  - Priority: 2
  - Logic: Matches `Zone` (Origin/Destination) and `ServiceComponent`.
  - Use case: Agreed rates with partners/customers.

- **LocalFeeResolver**:
  - Source: `LocalFeeRule`
  - Priority: 3 (Lowest)
  - Use case: Standard system-wide fees (e.g., cartage, documentation) that apply if no specific contract exists.

### 2. Engine Types (`engine_types.py`)
Pure Python dataclasses used to pass data between the Resolver and the Charge Engine.

- **`BuyCharge`**: Represents a resolved cost.
  - `source`: 'SPOT', 'CONTRACT', 'LOCAL_FEE'
  - `method`: 'FLAT', 'PER_UNIT', 'WEIGHT_BREAK', 'PERCENT'
  - `rate_per_unit`, `flat_amount`, `breaks`: The actual cost numbers.
  - `currency`: The currency of the cost.

### 3. Models (`models.py`)

#### Geography
- **`Zone`**: A collection of locations (e.g., "AU East Coast").
- **`ZoneMember`**: Links a `Location` to a `Zone`.

#### Contract Rates
- **`RateCard`**: A set of rates from a supplier, valid for a specific mode and zone pair.
- **`RateLine`**: A specific rate for a `ServiceComponent` within a card.
- **`RateBreak`**: Weight breaks for tiered pricing.

#### Spot Rates
- **`QuoteSpotRate`**: A container for spot rates linked to a specific `Quote`.
- **`QuoteSpotCharge`**: The actual rate line for a component.

#### Local Fees
- **`LocalFeeRule`**: Global rules for default charges.

## Integration Plan

### Current State
The `pricing_v3` module exists alongside the legacy `pricing_v2` / `ratecards` apps. It is not yet wired into the main `PricingServiceV3`.

### Next Steps
1. **Connect to Charge Engine**: Create a new `ChargeEngine` class that accepts `BuyCharge` objects and applies:
   - Currency conversion (using `FxSnapshot`)
   - Margins (using `Policy`)
   - Minimums (Buy vs Sell)
   - Tax (GST/VAT)
2. **Replace `_get_buy_rate`**: Update `PricingServiceV3` to use `BuyChargeResolver` instead of the legacy `PartnerRate` lookup.
3. **UI Integration**: Build UI for managing Zones and Rate Cards.
