# V4 Pricing Test Infrastructure

## Overview
As of Phase 4E, the V4 pricing test ecosystem has been modernized to align with production integrity guarantees (`PricingDomainService`, overlap prevention, and domain validation).

## Validated Factories
Located in `backend/pricing_v4/tests/validated_factories.py`, these helpers should be the **default** choice for creating pricing data in tests.

### Key Helpers:
- `create_validated_local_sell(**kwargs)`
- `create_validated_export_sell(**kwargs)`
- `create_validated_import_cogs(**kwargs)`
- `get_or_create_test_product(id, code, domain, category)`

### Why use them?
1. **Commercial Integrity**: They route through `PricingDomainService.save_rate()`, ensuring `full_clean()` is called.
2. **Overlap Prevention**: They will raise `ValidationError` if you attempt to create overlapping active rows for the same commercial identity.
3. **Consistency**: They ensure `ProductCode` metadata matches the table domain.

## When to use raw ORM (`objects.create`)
Raw ORM creation bypasses all commercial validation. It should only be used for:
1. **Integrity Testing**: Tests that specifically verify that the database allows/disallows certain states (e.g., testing selector tie-breaks on legacy corrupted data).
2. **Low-level Infrastructure**: Testing model fields or base class behavior without triggering commercial logic.

**Always document why raw creation is used if you bypass validation.**

## Handling Overlaps in Tests
If a test requires overlapping rows (e.g., to test selector tie-breaking):
```python
# Bypass service to force an overlap
LocalSellRate.objects.create(
    product_code=pc,
    valid_from=date(2025, 1, 1),
    valid_until=date(2025, 12, 31),
    # ...
)
LocalSellRate.objects.create(
    product_code=pc,
    valid_from=date(2025, 6, 1), # Overlaps!
    valid_until=date(2026, 6, 1),
    # ...
)
```

## Testing Rollovers
Sequential boundaries are encouraged:
```python
# Valid continuity (no gap, no overlap)
create_validated_export_sell(valid_from="2025-01-01", valid_until="2025-12-31", ...)
create_validated_export_sell(valid_from="2026-01-01", valid_until="2026-12-31", ...)
```
