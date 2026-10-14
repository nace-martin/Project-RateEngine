"""Pilot Gate B3L-C: BSP TT BUY / TT SELL mapping into the normalized PGK-per-FCY store.

The HTML fixture is shaped like the BSP exchange-rate page and carries the AUD and USD figures observed
on 2026-10-12 (published as FOREIGN CURRENCY PER 1 KINA). The values are test data, not approved rates.

Evidence for the mapping (see docs/b3l-c-bsp-fx-mapping.md; sides used for conversion corrected in B3M-E): the page is headed "Exchange rates for
Kina"; for AUD the columns read Notes Buy 0.3434 > TT Buy 0.3216 > TT Sell 0.3066 > Notes Sell 0.2854.
Read as AUD per PGK from the bank's side, that is the bank paying least for banknotes it buys and
charging most for banknotes it sells, with TT between the two. Read from the customer's side the notes
columns would be favourable to the customer, which is impossible. Hence TT Buy / TT Sell are bank sides.
"""

from datetime import date, datetime, timezone
from decimal import Decimal as D
from unittest.mock import Mock, patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from core.fx_market_models import FxMarketRate
from core.fx_providers.bsp_html import BspHtmlProvider
from pricing_v4.engine.import_engine import ImportPricingEngine, PaymentTerm, ServiceScope
from pricing_v4.services.fx_resolver import resolve_market_fx_pair

EFFECTIVE = date(2026, 10, 12)


def page(heading="Exchange rates for Kina", rows=None, when="Mon, 12 October 2026"):
    rows = rows or (
        ("Australian Dollar", "AUD", "0.3216", "0.3434", "0.0000", "0.3066", "0.2854"),
        ("US Dollar", "USD", "0.2315", "0.2378", "0.0000", "0.2165", "0.1871"),
    )
    body = "".join(
        "<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows
    )
    return f"""
    <section rel="CBCurrenciesTable">
      <header><h2>{heading}<time>{when}</time></h2></header>
      <table>
        <thead><tr><th>Currency</th><th>BSP Buy</th><th>BSP Sell</th></tr></thead>
      </table>
      <table>
        <thead><tr><th>Currency</th><th>Code</th><th>TT Buy</th><th>Notes Buy</th><th>A/M Buy</th>
          <th>TT Sell</th><th>Notes Sell</th></tr></thead>
        <tbody>{body}</tbody>
      </table>
    </section>"""


def fetch(html, pairs):
    provider = BspHtmlProvider()
    with patch.object(provider, "_fetch_html", return_value=html):
        return provider.fetch(pairs)


def sides(rows, base, quote):
    return {r.rate_type: r.rate for r in rows if (r.base_ccy, r.quote_ccy) == (base, quote)}


class TestProvider:
    def test_fcy_to_pgk_rows_are_pgk_per_fcy_with_the_bank_side_kept(self):
        rows = sides(fetch(page(), ["AUD:PGK"]), "AUD", "PGK")
        assert rows["BUY"] == D("3.10945274")   # 1 / 0.3216 : bank buys AUD, pays the fewer PGK
        assert rows["SELL"] == D("3.26157860")  # 1 / 0.3066 : bank sells AUD, charges the more PGK
        assert rows["SELL"] > rows["BUY"]

    def test_pgk_to_fcy_rows_are_the_published_figures_unchanged(self):
        rows = sides(fetch(page(), ["PGK:AUD"]), "PGK", "AUD")
        assert rows == {"BUY": D("0.3216"), "SELL": D("0.3066")}

    def test_both_orientations_describe_the_same_economics(self):
        direct = sides(fetch(page(), ["AUD:PGK"]), "AUD", "PGK")
        inverse = sides(fetch(page(), ["PGK:AUD"]), "PGK", "AUD")
        for side in ("BUY", "SELL"):
            assert (D(1) / inverse[side]).quantize(D("0.00000001")) == direct[side]

    def test_heading_that_is_not_per_kina_fails_closed(self):
        with pytest.raises(RuntimeError, match="orientation not confirmed"):
            fetch(page(heading="Exchange rates for Australian Dollar"), ["AUD:PGK"])

    def test_missing_published_date_fails_closed(self):
        html = page().replace("<time>Mon, 12 October 2026</time>", "")
        with pytest.raises(RuntimeError, match="effective date missing"):
            fetch(html, ["AUD:PGK"])

    def test_zero_published_rate_yields_no_row_for_that_side(self):
        html = page(rows=(("Australian Dollar", "AUD", "0.0000", "0", "0", "0.3066", "0"),))
        rows = fetch(html, ["AUD:PGK"])
        assert set(sides(rows, "AUD", "PGK")) == {"SELL"}


