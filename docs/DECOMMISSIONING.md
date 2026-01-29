# pricing_v3 Decommissioning Roadmap

This document defines the criteria, steps, and verification plan for safely removing the `pricing_v3` Django app from the codebase.

## Current Status

| Milestone | Status | Notes |
|-----------|--------|-------|
| V4 Adapter as sole engine | ✅ COMPLETE | `PricingServiceV4Adapter` is imported as `PricingServiceV3` in all views |
| Engine version tracking | ✅ COMPLETE | `engine_version` field added to `QuoteVersion` and `QuoteTotal` |
| Dispatcher entry point | ✅ COMPLETE | `pricing_v4/dispatcher.py` created with routing map |
| All quotes tagged V4 | ⏳ IN PROGRESS | New quotes tagged; existing quotes default to V4 |
| Shadow mode validation | ⏳ OPTIONAL | Can be enabled via `PRICING_SHADOW_MODE=true` |
| V3 rate cards migrated | 🔲 NOT STARTED | Requires migration CLI or manual review |
| V3 removal from INSTALLED_APPS | 🔲 BLOCKED | Waiting for death criteria |

---

## Death Criteria

**All conditions must be TRUE before removing pricing_v3:**

1. ✅ **V4 Adapter is sole calculation engine**
   - `calculation.py` and `lifecycle.py` use `PricingServiceV4Adapter`
   - No direct V3 resolver calls in production code paths

2. ✅ **Engine version tracking in place**
   - `QuoteVersion.engine_version` and `QuoteTotal.engine_version` fields exist
   - All new quotes are tagged with `engine_version='V4'`

3. 🔲 **No active V3 rate cards**
   - All `pricing_v3.RateCard` records archived or migrated
   - Verification: `RateCard.objects.filter(is_active=True).count() == 0`

4. 🔲 **30-day shadow mode validation**
   - Enable `PRICING_SHADOW_MODE=true`
   - Monitor logs for variance between V4 and V3 calculations
   - Variance threshold: < 1% deviation acceptable

5. 🔲 **V3 API endpoints deprecated**
   - `/api/v3/quotes/<id>/compute/` (debug endpoint) removed or returns 410
   - All clients migrated to V3-compatible V4 endpoints

---

## Feature Parity Checklist

| Feature | V3 Support | V4 Support | Notes |
|---------|:----------:|:----------:|-------|
| Import A2A, A2D, D2A, D2D | ✅ | ✅ | ImportPricingEngine |
| Export A2A, D2A, D2D | ✅ | ✅ | ExportPricingEngine |
| Domestic A2A, D2D | ✅ | ✅ | DomesticPricingEngine |
| FCY Pricing (Prepaid/Collect) | ✅ | ✅ | Adapter handles currency |
| Customer Discounts | ✅ | ✅ | `CustomerDiscount` model |
| SPOT Pricing Overlay | ✅ | ✅ | Adapter + SPE integration |
| GST Calculation | ✅ | ✅ | TaxHelper service |
| SEA Freight | ❌ | ❌ | Not in scope |

---

## Migration Steps

### Step 1: Archive V3 Rate Cards
```bash
# Export V3 rate cards for reference
python manage.py dumpdata pricing_v3.RateCard pricing_v3.RateLine --indent 2 > v3_rate_cards_backup.json

# Deactivate all V3 rate cards (if is_active field exists)
python manage.py shell -c "from pricing_v3.models import RateCard; RateCard.objects.update(is_active=False)"
```

### Step 2: Enable Shadow Mode (30 days)
```bash
# In .env
PRICING_SHADOW_MODE=true
```

Monitor: Check application logs for `PricingDispatcher` shadow comparison output.

### Step 3: Remove V3 from INSTALLED_APPS
```python
# rate_engine/settings.py
INSTALLED_APPS = [
    ...
    # 'pricing_v3',  # REMOVED - Decommissioned YYYY-MM-DD
    'pricing_v4',
]
```

### Step 4: Delete pricing_v3 Directory
```bash
rm -rf backend/pricing_v3
```

### Step 5: Remove V3 Migrations Reference
Run a fake migration to clean up Django's migration history:
```bash
python manage.py migrate pricing_v3 zero --fake
```

---

## Rollback Plan

If issues arise after V3 removal:

1. Restore `pricing_v3` from git history
2. Re-add to `INSTALLED_APPS`
3. Run `python manage.py migrate` to verify state
4. Toggle dispatcher back to shadow mode for investigation

---

## Sign-Off

| Role | Name | Date | Approved |
|------|------|------|:--------:|
| Lead Developer | | | 🔲 |
| Commercial Manager | | | 🔲 |
| QA Lead | | | 🔲 |

---

*Last Updated: 2026-01-29*
