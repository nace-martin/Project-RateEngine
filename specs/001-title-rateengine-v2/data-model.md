# Data Model

This feature does not introduce any new database models. It utilizes existing BUY/SELL models and seed data.

The following dataclasses will be used to pass data between the pure functions of the new rating core:

- **QuoteContext**: The initial input to the rating process.
- **NormalizedContext**: The result of the `normalize` function.
- **BuyResult**: The result of the `rate_buy` function.
- **SellResult**: The result of the `map_to_sell` function.
- **Totals**: The final result of the `tax_fx_round` function.

These will be defined in `pricing_v2/dataclasses_v2.py`.

## Dataclass Details

### QuoteContext

| Field Name    | Description                                     |
| :------------ | :---------------------------------------------- |
| `mode`        | Mode of transport (e.g., "AIR")               |
| `scope`       | Scope of the quote (e.g., "A2D")              |
| `payment_term`| Payment terms (e.g., "PREPAID", "COLLECT") |
| `origin_iata` | Origin IATA code (e.g., "BNE")                |
| `dest_iata`   | Destination IATA code (e.g., "POM")           |
| `pieces`      | List of pieces with weight, dimensions, etc.    |
| `audience`    | Optional: Audience for the quote                |
| `commodity`   | Commodity type (e.g., "GCR")                  |
| `margins`     | Dictionary of margins                           |
| `policy`      | Policy details                                  |

### Totals

| Field Name        | Description                                     |
| :---------------- | :---------------------------------------------- |
| `invoice_ccy`     | Invoice currency (e.g., "PGK")                |
| `sell_subtotal`   | Subtotal of sell price                          |
| `sell_tax`        | Total tax on sell price                         |
| `sell_total`      | Final total sell price                          |
| `buy_total_pgk`   | Total buy price in PGK                          |
| `manual_required` | Boolean indicating if manual intervention is needed |
| `reasons`         | List of reasons for manual intervention         |
