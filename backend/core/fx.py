"""FX utility functions for rate management.

Wave 3B3 makes ``FxMarketRate`` the authority for new market facts while
retaining ``FxSnapshot`` as historical quote evidence.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP


def d(val) -> Decimal:
    """Convert value to Decimal."""
    if isinstance(val, Decimal):
        return val
    return Decimal(str(val))


class FxUnavailableError(Exception):
    """Raised when required FX facts cannot be retrieved or persisted safely."""


@dataclass
class MidRateResult:
    """Result from a mid rate lookup."""

    rate: Decimal
    as_of: datetime


class EnvProvider:
    """Environment-variable FX provider used only when explicitly selected."""

    def get_mid_rate(self, base: str, quote: str) -> MidRateResult:
        env_key = f"FX_{base.upper()}_{quote.upper()}_MID"
        rate_str = os.environ.get(env_key)
        if not rate_str:
            raise ValueError(f"Environment variable {env_key} not set")
        return MidRateResult(
            rate=d(rate_str),
            as_of=datetime.now(timezone.utc),
        )


def compute_tt_buy_sell(
    mid_rate: Decimal,
    spread_bps: int = 100,
) -> tuple[Decimal, Decimal]:
    """Calculate TT Buy/Sell around a supplied mid rate."""

    spread_pct = Decimal(spread_bps) / Decimal("10000")
    half_spread = spread_pct / 2
    tt_buy = (mid_rate * (Decimal(1) - half_spread)).quantize(
        Decimal("0.0001"), rounding=ROUND_HALF_UP
    )
    tt_sell = (mid_rate * (Decimal(1) + half_spread)).quantize(
        Decimal("0.0001"), rounding=ROUND_HALF_UP
    )
    return tt_buy, tt_sell


def _canonical_fcy_pgk_pair(
    base_ccy: str,
    quote_ccy: str,
    tt_buy: Decimal,
    tt_sell: Decimal,
) -> tuple[str, str, Decimal, Decimal]:
    """Normalize a PGK cross to canonical FCY/PGK orientation.

    Canonical facts are quote currency (PGK) per one unit of foreign base
    currency.  If an input arrives as PGK/FCY it is inverted and BUY/SELL are
    swapped.
    """

    base = str(base_ccy or "").strip().upper()
    quote = str(quote_ccy or "").strip().upper()
    buy = d(tt_buy)
    sell = d(tt_sell)

    if buy <= 0 or sell <= 0:
        raise FxUnavailableError("TT BUY and TT SELL must both be strictly positive.")
    if base == quote:
        raise FxUnavailableError("FX market facts must use distinct currencies.")

    if quote == "PGK" and base != "PGK":
        return base, "PGK", buy, sell

    if base == "PGK" and quote != "PGK":
        # Inverse BUY = 1 / original SELL; inverse SELL = 1 / original BUY.
        return quote, "PGK", Decimal(1) / sell, Decimal(1) / buy

    raise FxUnavailableError(
        f"Canonical market persistence currently requires a PGK cross, got {base}/{quote}."
    )


def upsert_market_rate(
    *,
    as_of: datetime,
    base_ccy: str,
    quote_ccy: str,
    tt_buy: Decimal,
    tt_sell: Decimal,
    source: str,
    update_snapshot: bool = True,
):
    """Persist one complete canonical market fact.

    The authoritative database row is ``FxMarketRate``.  When
    ``update_snapshot`` is true, the same fact is also copied into the current
    source/day ``FxSnapshot`` so existing quote-history persistence remains
    intact during the Wave 3 cleanup.
    """

    from core.fx_market_models import FxMarketRate
    from core.models import FxSnapshot

    canonical_base, canonical_quote, canonical_buy, canonical_sell = (
        _canonical_fcy_pgk_pair(base_ccy, quote_ccy, tt_buy, tt_sell)
    )
    normalized_source = str(source or "").strip()
    if not normalized_source:
        raise FxUnavailableError("FX source is required.")

    effective_date = as_of.date()
    mid = (canonical_buy + canonical_sell) / Decimal(2)

    market_rate, _ = FxMarketRate.objects.update_or_create(
        base_currency=canonical_base,
        quote_currency=canonical_quote,
        effective_date=effective_date,
        source=normalized_source,
        defaults={
            "tt_buy_rate": canonical_buy,
            "tt_sell_rate": canonical_sell,
            "mid_rate": mid,
        },
    )

    if update_snapshot:
        snapshot = (
            FxSnapshot.objects.filter(
                source=normalized_source,
                as_of_timestamp__date=effective_date,
            )
            .order_by("-as_of_timestamp")
            .first()
        )
        if snapshot is None:
            snapshot = FxSnapshot.objects.create(
                as_of_timestamp=as_of,
                source=normalized_source,
                rates={},
                caf_percent=Decimal("0.0"),
                fx_buffer_percent=Decimal("0.0"),
            )

        rates = dict(snapshot.rates or {})
        rates[canonical_base] = {
            "tt_buy": str(canonical_buy),
            "tt_sell": str(canonical_sell),
            "effective_date": effective_date.isoformat(),
            "source": normalized_source,
        }
        snapshot.rates = rates
        snapshot.as_of_timestamp = as_of
        snapshot.save(update_fields=["rates", "as_of_timestamp"])

    return market_rate
