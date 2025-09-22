# Data Model

This feature does not introduce any new database models. It utilizes existing BUY/SELL models and seed data.

The following dataclasses will be used or extended to support the new deterministic policy for currency and fee selection:

- **QuoteContext**: Will be used as input, potentially with new fields for policy flags.
- **NormalizedContext**: Result of the `normalize` function, may include derived audience and invoice currency.
- **BuyResult**: Result of the `rate_buy` function, will include details on selected fees.
- **SellResult**: Result of the `map_to_sell` function, will reflect the new fee menu and currency rules.
- **Totals**: The final result, including `invoice_ccy`, `is_incomplete` flag, and `reasons` for manual intervention.
- **Snapshot**: A machine-readable record of policy decisions, skipped fees, and reasons.

These will be defined or updated in `pricing_v2/dataclasses_v2.py`.
