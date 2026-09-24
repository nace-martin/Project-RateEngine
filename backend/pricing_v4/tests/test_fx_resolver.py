"""
Tests for Deterministic Market FX Resolution Service (Wave 3B3).
"""

import datetime
from decimal import Decimal
import pytest

from core.fx_market_models import FxMarketRate
from pricing_v4.services.fx_resolver import (
    AmbiguousFxSourceError,
    InvalidCurrencyCodeError,
    InvalidFxEffectiveDateError,
    MissingFxMarketRateError,
    resolve_market_fx_pair,
    resolve_market_fx_rate,
)


@pytest.mark.django_db
class TestFxResolver:
    @pytest.fixture(autouse=True)
    def setup_rates(self):
        # Friday 2026-09-18 rates
        self.fx_aud_fri = FxMarketRate.objects.create(
            base_currency="AUD",
            quote_currency="PGK",
            effective_date=datetime.date(2026, 9, 18),
            tt_buy_rate=Decimal("2.45000000"),
            tt_sell_rate=Decimal("2.52000000"),
            mid_rate=Decimal("2.48500000"),
            source="BSP",
        )
        self.fx_usd_fri = FxMarketRate.objects.create(
            base_currency="USD",
            quote_currency="PGK",
            effective_date=datetime.date(2026, 9, 18),
            tt_buy_rate=Decimal("3.85000000"),
            tt_sell_rate=Decimal("3.95000000"),
            mid_rate=Decimal("3.90000000"),
            source="BSP",
        )
        # Monday 2026-09-21 new AUD rate
        self.fx_aud_mon = FxMarketRate.objects.create(
            base_currency="AUD",
            quote_currency="PGK",
            effective_date=datetime.date(2026, 9, 21),
            tt_buy_rate=Decimal("2.46000000"),
            tt_sell_rate=Decimal("2.53000000"),
            mid_rate=Decimal("2.49500000"),
            source="BSP",
        )

    def test_direct_rate_resolution(self):
        result = resolve_market_fx_pair(
            from_currency="AUD",
            to_currency="PGK",
            effective_date=datetime.date(2026, 9, 18),
        )
        assert result.from_currency == "AUD"
        assert result.to_currency == "PGK"
        assert result.tt_buy == Decimal("2.45000000")
        assert result.tt_sell == Decimal("2.52000000")
        assert result.mid_rate == Decimal("2.48500000")
        assert result.effective_date == datetime.date(2026, 9, 18)
        assert result.source == "BSP"
        assert not result.is_inverse

    def test_weekend_quote_resolves_friday_rate(self):
        # Saturday quote
        sat_result = resolve_market_fx_pair(
            from_currency="AUD",
            to_currency="PGK",
            effective_date=datetime.date(2026, 9, 19),
        )
        assert sat_result.effective_date == datetime.date(2026, 9, 18)
        assert sat_result.tt_buy == Decimal("2.45000000")

        # Sunday quote
        sun_result = resolve_market_fx_pair(
            from_currency="AUD",
            to_currency="PGK",
            effective_date=datetime.date(2026, 9, 20),
        )
        assert sun_result.effective_date == datetime.date(2026, 9, 18)
        assert sun_result.tt_buy == Decimal("2.45000000")

        # Monday quote resolves Monday's updated rate
        mon_result = resolve_market_fx_pair(
            from_currency="AUD",
            to_currency="PGK",
            effective_date=datetime.date(2026, 9, 21),
        )
        assert mon_result.effective_date == datetime.date(2026, 9, 21)
        assert mon_result.tt_buy == Decimal("2.46000000")

    def test_future_rate_never_resolves_backward(self):
        # Prior to Friday 2026-09-18: no rate exists
        with pytest.raises(MissingFxMarketRateError) as exc_info:
            resolve_market_fx_pair(
                from_currency="AUD",
                to_currency="PGK",
                effective_date=datetime.date(2026, 9, 17),
            )
        assert "No authoritative FX market rate found" in str(exc_info.value)

    def test_inverse_resolution_with_side_reversal(self):
        # Querying PGK -> AUD (when only AUD/PGK exists in DB)
        result = resolve_market_fx_pair(
            from_currency="PGK",
            to_currency="AUD",
            effective_date=datetime.date(2026, 9, 18),
        )
        assert result.from_currency == "PGK"
        assert result.to_currency == "AUD"
        assert result.is_inverse is True

        # Inversion rule:
        # inverse TT BUY  = 1 / original TT SELL = 1 / 2.52000000
        expected_tt_buy = (Decimal("1") / Decimal("2.52000000")).quantize(Decimal("0.00000001"))
        # inverse TT SELL = 1 / original TT BUY  = 1 / 2.45000000
        expected_tt_sell = (Decimal("1") / Decimal("2.45000000")).quantize(Decimal("0.00000001"))

        assert result.tt_buy == expected_tt_buy
        assert result.tt_sell == expected_tt_sell

    def test_resolve_single_side_market_rate(self):
        buy_res = resolve_market_fx_rate(
            from_currency="AUD",
            to_currency="PGK",
            tt_side="BUY",
            effective_date="2026-09-18",
        )
        assert buy_res.rate == Decimal("2.45000000")
        assert buy_res.tt_side == "BUY"

        sell_res = resolve_market_fx_rate(
            from_currency="AUD",
            to_currency="PGK",
            tt_side="SELL",
            effective_date="2026-09-18",
        )
        assert sell_res.rate == Decimal("2.52000000")
        assert sell_res.tt_side == "SELL"
        mid_res = resolve_market_fx_rate("PGK", "AUD", "MID", "2026-09-18")
        assert mid_res.raw_rate == Decimal("2.48500000")
        assert (mid_res.base_currency, mid_res.quote_currency) == ("AUD", "PGK")

    def test_newer_inverse_fact_beats_older_direct_fact(self):
        FxMarketRate.objects.create(
            base_currency="PGK", quote_currency="AUD",
            effective_date=datetime.date(2026, 9, 17),
            tt_buy_rate=Decimal("0.39"), tt_sell_rate=Decimal("0.40"),
            mid_rate=Decimal("0.395"), source="BSP",
        )
        result = resolve_market_fx_pair("PGK", "AUD", datetime.date(2026, 9, 18))
        assert result.is_inverse
        assert result.effective_date == datetime.date(2026, 9, 18)

    def test_equal_date_competing_orientations_fail_closed(self):
        FxMarketRate.objects.create(
            base_currency="PGK", quote_currency="AUD",
            effective_date=datetime.date(2026, 9, 18),
            tt_buy_rate=Decimal("0.39"), tt_sell_rate=Decimal("0.40"),
            mid_rate=Decimal("0.395"), source="BSP",
        )
        with pytest.raises(AmbiguousFxSourceError):
            resolve_market_fx_pair("PGK", "AUD", datetime.date(2026, 9, 18))

    def test_cross_currency_resolution_via_pgk(self):
        # AUD -> USD via PGK:
        # AUD -> PGK (BUY 2.450, SELL 2.520)
        # PGK -> USD (BUY 1/3.950, SELL 1/3.850)
        result = resolve_market_fx_pair(
            from_currency="AUD",
            to_currency="USD",
            effective_date=datetime.date(2026, 9, 18),
        )
        assert result.is_cross is True
        assert result.from_currency == "AUD"
        assert result.to_currency == "USD"
        # leg1.tt_buy * leg2.tt_buy: 2.45000000 * (1 / 3.95000000 quantized to 8 decimals)
        assert result.tt_buy == Decimal("0.62025317")
        assert result.tt_sell == Decimal("0.65454546")

    def test_identity_resolution_requires_no_db_rate(self):
        # PGK -> PGK requires no FX
        result = resolve_market_fx_pair("PGK", "PGK", "2026-09-18")
        assert result.is_identity is True
        assert result.tt_buy == Decimal("1.0")
        assert result.tt_sell == Decimal("1.0")

        # USD -> USD identity
        usd_ident = resolve_market_fx_pair("USD", "USD", "2026-09-18")
        assert usd_ident.is_identity is True
        assert usd_ident.tt_buy == Decimal("1.0")

    def test_ambiguous_competing_sources_fails_closed(self):
        # Add a competing source for USD/PGK on same date
        FxMarketRate.objects.create(
            base_currency="USD",
            quote_currency="PGK",
            effective_date=datetime.date(2026, 9, 18),
            tt_buy_rate=Decimal("3.86000000"),
            tt_sell_rate=Decimal("3.96000000"),
            mid_rate=Decimal("3.91000000"),
            source="KINA_BANK",
        )
        # Without specifying source, fails closed
        with pytest.raises(AmbiguousFxSourceError) as exc_info:
            resolve_market_fx_pair("USD", "PGK", "2026-09-18")
        assert "Multiple competing FX sources" in str(exc_info.value)

        # Specifying explicit source succeeds
        res_bsp = resolve_market_fx_pair("USD", "PGK", "2026-09-18", source="BSP")
        assert res_bsp.tt_buy == Decimal("3.85000000")

        res_kb = resolve_market_fx_pair("USD", "PGK", "2026-09-18", source="KINA_BANK")
        assert res_kb.tt_buy == Decimal("3.86000000")

    def test_invalid_inputs_fail_closed(self):
        with pytest.raises(InvalidCurrencyCodeError):
            resolve_market_fx_pair("US", "PGK")
        with pytest.raises(InvalidCurrencyCodeError):
            resolve_market_fx_pair("USD", "123")
        with pytest.raises(InvalidFxEffectiveDateError):
            resolve_market_fx_pair("USD", "PGK", effective_date="not-a-date")
        with pytest.raises(InvalidFxEffectiveDateError):
            resolve_market_fx_pair("USD", "PGK", effective_date=12345)
