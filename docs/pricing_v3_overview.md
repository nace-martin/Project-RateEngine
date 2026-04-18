# Pricing V3 Overview

> [!WARNING]
> **Legacy Documentation**
> This document describes the V3 pricing area, which is now in maintenance mode.
> The active development standard is **Pricing V4**.
> Refer to [Pricing V4 Overview](./pricing_v4_overview.md) for the primary engine design.

## Introduction

`pricing_v3` introduced a "Charge Engine + Resolver" direction for older quote calculation work. That historical context is still useful, but the live Spot workflow no longer uses the older quote-scoped Spot-rate model.

## Core Concepts

### 1. Resolvers

Resolvers fetch buy-side inputs and normalize them into engine-friendly structures.

- **ContractRateResolver**
  - Source: `RateCard` / `RateLine`
  - Priority: lower than explicit Spot overlay
  - Logic: matches geography, component, and coverage
  - Use case: standard contracted partner pricing

- **LocalFeeResolver**
  - Source: `LocalFeeRule`
  - Priority: lowest
  - Use case: standard system-wide fees when no more specific source exists

### 2. Engine Types (`engine_types.py`)

Pure Python dataclasses are used to pass validated pricing data into the engine layer.

- **`BuyCharge`**
  - Represents a resolved cost input
  - Carries source, pricing method, currency, and rate values

### 3. Models (`models.py`)

#### Geography

- **`Zone`**: A collection of locations
- **`ZoneMember`**: Links a `Location` to a `Zone`

#### Contract Rates

- **`RateCard`**: A set of supplier rates valid for a mode and coverage pattern
- **`RateLine`**: A rate for a specific component inside a card
- **`RateBreak`**: Weight-break details for tiered pricing

#### Spot Pricing Envelope Overlay

The active Spot workflow is SPE-driven rather than `QuoteSpotRate`-driven.

- **`SpotPricingEnvelopeDB`**
  - The persisted Spot Pricing Envelope linked to a quote when Spot workflow is required
  - Stores immutable shipment context in `shipment_context_json`
  - Stores a context integrity hash in `shipment_context_hash`
  - Stores Spot lifecycle state: `draft`, `ready`, `expired`, `rejected`
  - Stores Spot trigger audit fields: `spot_trigger_reason_code`, `spot_trigger_reason_text`

- **`SPESourceBatchDB`**
  - Stores one imported or manual Spot intake source
  - Represents agent text, airline reply, PDF-derived source, or manual entry batch

- **`SPEChargeLineDB`**
  - Stores the validated Spot charge rows attached to an envelope
  - May be associated with a source batch for auditability

- **`SPEAcknowledgementDB`**
  - Stores the sales acknowledgement record before quote creation

#### Local Fees

- **`LocalFeeRule`**: Global rules for default charges

## Live Spot Pricing Flow

The current Spot path is:

1. Frontend detects a Spot trigger and creates a `SpotPricingEnvelopeDB`.
2. Users import or enter Spot charge lines into the SPE.
3. Quote creation passes `spot_envelope_id` into `PricingServiceV4Adapter`.
4. `PricingServiceV4Adapter.calculate_charges()` computes the standard lines first.
5. `_calculate_spot_lines()` reconstructs the SPE from `SpotPricingEnvelopeDB` and converts envelope charges into calculated Spot lines.
6. `_merge_charge_lines()` overlays Spot lines onto the standard output.
   - Domestic shipments append Spot lines alongside standard charges.
   - Non-domestic shipments use bucket-level overlay so Spot coverage replaces standard coverage for supplied buckets.
7. The final hybrid result is persisted as canonical quote lines and totals.

This means the live Spot architecture is an **SPE-driven V4 hybrid overlay**, not a quote-scoped Spot-rate CRUD subsystem.

## Current State

The `pricing_v3` module still exists alongside older pricing code, but active Spot workflow logic now depends on:

- `backend/quotes/spot_models.py`
- `backend/quotes/spot_views.py`
- `backend/quotes/spot_services.py`
- `backend/pricing_v4/adapter.py`

## Practical Guidance

- Do not build new work around `QuoteSpotRate` or `QuoteSpotCharge`.
- Treat the SPE plus `PricingServiceV4Adapter` as the active Spot pricing model.
- Treat Spot charge data as an overlay on top of standard V4 pricing rather than a separate quote-only charge store.
