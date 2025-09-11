from __future__ import annotations

from decimal import Decimal
from datetime import datetime, timezone
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase
from django.core.management import call_command
from django.db import connection

from rate_engine.fx_providers.bsp_html import BspHtmlProvider
from rate_engine.fx_providers import RateRow


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
        p = BspHtmlProvider()
        with patch.object(BspHtmlProvider, "_fetch_html", return_value=USD_TABLE_HTML):
            rows = p.fetch(["PGK:USD", "USD:PGK"])
        got = {(r.base_ccy, r.quote_ccy, r.rate_type): r.rate for r in rows}
        self.assertEqual(got[("PGK", "USD", "BUY")], Decimal("0.2470"))
        self.assertEqual(got[("PGK", "USD", "SELL")], Decimal("0.2320"))
        self.assertEqual(got[("USD", "PGK", "BUY")], Decimal("4.0486"))  # 1/0.2470
        self.assertEqual(got[("USD", "PGK", "SELL")], Decimal("4.3103"))  # 1/0.2320

    def test_bsp_zeros_skip_direction(self):
        p = BspHtmlProvider()
        html = USD_TABLE_HTML.replace("0.2470", "0.0000")
        with patch.object(BspHtmlProvider, "_fetch_html", return_value=html):
            rows = p.fetch(["PGK:USD", "USD:PGK"])
        got = {(r.base_ccy, r.quote_ccy, r.rate_type): r.rate for r in rows}
        self.assertNotIn(("PGK", "USD", "BUY"), got)
        self.assertEqual(got[("PGK", "USD", "SELL")], Decimal("0.2320"))
        self.assertEqual(got[("USD", "PGK", "SELL")], Decimal("4.3103"))


