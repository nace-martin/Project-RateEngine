"""Deterministic FX market-rate resolution for RateEngine.

Wave 3B3 rules:
- ``FxMarketRate`` is the sole authority for new market FX facts.
- Resolution uses the latest published rate on or before the quote date.
- Currency-pair orientation is explicit; no magnitude heuristics are permitted.
- Missing or ambiguous market facts fail closed.
- PGK/PGK (and other same-currency conversions) are identity operations and do
  not require a database FX fact.

Rates returned by this module are always expressed as ``quote currency per one
unit of base currency``.  For example, AUD/PGK 2.50 means PGK 2.50 per AUD 1.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from django.db.models import QuerySet

from core.fx_market_models import FxMarketRate

TTSide = Literal["BUY", "SELL"]


class FxResolutionError(ValueError):
    """Base error for deterministic FX resolution failures."""


class InvalidFxRequestError(FxResolutionError):
    """Raised when a currency/date/side request is invalid."""


class MissingFxRateError(FxResolutionError):
    """Raised when no authoritative market fact exists for a required pair."""


class AmbiguousFxRateSourceError(FxResolutionError):
    """Raised when multiple sources compete for the same latest market fact."""


@dataclass(frozen=True)
class ResolvedFxPair:
    """A deterministic market pair expressed as quote currency per base unit."""

    base_currency: str
    quote_currency: str
    effective_date: date
    source: str
    tt_buy_rate: Decimal
    tt_sell_rate: Decimal
    path: tuple[str, ...]

    def rate_for(self, side: TTSide | str) -> Decimal:
        normalized = str(side or "").strip().upper()
        if normalized == "BUY":
            return self.tt_buy_rate
        if normalized == "SELL":
            return self.tt_sell_rate
        raise InvalidFxRequestError(f"Unsupported TT side '{side}'. Expected BUY or SELL.")


def _currency(value: str) -> str:
    code = str(value or "").strip().upper()
    if len(code) != 3 or not code.isalpha():
        raise InvalidFxRequestError(
            f"Currency code must be exactly three letters, got '{value}'."
        )
    return code


def _effective_date(value: date | datetime | str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            raise InvalidFxRequestError("FX effective date cannot be empty.")
        try:
            return date.fromisoformat(cleaned.split("T", 1)[0].split(" ", 1)[0])
        except ValueError as exc:
            raise InvalidFxRequestError(
                f"Invalid FX effective date '{value}'."
            ) from exc
    raise InvalidFxRequestError(
        f"Unsupported FX effective date type: {type(value).__name__}."
    )


def _latest_row(
    *,
    base_currency: str,
    quote_currency: str,
    effective_date: date,
    source: str | None,
) -> FxMarketRate | None:
    qs: QuerySet[FxMarketRate] = FxMarketRate.objects.filter(
        base_currency=base_currency,
        quote_currency=quote_currency,
        effective_date__lte=effective_date,
    )
    if source:
        qs = qs.filter(source=source)

    latest_date = (
        qs.order_by("-effective_date")
        .values_list("effective_date", flat=True)
        .first()
    )
    if latest_date is None:
        return None

    latest = qs.filter(effective_date=latest_date).order_by("source")
    if source:
        return latest.first()

    candidates = list(latest[:2])
    if len(candidates) > 1:
        sources = sorted({row.source for row in candidates})
        raise AmbiguousFxRateSourceError(
            "Multiple FX sources exist for "
            f"{base_currency}/{quote_currency} on {latest_date}: {', '.join(sources)}. "
            "Specify a source or establish an approved source-priority rule."
        )
    return candidates[0] if candidates else None


def _from_row(row: FxMarketRate) -> ResolvedFxPair:
    return ResolvedFxPair(
        base_currency=row.base_currency,
        quote_currency=row.quote_currency,
        effective_date=row.effective_date,
        source=row.source,
        tt_buy_rate=row.tt_buy_rate,
        tt_sell_rate=row.tt_sell_rate,
        path=(f"{row.base_currency}/{row.quote_currency}",),
    )


def _invert(pair: ResolvedFxPair) -> ResolvedFxPair:
    # Bid/ask inversion reverses sides:
    # inverse BUY = 1 / original SELL
    # inverse SELL = 1 / original BUY
    return ResolvedFxPair(
        base_currency=pair.quote_currency,
        quote_currency=pair.base_currency,
        effective_date=pair.effective_date,
        source=pair.source,
        tt_buy_rate=Decimal(1) / pair.tt_sell_rate,
        tt_sell_rate=Decimal(1) / pair.tt_buy_rate,
        path=pair.path + ("INVERTED",),
    )


def _resolve_pgk_leg(
    currency: str,
    target_date: date,
    source: str | None,
) -> ResolvedFxPair:
    direct = _latest_row(
        base_currency=currency,
        quote_currency="PGK",
        effective_date=target_date,
        source=source,
    )
    if direct:
        return _from_row(direct)

    inverse = _latest_row(
        base_currency="PGK",
        quote_currency=currency,
        effective_date=target_date,
        source=source,
    )
    if inverse:
        return _invert(_from_row(inverse))

    raise MissingFxRateError(
        f"No authoritative FX market rate found for {currency}/PGK on or before {target_date}."
    )


def resolve_market_fx_pair(
    base_currency: str,
    quote_currency: str,
    effective_date: date | datetime | str,
    *,
    source: str | None = None,
) -> ResolvedFxPair:
    """Resolve a market FX pair deterministically.

    Selection order:
    1. Same-currency identity.
    2. Direct stored pair.
    3. Stored inverse pair (with BUY/SELL swap on inversion).
    4. Cross currency through PGK.

    When ``source`` is omitted and more than one source exists for the latest
    eligible date of a required pair, resolution fails closed instead of
    arbitrarily choosing one.
    """

    base = _currency(base_currency)
    quote = _currency(quote_currency)
    target_date = _effective_date(effective_date)
    normalized_source = str(source or "").strip() or None

    if base == quote:
        return ResolvedFxPair(
            base_currency=base,
            quote_currency=quote,
            effective_date=target_date,
            source="IDENTITY",
            tt_buy_rate=Decimal(1),
            tt_sell_rate=Decimal(1),
            path=(f"{base}/{quote}", "IDENTITY"),
        )

    direct = _latest_row(
        base_currency=base,
        quote_currency=quote,
        effective_date=target_date,
        source=normalized_source,
    )
    if direct:
        return _from_row(direct)

    inverse = _latest_row(
        base_currency=quote,
        quote_currency=base,
        effective_date=target_date,
        source=normalized_source,
    )
    if inverse:
        return _invert(_from_row(inverse))

    if base == "PGK" or quote == "PGK":
        raise MissingFxRateError(
            f"No authoritative FX market rate found for {base}/{quote} on or before {target_date}."
        )

    base_to_pgk = _resolve_pgk_leg(base, target_date, normalized_source)
    quote_to_pgk = _resolve_pgk_leg(quote, target_date, normalized_source)

    if normalized_source is None and base_to_pgk.source != quote_to_pgk.source:
        raise AmbiguousFxRateSourceError(
            "Cross-currency FX legs resolve to different sources "
            f"({base_to_pgk.source} vs {quote_to_pgk.source}). "
            "Specify one source or establish an approved source-priority rule."
        )

    # A/B cross through PGK:
    # BUY(A/B) = BUY(A/PGK) / SELL(B/PGK)
    # SELL(A/B) = SELL(A/PGK) / BUY(B/PGK)
    return ResolvedFxPair(
        base_currency=base,
        quote_currency=quote,
        effective_date=min(base_to_pgk.effective_date, quote_to_pgk.effective_date),
        source=(normalized_source or base_to_pgk.source),
        tt_buy_rate=base_to_pgk.tt_buy_rate / quote_to_pgk.tt_sell_rate,
        tt_sell_rate=base_to_pgk.tt_sell_rate / quote_to_pgk.tt_buy_rate,
        path=base_to_pgk.path + quote_to_pgk.path + ("CROSS_VIA_PGK",),
    )


def resolve_market_fx_rate(
    base_currency: str,
    quote_currency: str,
    effective_date: date | datetime | str,
    tt_side: TTSide | str,
    *,
    source: str | None = None,
) -> Decimal:
    """Resolve one BUY/SELL market rate for a currency pair."""

    return resolve_market_fx_pair(
        base_currency,
        quote_currency,
        effective_date,
        source=source,
    ).rate_for(tt_side)


def convert_market_amount(
    amount: Decimal,
    from_currency: str,
    to_currency: str,
    effective_date: date | datetime | str,
    tt_side: TTSide | str,
    *,
    source: str | None = None,
) -> Decimal:
    """Convert an amount using the resolved pure market rate (CAF excluded)."""

    pair = resolve_market_fx_pair(
        from_currency,
        to_currency,
        effective_date,
        source=source,
    )
    return amount * pair.rate_for(tt_side)
