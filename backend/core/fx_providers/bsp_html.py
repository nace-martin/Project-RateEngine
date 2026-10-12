from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import Dict, List
import logging

import requests
from bs4 import BeautifulSoup

from . import RateRow

logger = logging.getLogger(__name__)

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
        try:
            resp = requests.get(self.url, headers=headers, timeout=self.timeout)
            resp.raise_for_status()
            return resp.text
        except requests.exceptions.RequestException as e:
            logger.error(f"BSP FX Scraper: Network request failed to {self.url}. Error: {e}")
            raise RuntimeError(f"BSP Network Error: {e}")

    @staticmethod
    def _round4(x: Decimal) -> Decimal:
        return d(x).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)

    @staticmethod
    def _parse_rates(html: str) -> tuple[date, Dict[str, Dict[str, Decimal]]]:
        try:
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
                logger.error("BSP FX Scraper: Required exchange rate table not found in HTML structure.")
                raise AttributeError("Exchange rate table missing")

            section = table.find_parent("section", attrs={"rel": "CBCurrenciesTable"})
            date_node = section.select_one("header h2 time") if section else None
            if date_node is None:
                raise RuntimeError("BSP published FX effective date missing")
            # Orientation guard: every figure below is read as FOREIGN CURRENCY PER 1 KINA. The page
            # states this in its heading ("Exchange rates for Kina"). If the heading changes, the
            # orientation is no longer proven and nothing may be loaded.
            heading = section.select_one("header h2")
            heading_text = heading.get_text(" ", strip=True).lower() if heading else ""
            if "for kina" not in heading_text:
                raise RuntimeError(
                    "BSP rate table orientation not confirmed: heading is not 'Exchange rates for Kina'"
                )
            try:
                effective_date = datetime.strptime(
                    date_node.get_text(strip=True), "%a, %d %B %Y"
                ).date()
            except ValueError as exc:
                raise RuntimeError("BSP published FX effective date invalid") from exc

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
                except (ValueError, TypeError, IndexError, InvalidOperation) as e:
                    logger.warning(f"BSP FX Scraper: Failed to parse row for {code}. Error: {e}")
                    continue
                # Keep zeros; decision to skip is made per-direction in fetch()
                rates[code] = {"TT_BUY": tt_buy, "TT_SELL": tt_sell}
            return effective_date, rates
        except (AttributeError, TypeError) as e:
            logger.error(f"BSP FX Scraper: HTML parsing failed. The site structure may have changed. Error: {e}")
            raise RuntimeError(f"BSP Parse Error: {e}")

    def fetch(self, pairs: List[str]) -> List[RateRow]:
        try:
            html = self._fetch_html()
            effective_date, table = self._parse_rates(html)
        except Exception as e:
            # The management command rejects failed fetches without an old-rate fallback.
            logger.error(f"BSP FX Scraper: Fetch failed. {e}")
            raise

        observed_at = datetime.now(timezone.utc)
        out: List[RateRow] = []
        for pair in pairs:
            if ":" not in pair:
                continue
            base, quote = [p.strip().upper() for p in pair.split(":", 1)]
            
            try:
                if base == "PGK" and quote in table:
                    raw_buy = table[quote]["TT_BUY"]; raw_sell = table[quote]["TT_SELL"]
                    if raw_buy != Decimal("0.0000"):
                        out.append(RateRow(observed_at, base, quote, self._round4(raw_buy), "BUY", "bsp_html", effective_date))
                    if raw_sell != Decimal("0.0000"):
                        out.append(RateRow(observed_at, base, quote, self._round4(raw_sell), "SELL", "bsp_html", effective_date))
                elif quote == "PGK" and base in table:
                    # Invert to PGK per 1 FCY and KEEP the bank side:
                    # BSP "TT Buy"  = bank buys FCY  -> normalized TT BUY  = 1 / TT Buy  (the lower PGK per FCY)
                    # BSP "TT Sell" = bank sells FCY -> normalized TT SELL = 1 / TT Sell (the higher PGK per FCY)
                    # Inverting a rate quoted as FCY per PGK reverses the numeric order but not the side.
                    buy_raw = table[base]["TT_BUY"]
                    sell_raw = table[base]["TT_SELL"]
                    if buy_raw and buy_raw != Decimal("0.0000"):
                        inv_buy = (Decimal(1) / buy_raw).quantize(Decimal("0.00000001"))
                        out.append(RateRow(observed_at, base, quote, inv_buy, "BUY", "bsp_html", effective_date))
                    if sell_raw and sell_raw != Decimal("0.0000"):
                        inv_sell = (Decimal(1) / sell_raw).quantize(Decimal("0.00000001"))
                        out.append(RateRow(observed_at, base, quote, inv_sell, "SELL", "bsp_html", effective_date))
            except Exception as e:
                logger.error(f"BSP FX Scraper: Unexpected error processing pair {base}:{quote}. Error: {e}")
                continue
                
        return out
