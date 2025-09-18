from __future__ import annotations

from decimal import Decimal, ROUND_CEILING

TWOPLACES = Decimal("0.01")
FOURPLACES = Decimal("0.0001")
ZERO = Decimal("0")


def d(val) -> Decimal:
    """Coerce incoming values to Decimal safely."""
    if isinstance(val, Decimal):
        return val
    return Decimal(str(val))


def round_up_nearest_0_05(amount: Decimal) -> Decimal:
    """Round upward to the nearest 0.05 (e.g., 12.01 -> 12.05)."""
    step = Decimal("0.05")
    multiples = (d(amount) / step).to_integral_value(rounding=ROUND_CEILING)
    return (multiples * step).quantize(TWOPLACES)


def round_up_to_next_whole(amount: Decimal) -> Decimal:
    """Round a Decimal amount up to the next whole number."""
    return amount.to_integral_value(rounding=ROUND_CEILING)
