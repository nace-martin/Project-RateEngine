from __future__ import annotations

from decimal import Decimal
from datetime import datetime, timezone

import pytest
from django.core.management import call_command
from django.utils.timezone import now

from rate_engine.fx_providers.bsp_html import BspHtmlProvider
from rate_engine.fx_providers import RateRow
from rate_engine.models import CurrencyRates as CurrencyRate


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


def test_bsp_parse_and_inversion(monkeypatch):
    p = BspHtmlProvider()
    monkeypatch.setattr(p, "_fetch_html", lambda: USD_TABLE_HTML)
    rows = p.fetch(["PGK:USD", "USD:PGK"])
    # Make a dict for quick checks: (base, quote, type) -> rate
    got = {(r.base_ccy, r.quote_ccy, r.rate_type): r.rate for r in rows}
    assert got[("PGK", "USD", "BUY")] == Decimal("0.2470")
    assert got[("PGK", "USD", "SELL")] == Decimal("0.2320")
    # inverted 1/0.2470 rounded 4dp -> 4.0486
    assert got[("USD", "PGK", "BUY")] == Decimal("4.0486")
    # inverted 1/0.2320 -> 4.3103
    assert got[("USD", "PGK", "SELL")] == Decimal("4.3103")


def test_bsp_zeros_skip_direction(monkeypatch):
    html = """
    <table>
      <tr><th>Currency</th><th>Code</th><th>TT Buy</th><th>Notes Buy</th><th>A/M Buy</th><th>TT Sell</th><th>Notes Sell</th></tr>
      <tr><td>US Dollar</td><td>USD</td><td>0.0000</td><td></td><td></td><td>0.2320</td><td></td></tr>
    </table>
    """.strip()
    p = BspHtmlProvider()
    monkeypatch.setattr(p, "_fetch_html", lambda: html)
    rows = p.fetch(["PGK:USD", "USD:PGK"])
    kinds = {(r.base_ccy, r.quote_ccy, r.rate_type) for r in rows}
    # PGK:USD BUY is zero -> skipped; SELL present
    assert ("PGK", "USD", "BUY") not in kinds
    assert ("PGK", "USD", "SELL") in kinds
    # For inverted USD:PGK BUY uses 1/0.0000 -> skip; SELL present
    assert ("USD", "PGK", "BUY") not in kinds
    assert ("USD", "PGK", "SELL") in kinds


def test_bsp_table_not_found(monkeypatch):
    p = BspHtmlProvider()
    monkeypatch.setattr(p, "_fetch_html", lambda: "<html><body>No table here</body></html>")
    with pytest.raises(RuntimeError, match="BSP FX: table not found"):
        p.fetch(["PGK:USD"])  # doesn't matter


@pytest.mark.django_db
def test_command_idempotent(monkeypatch):
    # Skip if the currency_rates table is not present in the configured DB
    from django.db import connection
    if 'currency_rates' not in connection.introspection.table_names():
        pytest.skip("currency_rates table not available; skipping idempotency test")

    # Stub provider loader to avoid network and ensure consistent as_of
    fixed_ts = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    class StubProvider:
        def fetch(self, pairs):
            out = []
            for pair in pairs:
                base, quote = pair.split(":", 1)
                out.append(RateRow(fixed_ts, base, quote, Decimal("1.2345"), "BUY", "bsp_html"))
                out.append(RateRow(fixed_ts, base, quote, Decimal("1.3456"), "SELL", "bsp_html"))
            return out

    from rate_engine.management.commands import fetch_fx as cmd
    monkeypatch.setattr(cmd, "load_provider", lambda name: StubProvider())

    # Run command twice with same timestamp; unique index prevents duplicates
    call_command("fetch_fx", "--pairs", "USD:PGK,PGK:USD", "--provider", "bsp_html")
    first = CurrencyRate.objects.count()
    call_command("fetch_fx", "--pairs", "USD:PGK,PGK:USD", "--provider", "bsp_html")
    second = CurrencyRate.objects.count()

    assert first == second
