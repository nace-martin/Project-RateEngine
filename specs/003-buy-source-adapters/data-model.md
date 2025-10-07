# Data Model: BUY Source Adapters

**Date**: 2025-10-02

This data model defines the core structures for normalizing BUY-side pricing from various adapters.

## Enums

Located in `backend/pricing_v2/types_v2.py`

- **`ProvenanceType(Enum)`**: Identifies the source of a BUY offer.
  - `RATE_CARD`
  - `SPOT`
  - `MANUAL`

- **`FeeBasis(Enum)`**: Defines how a fee is calculated.
  - `PER_KG`
  - `PER_SHIPMENT`
  - `PERCENT_OF_BASE`

- **`Side(Enum)`**: Specifies the applicability of a fee.
  - `ORIGIN`
  - `DESTINATION`

- **`PaymentTerm(Enum)`**: Defines the payment terms.
  - `PREPAID`
  - `COLLECT`

## Dataclasses

Located in `backend/pricing_v2/dataclasses_v2.py`

- **`Provenance`**
  - `type: ProvenanceType`
  - `ref: str` (e.g., Rate card name or Spot reference)
  - `raw_blob_hash: str | None` (Hash of the raw source data)

- **`BuyBreak`**
  - `from_kg: float`
  - `rate_per_kg: float`

- **`BuyFee`**
  - `code: str` (Normalized fee code, e.g., `CLEAR`)
  - `basis: FeeBasis`
  - `rate: float`
  - `min_charge: float | None`
  - `max_charge: float | None`
  - `side: Side | None`
  - `depends_on: str | None` (e.g., `FUEL_PCT` depends on `CARTAGE`)

- **`BuyLane`**
  - `origin: str` (Airport code)
  - `destination: str` (Airport code)

- **`BuyOffer`**
  - `lane: BuyLane`
  - `currency: str`
  - `breaks: list[BuyBreak]`
  - `min_charge: float`
  - `fees: list[BuyFee]`
  - `valid_from: date`
  - `valid_to: date`
  - `provenance: Provenance`

- **`BuyMenu`**
  - `offers: list[BuyOffer]`

- **`QuoteContext`**
  - `shipment_pieces: list[...]`
  - `audience: str` (e.g., `PNG_SHIPPER`, `OVERSEAS_AGENT_AU`)
  - `payment_term: PaymentTerm`
  - `compute_at: datetime`
