# Pricing Runtime Selection Rules

This document defines the canonical quote-time lookup rules for active V4 rate tables.

The runtime selector must use the same effective dimensions the admin manager validates.
It must not silently ignore currency, counterparty, or effective-date boundaries.

## Shared Rules

- All selectors hard-match `product_code`.
- All selectors hard-match the quote date against `valid_from <= quote_date <= valid_until`.
- All selectors use deterministic ordering:
  `order_by('-valid_from', '-updated_at', '-id')`
- If a selector stage leaves one or more dimensions unresolved and multiple distinct values remain across those dimensions, runtime must raise an ambiguity error.
- If no selector stage matches, runtime returns no match.

## ExportSellRate

- Hard-match fields:
  `product_code`, `origin_airport`, `destination_airport`, quote-date validity
- Exact currency stage:
  `currency`
- Allowed fallback:
  `PGK` fallback only when the caller explicitly allows it
- Tie-break:
  latest `valid_from`, then `updated_at`, then `id`
- Ambiguity:
  if currency is not provided and multiple currencies remain
- No-match:
  explicit no-match error

## ImportSellRate

- Hard-match fields:
  `product_code`, `origin_airport`, `destination_airport`, quote-date validity
- Exact currency stage:
  `currency`
- Allowed fallback:
  `PGK` fallback only when the caller explicitly allows it
- Tie-break:
  latest `valid_from`, then `updated_at`, then `id`
- Ambiguity:
  if currency is not provided and multiple currencies remain
- No-match:
  explicit no-match error

## DomesticSellRate

- Hard-match fields:
  `product_code`, `origin_zone`, `destination_zone`, quote-date validity
- Exact currency stage:
  `currency`
- Allowed fallback:
  none beyond single-currency unambiguous selection
- Tie-break:
  latest `valid_from`, then `updated_at`, then `id`
- Ambiguity:
  if currency is omitted and multiple currencies somehow remain
- No-match:
  explicit no-match error

## ExportCOGS

- Hard-match fields:
  `product_code`, `origin_airport`, `destination_airport`, quote-date validity
- Exact dimensions:
  `carrier_id` or `agent_id`, plus `currency` when provided
- Allowed fallback:
  only when omitted dimensions collapse to a single remaining value
- Tie-break:
  latest `valid_from`, then `updated_at`, then `id`
- Ambiguity:
  if multiple counterparties remain without explicit counterparty
  if multiple currencies remain without explicit currency
- No-match:
  explicit no-match error

## ImportCOGS

- Hard-match fields:
  `product_code`, `origin_airport`, `destination_airport`, quote-date validity
- Exact dimensions:
  `carrier_id` or `agent_id`, plus `currency` when provided
- Allowed fallback:
  only when omitted dimensions collapse to a single remaining value
- Tie-break:
  latest `valid_from`, then `updated_at`, then `id`
- Ambiguity:
  if multiple counterparties remain without explicit counterparty
  if multiple currencies remain without explicit currency
- No-match:
  explicit no-match error

## DomesticCOGS

- Hard-match fields:
  `product_code`, `origin_zone`, `destination_zone`, quote-date validity
- Exact dimensions:
  `carrier_id` or `agent_id`, plus `currency` when provided
- Allowed fallback:
  only when omitted dimensions collapse to a single remaining value
- Tie-break:
  latest `valid_from`, then `updated_at`, then `id`
- Ambiguity:
  if multiple counterparties remain without explicit counterparty
- No-match:
  explicit no-match error

## LocalSellRate

- Hard-match fields:
  `product_code`, `location`, `direction`, quote-date validity
- Exact dimensions:
  `payment_term`, `currency`
- Allowed fallback order:
  1. exact payment term + exact currency
  2. `ANY` payment term + exact currency
  3. `PGK` fallback only when the caller explicitly allows it
- Tie-break:
  latest `valid_from`, then `updated_at`, then `id`
- Ambiguity:
  if currency is omitted and multiple currencies remain inside a payment-term stage
- No-match:
  explicit no-match error

## LocalCOGSRate

- Hard-match fields:
  `product_code`, `location`, `direction`, quote-date validity
- Exact dimensions:
  `carrier_id` or `agent_id`, plus `currency` when provided
- Allowed fallback:
  only when omitted dimensions collapse to a single remaining value
- Tie-break:
  latest `valid_from`, then `updated_at`, then `id`
- Ambiguity:
  if multiple counterparties remain without explicit counterparty
  if multiple currencies remain without explicit currency
- No-match:
  explicit no-match error

## Runtime Notes

- Sell-side fallback paths are intentionally limited and explicit.
- COGS selectors do not invent a generic counterparty. If the caller does not provide one, the remaining active rows must still collapse to a single counterparty.
- Current quote payloads do not always carry carrier or agent IDs. In those cases runtime can still resolve safely only when the remaining rows are unambiguous.
