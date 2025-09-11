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
        zero_html = """
        <table>
          <tr><th>Currency</th><th>Code</th><th>TT Buy</th><th>Notes Buy</th><th>A/M Buy</th><th>TT Sell</th><th>Notes Sell</th></tr>
          <tr><td>US Dollar</td><td>USD</td><td>0.0000</td><td></td><td></td><td>0.2320</td><td></td></tr>
        </table>
        """.strip()
        p = BspHtmlProvider()
        with patch.object(BspHtmlProvider, "_fetch_html", return_value=zero_html):
            rows = p.fetch(["PGK:USD", "USD:PGK"])
        kinds = {(r.base_ccy, r.quote_ccy, r.rate_type) for r in rows}
        self.assertNotIn(("PGK", "USD", "BUY"), kinds)
        self.assertIn(("PGK", "USD", "SELL"), kinds)
        self.assertNotIn(("USD", "PGK", "BUY"), kinds)
        self.assertIn(("USD", "PGK", "SELL"), kinds)

    def test_bsp_table_not_found(self):
        p = BspHtmlProvider()
        with patch.object(BspHtmlProvider, "_fetch_html", return_value="<html>No table</html>"):
            with self.assertRaises(RuntimeError):
                p.fetch(["PGK:USD"])  # shape error


class FxCommandIdempotencyTests(TestCase):
    databases = {"default"}

    def setUp(self):
        # Skip if currency_rates table is not present in this DB
        if 'currency_rates' not in connection.introspection.table_names():
            self.skipTest("currency_rates table not available; skipping idempotency test")

    def test_command_idempotent(self):
        fixed_ts = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        class StubProvider:
            def fetch(self, pairs):
                out = []
                for pair in pairs:
                    base, quote = pair.split(":", 1)
                    out.append(RateRow(fixed_ts, base, quote, Decimal("1.2345"), "BUY", "bsp_html"))
                    out.append(RateRow(fixed_ts, base, quote, Decimal("1.3456"), "SELL", "bsp_html"))
                return out

        with patch("rate_engine.management.commands.fetch_fx.load_provider", return_value=StubProvider()):
            call_command("fetch_fx", "--pairs", "USD:PGK,PGK:USD", "--provider", "bsp_html")
            from rate_engine.models import CurrencyRates as CurrencyRate
            first = CurrencyRate.objects.count()
            call_command("fetch_fx", "--pairs", "USD:PGK,PGK:USD", "--provider", "bsp_html")
            second = CurrencyRate.objects.count()
            self.assertEqual(first, second)

