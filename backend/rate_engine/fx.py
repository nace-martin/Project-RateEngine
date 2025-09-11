from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
import json
import logging
import os
from typing import Dict, Iterable, List, Tuple

from django.utils.timezone import now

from .models import CurrencyRates

logger = logging.getLogger(__name__)


def d(val) -> Decimal:
    if isinstance(val, Decimal):
        return val
    return Decimal(str(val))


@dataclass
class MidRate:
    base: str
    quote: str
    rate: Decimal
    as_of: datetime


class FXProvider:
    def get_mid_rate(self, base: str, quote: str) -> MidRate:
        raise NotImplementedError


class EnvProvider(FXProvider):
    """
    Reads mid rates from FX_MID_RATES env var as JSON.
    Example:
      FX_MID_RATES='{"USD": {"PGK": 3.75, "AUD": 1.50}, "PGK": {"USD": 0.2667}}'
    """

    def __init__(self, as_of: datetime | None = None):
        self.as_of = as_of or now()
        blob = os.environ.get("FX_MID_RATES", "{}")
        try:
            self.table: Dict[str, Dict[str, float]] = json.loads(blob)
        except Exception:
            logger.exception("Invalid FX_MID_RATES JSON; falling back to empty table")
            self.table = {}

    def get_mid_rate(self, base: str, quote: str) -> MidRate:
        base = base.upper(); quote = quote.upper()
        r = None
        if self.table.get(base, {}).get(quote) is not None:
            r = d(self.table[base][quote])
        elif self.table.get(quote, {}).get(base) is not None:
            # Use reciprocal if only reverse is provided
            val = d(self.table[quote][base])
            if val:
                r = (Decimal(1) / val)
        if r is None:
            raise ValueError(f"No mid rate configured in FX_MID_RATES for {base}->{quote}")
        return MidRate(base=base, quote=quote, rate=r, as_of=self.as_of)


def compute_tt_buy_sell(mid: Decimal, spread_bps: int, caf_pct: Decimal) -> Tuple[Decimal, Decimal]:
    """
    Returns (buy_rate, sell_rate) as Decimals.
    - BUY: FCY -> PGK (use mid reduced by spread + caf)
    - SELL: PGK -> FCY (use mid increased by spread + caf)
    """
    spread = d(spread_bps) / Decimal(10_000)
    adj = spread + d(caf_pct)
    buy = d(mid) * (Decimal(1) - adj)
    sell = d(mid) * (Decimal(1) + adj)
    return buy, sell


def upsert_rate(as_of: datetime, base: str, quote: str, rate: Decimal, rate_type: str, source: str) -> None:
    CurrencyRates.objects.update_or_create(
        as_of_ts=as_of,
        base_ccy=base,
        quote_ccy=quote,
        rate_type=rate_type,
        defaults={"rate": d(rate), "source": source},
    )


def refresh_fx(
    pairs: Iterable[Tuple[str, str]],
    provider: FXProvider,
    *,
    spread_bps: int = 100,
    caf_pct: Decimal = Decimal("0.065"),
    source_label: str = "ENV",
) -> List[Dict]:
    """
    Fetch mid rates for pairs and persist BUY/SELL rows.
    Returns a summary list.
    """
    results: List[Dict] = []
    for base, quote in pairs:
        mr = provider.get_mid_rate(base, quote)
        buy, sell = compute_tt_buy_sell(mr.rate, spread_bps, caf_pct)
        # Persist both types for the same base->quote
        upsert_rate(mr.as_of, mr.base, mr.quote, buy, "BUY", source_label)
        upsert_rate(mr.as_of, mr.base, mr.quote, sell, "SELL", source_label)
        results.append({
            "pair": f"{mr.base}->{mr.quote}",
            "as_of": mr.as_of.isoformat(),
            "mid": str(mr.rate),
            "buy": str(buy),
            "sell": str(sell),
            "source": source_label,
        })
    return results

