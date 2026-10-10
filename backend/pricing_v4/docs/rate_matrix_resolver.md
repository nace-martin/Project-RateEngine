# Rate Matrix Resolver and Shadow Comparison (Stage 1 and Stage 2)

Status: resolver and Stage-1 shadow implemented in Pilot Gate B3J; Stage-2 commercial shadow implemented in Pilot Gate B3K (section 3). **Read only and not live.** No quote, engine, adapter, or
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

## 3. Stage-2 commercial shadow: `shadow_price_rate_matrix` (Pilot Gate B3K)

```bash
python manage.py shadow_price_rate_matrix [--lane BNE-POM ...] [--date YYYY-MM-DD] \n    [--weights 30,45,100,...] [--terms COLLECT,PREPAID] [--scopes A2D,D2D] \n    [--explained stage1-registry.json] [--max-fx-age-days N] [--format text|json] [--fail-on-unexplained]
```

For each scenario (lane, chargeable weight, payment term, service scope) it prices the import **twice with
the production `ImportPricingEngine`**: once from legacy rate rows, and once with
`MatrixShadowImportEngine`, a subclass that redirects only the rate lookups (`_get_cogs`, `_get_local_cogs`,
`_get_sell_rate`, `_get_destination_sell_rate`) and the surcharge-basis seed (`_calculate_cogs_amount`) to the
resolver. Tier selection, minimum and maximum charges, percentage surcharges, FX, CAF, margin, GST
classification, rounding and totals are the unmodified production code, so no commercial formula is
duplicated. A test pins the override set.

Then it compares line by line (sell amount, GST, sell including GST, native cost) and total by total.

### Policy and FX are legacy observed values

CAF, margin and the margin method are read from `CommercialTermsPolicy`; FX from `FxMarketRate`. They are
reported with provenance as **LEGACY OBSERVED POLICY. NOT APPROVED FOR CUTOVER.** Nothing is invented,
seeded, or approved. GST rates come from `quotes.tax_policy` exactly as production applies them.

### Fails closed (`BLOCKED`)

| Condition | Code |
|---|---|
| No active policy for the date | `POLICY_MISSING` |
| More than one active policy covers the date (production would silently take the newest) | `POLICY_AMBIGUOUS` |
| Policy lacks CAF or margin | `POLICY_INCOMPLETE` |
| FX rate missing for a needed pair | `MissingFxMarketRateError` |
| Competing FX sources on the resolved date | `AmbiguousFxSourceError` |
| FX older than an operator-supplied `--max-fx-age-days` (no default is assumed) | `FX_STALE` |
| Resolver returns `AMBIGUOUS` or `INVALID_CONTEXT` | `RESOLVER_*` |
| Matrix percentage basis differs from the legacy basis | `PERCENTAGE_BASIS_MISMATCH` |
| Matrix mirror GST treatment differs from the legacy ProductCode | `GST_TREATMENT_MISMATCH` |
| BUY sheets for the origin do not name exactly one supplier | `SUPPLIER_NOT_SINGLE` |

A scenario that needs no FX (for example A2D COLLECT in PGK) is still priced when FX is absent.

### Classes

`MATCH`, `EXPECTED_DIFFERENCE`, `UNEXPLAINED_DIFFERENCE`, `BLOCKED`, `NOT_COMPARABLE`. A line difference is
`EXPECTED_DIFFERENCE` only when the Stage-1 comparison for that charge has native differences and **all**
of them are explained in the Stage-1 registry; if the native facts match but the amount differs, the
divergence is in the downstream calculation and is `UNEXPLAINED_DIFFERENCE`. Native cost on destination
charges is `NOT_COMPARABLE` because the Rate Matrix holds no destination BUY tariff. Every record carries
ProductCode, legacy amount, shadow amount, currency, calculation stage, policy and FX provenance, and
reason.

## 4. Safety

- None of the modules is imported by `quotes`, `pricing_v4/engine`, the adapter, the dispatcher, or `core`.
- All only issue `SELECT` statements; tests assert this and that no FX table is read.
- No tariff, master data, or legacy row is changed.
