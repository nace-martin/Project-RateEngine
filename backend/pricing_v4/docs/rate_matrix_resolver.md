# Rate Matrix Resolver and Stage-1 Shadow Comparison

Status: implemented in Pilot Gate B3J. **Read only and not live.** No quote, engine, adapter, or
dispatcher imports either module (a test enforces this). Legacy pricing remains authoritative and
route automation stays disabled. Nothing here writes a row, converts currency, or computes CAF,
margin, GST, or a quote total.

Related: `rate_matrix_manifest.md` (validation contract), `rate_matrix_loader.md` (how tariffs get
stored), spec `docs/architecture/clean-database-architecture-v2.1.md` §3.5.1.

## 1. Resolver: `pricing_v4/services/rate_matrix_resolver.py`

```python
from pricing_v4.services.rate_matrix_resolver import ResolutionContext, resolve

result = resolve(ResolutionContext(
    rate_type="BUY", direction="IMPORT", effective_date=date(2026, 10, 10),
    product_code="IMP-FRT-AIR", origin_iata="BNE", destination_iata="POM",
    supplier_id=<PartyMaster id>, chargeable_weight=Decimal("120"),
))
result.outcome      # EXACT_MATCH | NO_MATCH | AMBIGUOUS | INVALID_CONTEXT
result.tariff       # native facts and provenance, only for EXACT_MATCH
result.candidates   # the competing lines, for AMBIGUOUS
result.reasons      # why
```

### Context

Every field is stated by the caller; nothing is defaulted from elsewhere.

| Field | Rule |
|---|---|
| `rate_type` | `BUY` or `SELL` |
| `transport_mode` | `AIR` (the Pilot) |
| `direction` | `IMPORT`, `EXPORT`, or `DOMESTIC` |
| `effective_date` | required; validity is inclusive at both ends |
| `product_code` | a `CommercialProductCode.code` |
| `origin_iata`, `destination_iata` | optional; resolved through the IATA identifier chain |
| `payment_term` | `PREPAID`, `COLLECT`, or blank |
| `quote_currency` | required for SELL; the requested customer currency |
| `supplier_id` | required for BUY; forbidden for SELL |
| `service_level`, `commodity_category`, `equipment_type` | blank by default |
| `chargeable_weight` | required to select a tier |
| `allow_line_without_weight` | structural comparison only: return a tiered line with no tier selected |

### Rules

- Only active sheets whose validity window contains `effective_date`.
- A blank applicability value means ANY. There is **no specific-over-general precedence**: if more
  than one line could match, the outcome is `AMBIGUOUS` and nothing is chosen.
- BUY: the supplier must match. BUY currency never filters, so two costs for one charge that differ only
  in currency are `AMBIGUOUS`.
- SELL: the sheet currency must equal `quote_currency`. There is no FX and no fallback to another
  currency or route.
- Direction is never inferred in reverse. A BNE to POM IMPORT tariff does not answer POM to BNE.
- Tiers: lower bound inclusive, upper bound exclusive, whole-weight pricing, a weight no tier covers is
  `NO_MATCH`.
- A legitimate zero rate is an `EXACT_MATCH`, not a missing rate.
- `INVALID_CONTEXT` is returned for an unstated, malformed, or unresolvable context (unknown airport,
  BUY without a supplier, SELL without a currency, tiered rate without a weight, negative weight).

### Facts returned

Sheet id, name, version and `source_reference`; rate type; native currency; validity; supplier;
product code; basis; unit rate, additive flat amount, minimum, maximum; percentage rate and its basis
product code; the tier table and the selected tier; and the line's applicability (direction, origin,
destination, payment term, service level, commodity, equipment). No amount is calculated.

## 2. Stage-1 shadow comparison: `shadow_compare_rate_matrix`

```bash
python manage.py shadow_compare_rate_matrix [--lane BNE-POM ...] [--date YYYY-MM-DD] \
    [--weights 30,45,100,...] [--explained registry.json] [--legacy-agent-code CODE] \
    [--format text|json] [--show-matches] [--fail-on-unexplained]
```

Compares **native facts only** between the Rate Matrix and legacy rows read through the production
selectors (`select_import_cogs_rate`, `select_local_sell_rate`): charge presence, currency, basis, rate,
minimum, maximum, additive amount, percentage and its basis, tier table, selected rate at stated
weights, applicability, and validity. It runs inside a read-only, rolled-back transaction.

- **BUY** facts come from `ImportCOGS` for each lane (default BNE-POM and SYD-POM).
- **Destination SELL** facts come from `LocalSellRate` at the destination, for IMPORT COLLECT and
  IMPORT PREPAID, in the quote currency from `quotes.currency_rules.determine_quote_currency`.
- Legacy import SELL for origin and freight charges is cost-plus (no rows), so only BUY facts exist
  there.
- Legacy weight breaks are compared with the rule used by live pricing: the highest break at or below the
  weight applies, and below the first break the lowest break's rate applies. A test locks this to
  `core.charge_rules.evaluate_tiered_break_rule`.

### Classifications

| Class | Meaning |
|---|---|
| `MATCH` | identical native facts |
| `EXPECTED_DIFFERENCE` | differs, and an explained-differences registry entry names this exact difference |
| `UNEXPLAINED_DIFFERENCE` | differs with no registry entry; never normalised away |
| `LEGACY_ONLY` | legacy prices the charge and the Rate Matrix has no tariff |
| `RATE_MATRIX_ONLY` | the Rate Matrix has a tariff and legacy has no row |
| `NOT_COMPARABLE` | ambiguous or unresolved on either side, or the basis differs so rate values cannot be compared |

Currency, minimum, and maximum are still compared when the basis differs; unit rate, additive amount,
percentage, and tiers become `NOT_COMPARABLE`.

### Explained-differences registry

An optional strict JSON file: `{"registry_version": 1, "entries": [...]}` where each entry has exactly
`lane`, `side`, `product_code`, `aspect`, `legacy`, `matrix`, `reason`, `evidence`, all non-blank. An
entry applies only when the lane (or `*`), side, charge, aspect **and both rendered values** match, so a
change to either side stops it applying. An entry that matches nothing is reported as stale.
`EXPECTED_DIFFERENCE` records *why a difference exists*; it does not approve it. The registry is
operator-supplied and private; real tariff values are not committed to the repository.

## 3. Safety

- Neither module is imported by `quotes`, `pricing_v4/engine`, the adapter, the dispatcher, or `core`.
- Both only issue `SELECT` statements; tests assert this and that no FX table is read.
- No tariff, master data, or legacy row is changed.
