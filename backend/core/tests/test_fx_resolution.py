from datetime import date
from decimal import Decimal

import pytest

from core.fx_market_models import FxMarketRate
from core.fx_resolution import (
    AmbiguousFxRateSourceError,
    MissingFxRateError,
    convert_market_amount,
    resolve_market_fx_pair,
    resolve_market_fx_rate,
)


@pytest.mark.django_db
class TestFxResolution:
    def _rate(
        self,
        base: str,
        quote: str,
        effective_date: date,
        buy: str,
        sell: str,
        *,
        source: str = "BSP",
    ) -> FxMarketRate:
        buy_d = Decimal(buy)
        sell_d = Decimal(sell)
        return FxMarketRate.objects.create(
            base_currency=base,
            quote_currency=quote,
            effective_date=effective_date,
            tt_buy_rate=buy_d,
            tt_sell_rate=sell_d,
            mid_rate=(buy_d + sell_d) / Decimal(2),
            source=source,
        )

    def test_weekend_uses_latest_rate_on_or_before_quote_date(self):
        self._rate("AUD", "PGK", date(2026, 9, 25), "2.45", "2.52")

        resolved = resolve_market_fx_pair("AUD", "PGK", date(2026, 9, 27))

        assert resolved.effective_date == date(2026, 9, 25)
        assert resolved.tt_buy_rate == Decimal("2.45")
        assert resolved.tt_sell_rate == Decimal("2.52")

    def test_future_rate_never_resolves_backward(self):
        self._rate("AUD", "PGK", date(2026, 9, 28), "2.50", "2.57")

        with pytest.raises(MissingFxRateError):
            resolve_market_fx_pair("AUD", "PGK", date(2026, 9, 27))

    def test_direct_pair_is_quote_currency_per_base_unit(self):
        self._rate("AUD", "PGK", date(2026, 9, 24), "2.45", "2.52")

        assert resolve_market_fx_rate(
            "AUD", "PGK", date(2026, 9, 24), "BUY"
        ) == Decimal("2.45")
        assert convert_market_amount(
            Decimal("100"), "AUD", "PGK", date(2026, 9, 24), "BUY"
        ) == Decimal("245.00")

    def test_inverse_pair_swaps_buy_and_sell(self):
        self._rate("AUD", "PGK", date(2026, 9, 24), "2.40", "2.50")

        inverse = resolve_market_fx_pair("PGK", "AUD", date(2026, 9, 24))

        assert inverse.tt_buy_rate == Decimal(1) / Decimal("2.50")
        assert inverse.tt_sell_rate == Decimal(1) / Decimal("2.40")
        assert "INVERTED" in inverse.path

    def test_cross_currency_is_resolved_through_pgk(self):
        self._rate("AUD", "PGK", date(2026, 9, 24), "2.40", "2.50")
        self._rate("USD", "PGK", date(2026, 9, 24), "3.80", "3.90")

        cross = resolve_market_fx_pair("AUD", "USD", date(2026, 9, 24))

        assert cross.tt_buy_rate == Decimal("2.40") / Decimal("3.90")
        assert cross.tt_sell_rate == Decimal("2.50") / Decimal("3.80")
        assert cross.source == "BSP"
        assert "CROSS_VIA_PGK" in cross.path

    def test_same_currency_is_identity_without_market_row(self):
        resolved = resolve_market_fx_pair("PGK", "PGK", date(2026, 9, 24))

        assert resolved.tt_buy_rate == Decimal(1)
        assert resolved.tt_sell_rate == Decimal(1)
        assert resolved.source == "IDENTITY"

    def test_competing_sources_on_latest_date_fail_closed(self):
        self._rate("AUD", "PGK", date(2026, 9, 24), "2.40", "2.50", source="BSP")
        self._rate("AUD", "PGK", date(2026, 9, 24), "2.41", "2.51", source="MANUAL")

        with pytest.raises(AmbiguousFxRateSourceError):
            resolve_market_fx_pair("AUD", "PGK", date(2026, 9, 24))

        manual = resolve_market_fx_pair(
            "AUD", "PGK", date(2026, 9, 24), source="MANUAL"
        )
        assert manual.tt_buy_rate == Decimal("2.41")

    def test_cross_currency_mixed_sources_fail_closed(self):
        self._rate("AUD", "PGK", date(2026, 9, 24), "2.40", "2.50", source="BSP")
        self._rate("USD", "PGK", date(2026, 9, 24), "3.80", "3.90", source="MANUAL")

        with pytest.raises(AmbiguousFxRateSourceError):
            resolve_market_fx_pair("AUD", "USD", date(2026, 9, 24))

    def test_missing_pair_fails_closed(self):
        with pytest.raises(MissingFxRateError):
            resolve_market_fx_pair("USD", "PGK", date(2026, 9, 24))