@pytest.mark.django_db
class TestLoader:
    def run(self, html, pairs):
        provider = BspHtmlProvider()
        with patch.object(provider, "_fetch_html", return_value=html), \
                patch("core.management.commands.fetch_fx.load_provider", return_value=provider):
            call_command("fetch_fx", pairs=pairs)

    @pytest.mark.parametrize("pairs", ["AUD:PGK", "PGK:AUD", "AUD:PGK,PGK:AUD"])
    def test_real_shaped_page_loads_with_the_same_normalized_rate_for_any_pair_orientation(self, pairs):
        FxMarketRate.objects.all().delete()
        self.run(page(), pairs)
        row = FxMarketRate.objects.get(base_currency="AUD", quote_currency="PGK", source="bsp_html")
        assert row.tt_buy_rate == D("3.10945274")
        assert row.tt_sell_rate == D("3.26157860")
        assert row.tt_sell_rate > row.tt_buy_rate
        assert row.effective_date == EFFECTIVE
        assert FxMarketRate.objects.count() == 1  # one canonical fact, whichever orientation was fetched

    def test_the_production_refresh_orientation_loads(self):
        FxMarketRate.objects.all().delete()
        self.run(page(), "PGK:AUD,PGK:USD")
        usd = FxMarketRate.objects.get(base_currency="USD", quote_currency="PGK")
        assert usd.tt_buy_rate == D("4.31965443") and usd.tt_sell_rate == D("4.61893764")

    def test_impossible_page_orientation_still_fails_closed_without_writing(self):
        # TT Buy below TT Sell as published (FCY per PGK) would put the bank's sell rate below its buy rate.
        html = page(rows=(("Australian Dollar", "AUD", "0.3066", "0.3434", "0", "0.3216", "0.2854"),))
        FxMarketRate.objects.all().delete()
        with pytest.raises(CommandError, match="TT SELL is below TT BUY"):
            self.run(html, "PGK:AUD")
        assert not FxMarketRate.objects.exists()

    def test_missing_side_fails_closed(self):
        html = page(rows=(("Australian Dollar", "AUD", "0.3216", "0", "0", "0.0000", "0"),))
        with pytest.raises(CommandError, match="Incomplete"):
            self.run(html, "PGK:AUD")
        assert not FxMarketRate.objects.exists()


APPROVED_CONVENTION = dict(
    caf_method="TO_PGK_RATE_REDUCTION_FROM_PGK_UPLIFT",
    fx_side_convention="FCY_TO_PGK_AT_TT_BUY_PGK_TO_FCY_AT_TT_SELL",
)


def load(html):
    FxMarketRate.objects.all().delete()
    provider = BspHtmlProvider()
    with patch.object(provider, "_fetch_html", return_value=html), \
            patch("core.management.commands.fetch_fx.load_provider", return_value=provider):
        call_command("fetch_fx", pairs="PGK:AUD")


def import_engine(quote_date, caf_rate=D("0.05")):
    return ImportPricingEngine(
        quote_date=quote_date, origin="SYD", destination="POM", chargeable_weight_kg=D("100"),
        payment_term=PaymentTerm.COLLECT, service_scope=ServiceScope.D2D, caf_rate=caf_rate,
        margin_rate=D("0.1667"), margin_method="TARGET_GROSS_MARGIN", **APPROVED_CONVENTION,
    )


