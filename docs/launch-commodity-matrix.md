# Launch Commodity Matrix

This is the conservative launch matrix for commodity-aware routing.

Principle:
- use `AUTO` only where a real commercial product and seeded coverage already exist
- use `REQUIRES_MANUAL` where the product exists but the charge still depends on operator confirmation
- use `REQUIRES_SPOT` where the commodity remains partner/airline driven at launch

## Export

| Commodity | Scope | Product code | Trigger mode | Notes |
| --- | --- | --- | --- | --- |
| `DG` | `D2A`, `D2D` | `EXP-DG` | `AUTO` | Product/rate path already exists, but standard DG quote compute is still blocked until DG support is enabled. |
| `AVI` | `D2A`, `D2D` | `EXP-LPC` | `REQUIRES_MANUAL` | Live animal pricing stays manual at launch. |
| `HVC` | `D2A`, `D2D` | `EXP-VCH` | `REQUIRES_MANUAL` | Valuable cargo handling stays manual at launch. |
| `PER` | `D2A`, `D2D` | `EXP-PER-SPECIAL` | `REQUIRES_SPOT` | Perishable export charges remain airline/handling driven. |

## Import

| Commodity | Scope | Product code | Trigger mode | Notes |
| --- | --- | --- | --- | --- |
| `DG` | `A2D`, `D2D` | `IMP-DG-SPECIAL` | `AUTO` | Standard quote stays enabled when destination-local DG tariffs exist in `LocalSellRate`; otherwise commodity coverage falls back to missing-rates/SPOT. |
| `AVI` | `A2D`, `D2D` | `IMP-AVI-SPECIAL` | `AUTO` | Standard quote stays enabled when destination-local live-animal tariffs exist in `LocalSellRate`; otherwise commodity coverage falls back to missing-rates/SPOT. |
| `HVC` | `A2D`, `D2D` | `IMP-HVC-SPECIAL` | `AUTO` | Standard quote stays enabled when destination-local high-value tariffs exist in `LocalSellRate`; otherwise commodity coverage falls back to missing-rates/SPOT. |
| `PER` | `A2D`, `D2D` | `IMP-PER-SPECIAL` | `REQUIRES_SPOT` | Perishable import pricing remains partner-driven. |

## Domestic

| Commodity | Scope | Product code | Trigger mode | Notes |
| --- | --- | --- | --- | --- |
| `AVI` | all scopes | `DOM-LIVE-ANIMAL` | `REQUIRES_MANUAL` | Manual until domestic special-cargo pricing is fully modeled. |
| `HVC` | all scopes | `DOM-VALUABLE` | `REQUIRES_MANUAL` | Manual until domestic special-cargo pricing is fully modeled. |
| `DG` | all scopes | `DOM-DG-SPECIAL` | `REQUIRES_SPOT` | Domestic DG remains SPOT-only at launch. |
| `PER` | all scopes | `DOM-PER-SPECIAL` | `REQUIRES_SPOT` | Domestic perishables remain SPOT-only at launch. |

## Command

Run from `backend/`:

```bash
python manage.py seed_launch_commodity_rules --dry-run
python manage.py seed_launch_commodity_rules --effective-from 2026-01-01
```

The command is idempotent and will:
- create missing routing-marker `ProductCode` rows where needed
- upsert the launch `CommodityChargeRule` matrix
- leave existing rules intact unless they match the same lookup and need updating
