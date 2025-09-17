from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from django.utils.timezone import now

from ..dataclasses import Money
from core.models import CurrencyRates as CurrencyRate
from .utils import TWOPLACES, d


class FxConverter:
    def __init__(self, caf_on_fx: bool = True, caf_pct: Decimal = Decimal("0.00")):
        self.caf_on_fx = caf_on_fx
        self.caf_pct = caf_pct

    def rate(self, base_ccy: str, quote_ccy: str, at: Optional[datetime] = None) -> Decimal:
        """Fetch the latest FX rate base->quote using TT Buy/Sell direction logic."""
        at = at or now()

        if quote_ccy == "PGK":
            rate_type_to_fetch = "BUY"
            is_to_pgk = True
        else:
            rate_type_to_fetch = "SELL"
            is_to_pgk = False

        row = (
            CurrencyRate.objects
            .filter(
                base_ccy=base_ccy,
                quote_ccy=quote_ccy,
                as_of_ts__lte=at,
                rate_type=rate_type_to_fetch,
            )
            .order_by("-as_of_ts")
            .first()
        )
        if not row:
            raise ValueError(f"No FX rate {base_ccy}->{quote_ccy} (Type: {rate_type_to_fetch}) available")

        rate = d(row.rate)

        if not self.caf_on_fx:
            return rate

        if is_to_pgk:
            return rate * (Decimal("1.0") - self.caf_pct)
        return rate * (Decimal("1.0") + self.caf_pct)

    def convert(self, money: Money, to_ccy: str) -> Money:
        if money.currency == to_ccy:
            return money
        fx_rate = self.rate(money.currency, to_ccy)
        return Money((money.amount * fx_rate).quantize(TWOPLACES), to_ccy)

