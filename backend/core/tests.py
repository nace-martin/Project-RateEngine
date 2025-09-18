from __future__ import annotations

import sys
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch
from types import SimpleNamespace
from xml.etree import ElementTree as ET

class _SimpleNode:
    def __init__(self, element):
        self._element = element

    def find_all(self, names):
        if isinstance(names, (list, tuple, set)):
            names_set = set(names)
        else:
            names_set = {names}
        results = []
        for child in self._element.iter():
            if child is self._element:
                continue
            if child.tag in names_set:
                results.append(_SimpleNode(child))
        return results

    def get_text(self, strip=False):
        text = ''.join(self._element.itertext())
        return text.strip() if strip else text


class _SimpleSoup(_SimpleNode):
    def __init__(self, html, parser='html.parser'):
        root = ET.fromstring(html)
        super().__init__(root)


for module_name in ("requests", "bs4"):
    if module_name not in sys.modules:
        if module_name == 'bs4':
            sys.modules[module_name] = SimpleNamespace(BeautifulSoup=_SimpleSoup)
        else:
            sys.modules[module_name] = MagicMock()


from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from core.fx import upsert_rate
from core.fx_providers import RateRow
from core.fx_providers.bsp_html import BspHtmlProvider
from core.models import CurrencyRates

MOCK_BSP_HTML = """
<html>
<head><title>BSP Rates</title></head>
<body>
    <div class="some-container">
        <p>Date: 01 Jan 2024</p>
        <div id="fx-rates-table-wrapper">
            <table class="table-striped">
                <thead>
                    <tr>
                        <th>Currency</th>
                        <th>Code</th>
                        <th>TT Buy</th>
                        <th>Notes Buy</th>
                        <th>A/M Buy</th>
                        <th>TT Sell</th>
                        <th>Notes Sell</th>
                    </tr>
                </thead>
                <tbody>
                    <tr>
                        <td>US DOLLAR</td>
                        <td>USD</td>
                        <td>3.4567</td>
                        <td></td>
                        <td></td>
                        <td>3.5432</td>
                        <td></td>
                    </tr>
                    <tr>
                        <td>AUSTRALIAN DOLLAR</td>
                        <td>AUD</td>
                        <td>2.3456</td>
                        <td></td>
                        <td></td>
                        <td>2.4567</td>
                        <td></td>
                    </tr>
                    <tr>
                        <td>ZERO RATE</td>
                        <td>ZRO</td>
                        <td>0</td>
                        <td></td>
                        <td></td>
                        <td>0</td>
                        <td></td>
                    </tr>
                </tbody>
            </table>
        </div>
    </div>
</body>
</html>
""".strip()




class BspHtmlParseTests(SimpleTestCase):
    def test_bsp_parse_and_inversion(self):
        provider = BspHtmlProvider()
        with patch.object(BspHtmlProvider, "_fetch_html", return_value=MOCK_BSP_HTML):
            rows = provider.fetch(["PGK:USD", "USD:PGK"])
        got = {(r.base_ccy, r.quote_ccy, r.rate_type): r.rate for r in rows}
        self.assertEqual(got[("PGK", "USD", "BUY")], Decimal("3.4567"))
        self.assertEqual(got[("PGK", "USD", "SELL")], Decimal("3.5432"))
        self.assertEqual(got[("USD", "PGK", "BUY")], Decimal("0.2893"))  # inverse of 3.4567
        self.assertEqual(got[("USD", "PGK", "SELL")], Decimal("0.2822"))  # inverse of 3.5432

    def test_bsp_zeros_skip_direction(self):
        provider = BspHtmlProvider()
        html = MOCK_BSP_HTML.replace("3.4567", "0")
        with patch.object(BspHtmlProvider, "_fetch_html", return_value=html):
            rows = provider.fetch(["PGK:USD", "USD:PGK"])
        got = {(r.base_ccy, r.quote_ccy, r.rate_type): r.rate for r in rows}
        self.assertNotIn(("PGK", "USD", "BUY"), got)
        self.assertEqual(got[("PGK", "USD", "SELL")], Decimal("3.5432"))
        self.assertEqual(got[("USD", "PGK", "SELL")], Decimal("0.2822"))


class FxFetchCommandTests(TestCase):
    def tearDown(self):
        CurrencyRates.objects.all().delete()

    def test_fetch_fx_command_upserts_rates(self):
        as_of = datetime.now(timezone.utc)
        rows = [
            RateRow(as_of, "USD", "PGK", Decimal("4.1"), "BUY", "TEST"),
            RateRow(as_of, "USD", "PGK", Decimal("4.2"), "SELL", "TEST"),
        ]
        upsert_rate(as_of, "USD", "PGK", Decimal("4.0"), "BUY", "ENV")
        upsert_rate(as_of, "USD", "PGK", Decimal("4.3"), "SELL", "ENV")

        with patch("core.fx_providers.load", return_value=type("Provider", (), {"fetch": lambda self, _: rows})()):
            call_command("fetch_fx", pairs="USD:PGK")

        qs = CurrencyRates.objects.filter(base_ccy="USD", quote_ccy="PGK").values_list("rate_type", "rate")
        data = {rt: rate for rt, rate in qs}
        self.assertEqual(data["BUY"], Decimal("4.1"))
        self.assertEqual(data["SELL"], Decimal("4.2"))
