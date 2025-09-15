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


@dataclass
class TTRate:
    base: str
    quote: str
    tt_buy: Decimal
    tt_sell: Decimal
    as_of: datetime


class BspHtmlProvider:
    """
    Scrapes BSP public FX page. BSP publishes foreign per 1 PGK for TT BUY/SELL.
    For requested pairs:
      - PGK:FCY -> BUY = TT_BUY, SELL = TT_SELL (no inversion)
      - FCY:PGK -> BUY = 1/TT_BUY, SELL = 1/TT_SELL (invert)
    """

    def __init__(self, url: str | None = None, as_of: datetime | None = None):
        self.url = url or os.environ.get(
            "BSP_FX_URL",
            "https://www.bsp.com.pg/Personal-Banking/Foreign-Exchange/Exchange-Rates/",
        )
        self.as_of = as_of or now()

    def _fetch_html(self) -> str:
        import urllib.request
        with urllib.request.urlopen(self.url, timeout=15) as resp:  # nosec B310
            return resp.read().decode("utf-8", errors="ignore")

    @staticmethod
    def _parse_table(html: str) -> Dict[str, Tuple[Decimal, Decimal]]:
        """
        Return mapping currency_code -> (tt_buy, tt_sell). Skips 0.0000.
        Tries to be liberal with HTML using regex.
        """
        import re

        # Normalize whitespace
        text = re.sub(r"\s+", " ", html)

        # Heuristic: find rows that contain a 3-letter code and two decimal numbers
        row_re = re.compile(
            r"(?i)>([A-Z]{3})<[^>]*>.*?TT\s*Buy[^<]*<|>([A-Z]{3})<",
        )

        # Simpler approach: find sequences like CODE ... (\d+\.\d{1,6}) ... (\d+\.\d{1,6}) in a row
        # We'll scan by each occurrence of a currency code and then look ahead for two numbers.
        code_re = re.compile(r"(?i)>([A-Z]{3})<")
        num_re = re.compile(r"(\d+\.\d{1,6})")

        table: Dict[str, Tuple[Decimal, Decimal]] = {}
        for m in code_re.finditer(text):
            code = m.group(1).upper()
            # Skip PGK as it's the base
            if code == "PGK":
                continue
            tail = text[m.end(): m.end() + 400]  # look ahead
            nums = num_re.findall(tail)
            if len(nums) >= 2:
                buy_v = d(nums[0])
                sell_v = d(nums[1])
                if buy_v == Decimal("0.0000") or sell_v == Decimal("0.0000"):
                    continue
                table[code] = (buy_v, sell_v)
        return table

    def get_tt_rates(self, base: str, quote: str) -> TTRate:
        html = self._fetch_html()
        table = self._parse_table(html)
        base_u = base.upper(); quote_u = quote.upper()

        if base_u == "PGK" and quote_u in table:
            buy, sell = table[quote_u]
            return TTRate(base=base_u, quote=quote_u, tt_buy=buy, tt_sell=sell, as_of=self.as_of)
        if quote_u == "PGK" and base_u in table:
            buy, sell = table[base_u]
            # Invert for FCY:PGK pair
            inv_buy = (Decimal(1) / buy) if buy else Decimal(0)
            inv_sell = (Decimal(1) / sell) if sell else Decimal(0)
            return TTRate(base=base_u, quote=quote_u, tt_buy=inv_buy, tt_sell=inv_sell, as_of=self.as_of)

        raise ValueError(f"Pair not supported by BSP table: {base_u}:{quote_u}")


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


def upsert_rate(
    as_of: datetime, base: str, quote: str, rate: Decimal, rate_type: str, source: str
) -> None:
    CurrencyRates.objects.update_or_create(
        as_of_ts=as_of,
        base_ccy=base.upper(),
        quote_ccy=quote.upper(),
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
        # If provider exposes TT directly (e.g., BSP), use it
        if hasattr(provider, "get_tt_rates"):
            tr = getattr(provider, "get_tt_rates")(base, quote)
            # Skip if TT values are zero
            if tr.tt_buy == Decimal("0.0000") or tr.tt_sell == Decimal("0.0000"):
                continue
            upsert_rate(tr.as_of, tr.base, tr.quote, tr.tt_buy, "BUY", source_label)
            upsert_rate(tr.as_of, tr.base, tr.quote, tr.tt_sell, "SELL", source_label)
            results.append({
                "pair": f"{tr.base}->{tr.quote}",
                "as_of": tr.as_of.isoformat(),
                "mid": None,
                "buy": str(tr.tt_buy),
                "sell": str(tr.tt_sell),
                "source": source_label,
            })
            continue

        # Fallback: mid + spread/CAF
        mr = provider.get_mid_rate(base, quote)
        buy, sell = compute_tt_buy_sell(mr.rate, spread_bps, caf_pct)
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