@pytest.mark.django_db
class TestEconomicsEndToEnd:
    """Loaded BSP-shaped data drives the BSP calculator sides: FCY to PGK at TT BUY, PGK to FCY at TT SELL."""

    @pytest.fixture(autouse=True)
    def loaded(self, db):
        load(page())

    def test_aud_cost_to_pgk_converts_at_tt_buy_with_the_caf_reducing_the_rate(self):
        engine = import_engine(EFFECTIVE)
        # 100 AUD / (0.3216 x 0.95) = 100 x 3.10945274 / 0.95 = 327.31 PGK
        assert engine._convert_fcy_to_pgk(D("100"), "AUD") == D("327.31")
        leg = engine._conversions[0]["legs"][0]
        assert leg["side"] == "TT_BUY" and D(leg["rate"]) == D("3.10945274")

    def test_pgk_to_aud_converts_at_tt_sell_then_caf_uplift(self):
        engine = import_engine(EFFECTIVE)
        # 1000 PGK x 0.3066 = 1000 / 3.26157860 = 306.60 AUD ; CAF uplift x 1.05 = 321.93
        assert engine._convert_pgk_to_fcy(D("1000"), "AUD") == D("321.93")
        leg = engine._conversions[0]["legs"][0]
        assert leg["side"] == "TT_SELL" and D(leg["rate"]) == D("3.26157860")

    def test_resolved_pair_never_silently_swaps_the_sides(self):
        direct = resolve_market_fx_pair("AUD", "PGK", EFFECTIVE)
        assert (direct.tt_buy, direct.tt_sell) == (D("3.10945274"), D("3.26157860"))
        inverse = resolve_market_fx_pair("PGK", "AUD", EFFECTIVE)
        # inverse TT BUY = 1 / stored TT SELL ; inverse TT SELL = 1 / stored TT BUY
        assert inverse.tt_buy == (D(1) / D("3.26157860")).quantize(D("0.00000001"))
        assert inverse.tt_sell == (D(1) / D("3.10945274")).quantize(D("0.00000001"))
        assert inverse.tt_buy == D("0.30660000") and inverse.tt_sell == D("0.32160000")

    def test_direct_and_inverse_pairs_give_the_same_economics(self):
        direct = resolve_market_fx_pair("AUD", "PGK", EFFECTIVE)
        inverse = resolve_market_fx_pair("PGK", "AUD", EFFECTIVE)
        # PGK to AUD: PGK / stored TT SELL (direct) == PGK x published TT Sell (the inverse pair's bank-buys-PGK side)
        assert (D("1000") / direct.tt_sell).quantize(D("0.01")) == (D("1000") * inverse.tt_buy).quantize(D("0.01"))
        # AUD to PGK: AUD x stored TT BUY (direct) == AUD / published TT Buy (the inverse pair's bank-sells-PGK side)
        assert (D("100") * direct.tt_buy).quantize(D("0.01")) == (D("100") / inverse.tt_sell).quantize(D("0.01"))


BSP_2026_10_14 = page(
    rows=(("Australian Dollar", "AUD", "0.3215", "0.3433", "0.0000", "0.3065", "0.2853"),),
    when="Wed, 14 October 2026",
)


@pytest.mark.django_db
class TestBspCalculatorWorkedExamples:
    """BSP published AUD rates and calculator, 2026-10-14: TT Buy 0.3215, TT Sell 0.3065 (AUD per PGK)."""

    QUOTE_DATE = date(2026, 10, 14)

    @pytest.fixture(autouse=True)
    def loaded(self, db):
        load(BSP_2026_10_14)

    def test_stored_values_are_the_inverted_published_figures_without_a_side_swap(self):
        row = FxMarketRate.objects.get(base_currency="AUD", quote_currency="PGK")
        assert row.tt_buy_rate == (D(1) / D("0.3215")).quantize(D("0.00000001")) == D("3.11041991")
        assert row.tt_sell_rate == (D(1) / D("0.3065")).quantize(D("0.00000001")) == D("3.26264274")

    def test_pgk_1000_to_aud_is_337_15_under_the_export_rule(self):
        from pricing_v4.services.rate_matrix_export_shadow import convert_pgk_to_aud

        published = (D("1000") * D("0.3065")).quantize(D("0.01"))
        assert published == D("306.50") and (published * D("1.10")).quantize(D("0.01")) == D("337.15")
        tt_sell = resolve_market_fx_pair("AUD", "PGK", self.QUOTE_DATE).tt_sell
        assert convert_pgk_to_aud(D("1000"), tt_sell, D("0.10")) == (D("306.50"), D("30.65"), D("337.15"))

    def test_aud_100_to_pgk_is_327_41_under_the_import_rule(self):
        published = (D("100") / (D("0.3215") * D("0.95"))).quantize(D("0.01"))
        assert D("0.3215") * D("0.95") == D("0.305425") and published == D("327.41")
        engine = import_engine(self.QUOTE_DATE)
        assert engine._convert_fcy_to_pgk(D("100"), "AUD") == D("327.41")
        conversion = engine._conversions[0]
        assert conversion["legs"][0]["side"] == "TT_BUY"
        assert conversion["caf_operation"] == "PUBLISHED_RATE_REDUCED"
        assert (conversion["pure_market_amount"], conversion["caf_amount"]) == ("311.04", "16.37")

    def test_import_caf_is_not_an_uplift_on_the_pure_amount(self):
        # 311.04 x 1.05 = 326.59, which is not the BSP rate-reduction result 327.41
        assert (D("311.04") * D("1.05")).quantize(D("0.01")) == D("326.59")
        assert import_engine(self.QUOTE_DATE)._convert_fcy_to_pgk(D("100"), "AUD") != D("326.59")
