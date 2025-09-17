from __future__ import annotations

import sys
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

for module_name in ("requests", "bs4"):
    if module_name not in sys.modules:
        mock_module = MagicMock()
        if module_name == "bs4":
            mock_module.BeautifulSoup = MagicMock()
        sys.modules[module_name] = mock_module


from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from core.fx import upsert_rate
from core.fx_providers import RateRow
from core.fx_providers.bsp_html import BspHtmlProvider
from core.models import CurrencyRates

USD_TABLE_HTML = """
<html><body>
<table>
  <thead>
    <tr><th>Currency</th><th>Code</th><th>TT Buy</th><th>Notes Buy</th><th>A/M Buy</th><th>TT Sell</th><th>Notes Sell</th></tr>
  </thead>
  <tbody>
    <tr><td>US Dollar</td><td>USD</td><td>0.2470</td><td></td><td></td><td>0.2320</td><td></td></tr>
  </tbody>
 </table>
</body></html>
""".strip()


class BspHtmlParseTests(SimpleTestCase):
    def test_bsp_parse_and_inversion(self):
        provider = BspHtmlProvider()
        with patch.object(BspHtmlProvider, "_fetch_html", return_value=USD_TABLE_HTML):
            rows = provider.fetch(["PGK:USD", "USD:PGK"])
        got = {(r.base_ccy, r.quote_ccy, r.rate_type): r.rate for r in rows}
        self.assertEqual(got[("PGK", "USD", "BUY")], Decimal("0.2470"))
        self.assertEqual(got[("PGK", "USD", "SELL")], Decimal("0.2320"))
        self.assertEqual(got[("USD", "PGK", "BUY")], Decimal("4.0486"))  # 1/0.2470
        self.assertEqual(got[("USD", "PGK", "SELL")], Decimal("4.3103"))  # 1/0.2320

    def test_bsp_zeros_skip_direction(self):
        provider = BspHtmlProvider()
        html = USD_TABLE_HTML.replace("0.2470", "0.0000")
        with patch.object(BspHtmlProvider, "_fetch_html", return_value=html):
            rows = provider.fetch(["PGK:USD", "USD:PGK"])
        got = {(r.base_ccy, r.quote_ccy, r.rate_type): r.rate for r in rows}
        self.assertNotIn(("PGK", "USD", "BUY"), got)
        self.assertEqual(got[("PGK", "USD", "SELL")], Decimal("0.2320"))
        self.assertEqual(got[("USD", "PGK", "SELL")], Decimal("4.3103"))


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
