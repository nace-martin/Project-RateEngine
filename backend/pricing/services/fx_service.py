from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from django.utils.timezone import now

from ..dataclasses import Money
from core.models import CurrencyRates as CurrencyRate
from .utils import TWOPLACES, d


class FxConverter:
    def __init__(self, caf_buy_pct: Decimal = Decimal("0.05"), caf_sell_pct: Decimal = Decimal("0.10")):
        self.caf_buy_pct = caf_buy_pct
        self.caf_sell_pct = caf_sell_pct

    def _fetch_rate(self, base_ccy: str, quote_ccy: str, rate_type: str, at: datetime) -> Optional[Decimal]:
        row = (
            CurrencyRate.objects
            .filter(
                base_ccy=base_ccy,
                quote_ccy=quote_ccy,
                rate_type=rate_type,
                as_of_ts__lte=at,
            )
            .order_by("-as_of_ts")
            .first()
        )
        return d(row.rate) if row else None

    def _rate_foreign_to_pgk(self, foreign_ccy: str, at: datetime) -> Decimal:
        """
        Calculates the conversion rate from a foreign currency TO PGK.

        This is a "BUY" transaction from the company's perspective (buying foreign
        currency with PGK). The `caf_buy_pct` is applied to the bank's Telegraphic
        Transfer (TT) BUY rate to determine the final customer rate.
        """
        # Prefer PGK->foreign TT BUY (quoted as foreign per PGK)
        raw = self._fetch_rate('PGK', foreign_ccy, 'BUY', at)
        if raw is not None:
            adjusted = raw * (Decimal('1.0') - self.caf_buy_pct)
            if adjusted == 0:
                raise ValueError("Adjusted BUY rate results in zero; cannot convert.")
            return Decimal('1.0') / adjusted

        raw = self._fetch_rate(foreign_ccy, 'PGK', 'BUY', at)
        if raw is None:
            raise ValueError(f"No TT BUY rate found for {foreign_ccy}->PGK")
        adjusted = raw / (Decimal('1.0') - self.caf_buy_pct)
        if adjusted == 0:
            raise ValueError("Adjusted BUY rate results in zero; cannot convert.")
        return adjusted

    def _rate_pgk_to_foreign(self, foreign_ccy: str, at: datetime) -> Decimal:
        """
        Calculates the conversion rate FROM PGK to a foreign currency.

        This is a "SELL" transaction (selling foreign currency for PGK), so the
        `caf_sell_pct` is applied to the bank's TT SELL rate.
        """
        raw = self._fetch_rate('PGK', foreign_ccy, 'SELL', at)
        if raw is not None:
            adjusted = raw * (Decimal('1.0') + self.caf_sell_pct)
            if adjusted == 0:
                raise ValueError("Adjusted SELL rate results in zero; cannot convert.")
            return Decimal('1.0') / adjusted

        raw = self._fetch_rate(foreign_ccy, 'PGK', 'SELL', at)
        if raw is None:
            raise ValueError(f"No TT SELL rate found for PGK->{foreign_ccy}")
        adjusted = raw * (Decimal('1.0') + self.caf_sell_pct)
        if adjusted == 0:
            raise ValueError("Adjusted SELL rate results in zero; cannot convert.")
        return adjusted

    def rate(self, base_ccy: str, quote_ccy: str, at: Optional[datetime] = None) -> Decimal:
        at = at or now()

        base_ccy = base_ccy.upper()
        quote_ccy = quote_ccy.upper()

        if base_ccy == quote_ccy:
            return Decimal('1.0')

        if quote_ccy == 'PGK':
            return self._rate_foreign_to_pgk(base_ccy, at)

        if base_ccy == 'PGK':
            return self._rate_pgk_to_foreign(quote_ccy, at)

        to_pgk = self._rate_foreign_to_pgk(base_ccy, at)
        from_pgk = self._rate_pgk_to_foreign(quote_ccy, at)
        return to_pgk * from_pgk

    def convert(self, money: Money, to_ccy: str) -> Money:
        if money.currency == to_ccy:
            return money
        fx_rate = self.rate(money.currency, to_ccy)
        return Money((money.amount * fx_rate).quantize(TWOPLACES), to_ccy)

