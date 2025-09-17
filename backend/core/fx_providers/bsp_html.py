from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List

import requests
from bs4 import BeautifulSoup

from . import RateRow


def d(val) -> Decimal:
    if isinstance(val, Decimal):
        return val
    return Decimal(str(val))


class BspHtmlProvider:
    def __init__(
        self,
        url: str = "https://www.bsp.com.pg/international-services/foreign-exchange/exchange-rates/",
        timeout: int = 15,
    ) -> None:
        self.url = url
        self.timeout = timeout

    def _fetch_html(self) -> str:
        headers = {
            "User-Agent": "RateEngineFXBot/1.0 (+https://example.com)",
            "Accept": "text/html,application/xhtml+xml",
        }
        resp = requests.get(self.url, headers=headers, timeout=self.timeout)
        resp.raise_for_status()
        return resp.text

    @staticmethod
    def _round4(x: Decimal) -> Decimal:
        return d(x).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)

    @staticmethod
    def _parse_rates(html: str) -> Dict[str, Dict[str, Decimal]]:
        soup = BeautifulSoup(html, "html.parser")
        table = None
        for t in soup.find_all("table"):
            # Find header cells that look like TT Buy/Sell
            headers = [th.get_text(strip=True) for th in t.find_all("th")]
            normalized = [h.lower() for h in headers]
            if any("tt buy" in h for h in normalized) and any("tt sell" in h for h in normalized):
                table = t
                break
        if table is None:
            raise RuntimeError("BSP FX: table not found")

        rates: Dict[str, Dict[str, Decimal]] = {}
        # Expect rows with columns: Currency | Code | TT Buy | Notes Buy | A/M Buy | TT Sell | Notes Sell
        for tr in table.find_all("tr"):
            tds = tr.find_all(["td", "th"])
            if len(tds) < 6:
                continue
            # Attempt to read code and tt values
            code = tds[1].get_text(strip=True).upper()
            # Some tables may put code in first column; fallback if secondary empty or not 3 letters
            if not (len(code) == 3 and code.isalpha()):
                code_primary = tds[0].get_text(strip=True).upper()
                if len(code_primary) == 3 and code_primary.isalpha():
                    code = code_primary
            if len(code) != 3 or not code.isalpha() or code == "CODE":
                continue
            try:
                tt_buy_txt = tds[2].get_text(strip=True).replace(",", "")
                tt_sell_txt = tds[5].get_text(strip=True).replace(",", "")
                tt_buy = d(tt_buy_txt)
                tt_sell = d(tt_sell_txt)
            except Exception:
                continue
            # Keep zeros; decision to skip is made per-direction in fetch()
            rates[code] = {"TT_BUY": tt_buy, "TT_SELL": tt_sell}
        return rates

    def fetch(self, pairs: List[str]) -> List[RateRow]:
        html = self._fetch_html()
        table = self._parse_rates(html)
        as_of = datetime.now(timezone.utc)
        out: List[RateRow] = []
        for pair in pairs:
            if ":" not in pair:
                continue
            base, quote = [p.strip().upper() for p in pair.split(":", 1)]
            if base == "PGK" and quote in table:
                raw_buy = table[quote]["TT_BUY"]; raw_sell = table[quote]["TT_SELL"]
                if raw_buy != Decimal("0.0000"):
                    out.append(RateRow(as_of, base, quote, self._round4(raw_buy), "BUY", "bsp_html"))
                if raw_sell != Decimal("0.0000"):
                    out.append(RateRow(as_of, base, quote, self._round4(raw_sell), "SELL", "bsp_html"))
            elif quote == "PGK" and base in table:
                # Invert
                buy_raw = table[base]["TT_BUY"]
                sell_raw = table[base]["TT_SELL"]
                if buy_raw and buy_raw != Decimal("0.0000"):
                    inv_buy = self._round4(Decimal(1) / buy_raw)
                    out.append(RateRow(as_of, base, quote, inv_buy, "BUY", "bsp_html"))
                if sell_raw and sell_raw != Decimal("0.0000"):
                    inv_sell = self._round4(Decimal(1) / sell_raw)
                    out.append(RateRow(as_of, base, quote, inv_sell, "SELL", "bsp_html"))
        return out
