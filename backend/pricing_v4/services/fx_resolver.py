"""
Deterministic Market FX Resolution Service.

Resolves authoritative foreign exchange market rates from core.FxMarketRate (Wave 3B3).
Replaces legacy mutable core.FxRate and unvalidated snapshot lookups.

Governance & Rules:
1. Authority: core.FxMarketRate is the sole market FX authority for new calculations.
2. Canonical Orientation: FxMarketRate stores market facts primarily as FCY / PGK
   (base_currency=FCY, quote_currency=PGK, rate in PGK per 1 FCY).
3. Date Resolution: Latest valid published market rate on or before the quote date
   (effective_date <= quote_date, ordered by -effective_date). Future rates are never used.
4. Bid/Ask Inversion: When converting in inverse direction (PGK / FCY):
   - inverse TT BUY  = 1 / original TT SELL
   - inverse TT SELL = 1 / original TT BUY
   - inverse MID     = 1 / original MID
5. Cross-Currency: For A -> B where neither currency is PGK, resolves deterministically
   via PGK (A -> PGK -> B).
6. Source Governance: If multiple competing sources exist on the resolved effective date,
   an explicit source must be requested; otherwise fails closed with AmbiguousFxSourceError.
7. Identity: PGK -> PGK (or calculations requiring no conversion) resolves as identity (1.0)
   without requiring a market rate record.
8. Fail Closed: Missing required FX market rates fail closed with MissingFxMarketRateError.
   No silent defaults, no 1.0 foreign currency fallbacks, no 0.35 / 0.36 / 2.50 / 2.78 constants.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from django.db.models import QuerySet
from django.utils import timezone

from core.fx_market_models import FxMarketRate

logger = logging.getLogger(__name__)

CURRENCY_CODE_REGEX = re.compile(r"^[A-Z]{3}$")


class FxResolutionError(ValueError):
    """Base exception for FX rate resolution errors."""


class MissingFxMarketRateError(FxResolutionError):
    """Raised when an authoritative FX market rate is required but cannot be found."""


class AmbiguousFxSourceError(FxResolutionError):
    """Raised when multiple competing FX sources exist for a pair on the effective date."""


class InvalidFxEffectiveDateError(FxResolutionError):
    """Raised when an invalid effective date is provided for FX resolution."""


class InvalidCurrencyCodeError(FxResolutionError):
    """Raised when an invalid currency code is provided for FX resolution."""


@dataclass(frozen=True)
class FxRateResult:
    """
    Resolved single-side FX rate with complete provenance and calculation metadata.
    """
    rate: Decimal
    from_currency: str
    to_currency: str
    base_currency: str
    quote_currency: str
    effective_date: date
    source: str
    tt_side: str  # 'BUY', 'SELL', 'MID', or 'IDENTITY'
    is_inverse: bool = False
    is_cross: bool = False
    is_identity: bool = False
    raw_rate: Optional[Decimal] = None
    cross_details: Optional[dict] = None


@dataclass(frozen=True)
class FxPairResult:
    """
    Resolved full two-sided FX pair (TT BUY, TT SELL, MID) for converting from_currency -> to_currency.
    """
    from_currency: str
    to_currency: str
    tt_buy: Decimal
    tt_sell: Decimal
    mid_rate: Decimal
    effective_date: date
    source: str
    is_inverse: bool = False
    is_cross: bool = False
    is_identity: bool = False
    cross_details: Optional[dict] = None
    stored_base_currency: Optional[str] = None
    stored_quote_currency: Optional[str] = None
    raw_tt_buy: Optional[Decimal] = None
    raw_tt_sell: Optional[Decimal] = None
    raw_mid: Optional[Decimal] = None


def normalize_currency_code(code: str) -> str:
    """Validate and normalize a 3-letter currency code."""
    if not code or not isinstance(code, str):
        raise InvalidCurrencyCodeError(f"Currency code must be a non-empty string, got: {repr(code)}")
    cleaned = code.strip().upper()
    if not CURRENCY_CODE_REGEX.match(cleaned):
        raise InvalidCurrencyCodeError(
            f"Currency code must be exactly 3 uppercase letters [A-Z]{{3}}, got: '{code}'"
        )
    return cleaned


def normalize_effective_date(effective_date: date | datetime | str | None = None) -> date:
    """
    Normalize effective date to date.
    - None: current system date (timezone.now().date()).
    - str: ISO format YYYY-MM-DD.
    - datetime: extracts date component.
    - date: used directly.
    - invalid / unsupported: fails closed with InvalidFxEffectiveDateError.
    """
    if effective_date is None:
        return timezone.now().date()
    if isinstance(effective_date, str):
        cleaned = effective_date.strip()
        if not cleaned:
            raise InvalidFxEffectiveDateError("Empty effective_date string provided.")
        clean_str = cleaned.split("T")[0].split(" ")[0]
        try:
            return date.fromisoformat(clean_str)
        except ValueError as err:
            raise InvalidFxEffectiveDateError(
                f"Invalid effective_date string '{effective_date}': {err}"
            ) from err
    if isinstance(effective_date, datetime):
        return effective_date.date()
    if isinstance(effective_date, date):
        return effective_date
    raise InvalidFxEffectiveDateError(
        f"Unsupported effective_date type: {type(effective_date).__name__}"
    )


def _check_source_ambiguity(
    candidate_qs: QuerySet[FxMarketRate],
    pair_desc: str,
    target_date: date,
    requested_source: str | None,
) -> FxMarketRate:
    """
    If multiple sources exist on the candidate date and no source was requested, fail closed.
    Never use .first() arbitrarily across competing sources.
    """
    if requested_source:
        candidate_qs = candidate_qs.filter(source=requested_source)
        record = candidate_qs.first()
        if not record:
            raise MissingFxMarketRateError(
                f"No authoritative FX market rate found for {pair_desc} from source '{requested_source}' "
                f"on or before {target_date}."
            )
        return record

    sources = list(candidate_qs.values_list("source", flat=True).distinct())
    if len(sources) > 1:
        raise AmbiguousFxSourceError(
            f"Multiple competing FX sources found on {candidate_qs.first().effective_date} for {pair_desc}: "
            f"{sources}. An explicit source must be specified; cannot pick arbitrarily."
        )
    record = candidate_qs.first()
    if not record:
        raise MissingFxMarketRateError(
            f"No authoritative FX market rate found for {pair_desc} on or before {target_date}."
        )
    return record


def resolve_market_fx_pair(
    from_currency: str,
    to_currency: str,
    effective_date: date | datetime | str | None = None,
    source: str | None = None,
) -> FxPairResult:
    """
    Resolve the authoritative two-sided market rate (TT BUY, TT SELL, MID) for converting
    from_currency into to_currency as of effective_date.

    Resolution order:
    1. Identity: from_currency == to_currency -> returns 1.0 (no FX required).
    2. Direct Pair: base_currency = from_currency, quote_currency = to_currency.
    3. Inverse Pair: base_currency = to_currency, quote_currency = from_currency.
       Derived mathematically with side-reversal:
         inverse TT BUY  = 1 / original TT SELL
         inverse TT SELL = 1 / original TT BUY
         inverse MID     = 1 / original MID
    4. Cross-Currency: If neither is PGK, resolves via PGK:
       from_currency -> PGK (BUY leg) then PGK -> to_currency (SELL leg).
    5. Fails closed with MissingFxMarketRateError if unresolved.
    """
    from_curr = normalize_currency_code(from_currency)
    to_curr = normalize_currency_code(to_currency)
    target_date = normalize_effective_date(effective_date)

    # 1. Identity conversion
    if from_curr == to_curr:
        return FxPairResult(
            from_currency=from_curr,
            to_currency=to_curr,
            tt_buy=Decimal("1.0"),
            tt_sell=Decimal("1.0"),
            mid_rate=Decimal("1.0"),
            effective_date=target_date,
            source="IDENTITY",
            is_identity=True,
        )

    # 2. Check Direct Pair in FxMarketRate: base=from_curr, quote=to_curr
    direct_qs = FxMarketRate.objects.filter(
        base_currency=from_curr,
        quote_currency=to_curr,
        effective_date__lte=target_date,
    )
    if source:
        direct_qs = direct_qs.filter(source=source)

    latest_direct_date = direct_qs.order_by("-effective_date").values_list("effective_date", flat=True).first()

    inverse_qs = FxMarketRate.objects.filter(
        base_currency=to_curr,
        quote_currency=from_curr,
        effective_date__lte=target_date,
    )
    if source:
        inverse_qs = inverse_qs.filter(source=source)
    latest_inverse_date = inverse_qs.order_by("-effective_date").values_list("effective_date", flat=True).first()

    if latest_direct_date and latest_inverse_date and latest_direct_date == latest_inverse_date:
        raise AmbiguousFxSourceError(
            f"Both {from_curr}/{to_curr} and {to_curr}/{from_curr} market facts exist on "
            f"{latest_direct_date}; orientation priority is not defined."
        )

    if latest_direct_date and (not latest_inverse_date or latest_direct_date > latest_inverse_date):
        candidates = direct_qs.filter(effective_date=latest_direct_date)
        record = _check_source_ambiguity(
            candidates, f"{from_curr}/{to_curr}", target_date, source
        )
        return FxPairResult(
            from_currency=from_curr,
            to_currency=to_curr,
            tt_buy=record.tt_buy_rate,
            tt_sell=record.tt_sell_rate,
            mid_rate=record.mid_rate,
            effective_date=record.effective_date,
            source=record.source,
            is_inverse=False,
            stored_base_currency=record.base_currency,
            stored_quote_currency=record.quote_currency,
            raw_tt_buy=record.tt_buy_rate,
            raw_tt_sell=record.tt_sell_rate,
            raw_mid=record.mid_rate,
        )

    # 3. Check Inverse Pair in FxMarketRate: base=to_curr, quote=from_curr
    if latest_inverse_date:
        candidates = inverse_qs.filter(effective_date=latest_inverse_date)
        record = _check_source_ambiguity(
            candidates, f"{to_curr}/{from_curr}", target_date, source
        )
        # Inversion rule:
        # inverse TT BUY  = 1 / original TT SELL
        # inverse TT SELL = 1 / original TT BUY
        # inverse MID     = 1 / original MID
        inv_tt_buy = (Decimal("1") / record.tt_sell_rate).quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)
        inv_tt_sell = (Decimal("1") / record.tt_buy_rate).quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)
        inv_mid = (Decimal("1") / record.mid_rate).quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)
        return FxPairResult(
            from_currency=from_curr,
            to_currency=to_curr,
            tt_buy=inv_tt_buy,
            tt_sell=inv_tt_sell,
            mid_rate=inv_mid,
            effective_date=record.effective_date,
            source=record.source,
            is_inverse=True,
            stored_base_currency=record.base_currency,
            stored_quote_currency=record.quote_currency,
            raw_tt_buy=record.tt_buy_rate,
            raw_tt_sell=record.tt_sell_rate,
            raw_mid=record.mid_rate,
        )

    # 4. Cross-Currency Resolution via PGK (when neither is PGK)
    if from_curr != "PGK" and to_curr != "PGK":
        # Leg 1: from_curr -> PGK
        leg1 = resolve_market_fx_pair(from_curr, "PGK", target_date, source)
        # Leg 2: PGK -> to_curr
        leg2 = resolve_market_fx_pair("PGK", to_curr, target_date, source)

        # Cross rates: multiply conversion factors
        cross_tt_buy = (leg1.tt_buy * leg2.tt_buy).quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)
        cross_tt_sell = (leg1.tt_sell * leg2.tt_sell).quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)
        cross_mid = (leg1.mid_rate * leg2.mid_rate).quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)
        resolved_date = min(leg1.effective_date, leg2.effective_date)
        resolved_source = f"{leg1.source}:{leg2.source}" if leg1.source != leg2.source else leg1.source

        return FxPairResult(
            from_currency=from_curr,
            to_currency=to_curr,
            tt_buy=cross_tt_buy,
            tt_sell=cross_tt_sell,
            mid_rate=cross_mid,
            effective_date=resolved_date,
            source=resolved_source,
            is_cross=True,
            cross_details={
                "leg1": {
                    "pair": f"{from_curr}/PGK",
                    "tt_buy": str(leg1.tt_buy),
                    "tt_sell": str(leg1.tt_sell),
                    "effective_date": leg1.effective_date.isoformat(),
                    "source": leg1.source,
                    "stored_pair": f"{leg1.stored_base_currency}/{leg1.stored_quote_currency}",
                    "raw_tt_buy": str(leg1.raw_tt_buy),
                    "raw_tt_sell": str(leg1.raw_tt_sell),
                },
                "leg2": {
                    "pair": f"PGK/{to_curr}",
                    "tt_buy": str(leg2.tt_buy),
                    "tt_sell": str(leg2.tt_sell),
                    "effective_date": leg2.effective_date.isoformat(),
                    "source": leg2.source,
                    "stored_pair": f"{leg2.stored_base_currency}/{leg2.stored_quote_currency}",
                    "raw_tt_buy": str(leg2.raw_tt_buy),
                    "raw_tt_sell": str(leg2.raw_tt_sell),
                },
            },
        )

    # 5. Fails closed
    raise MissingFxMarketRateError(
        f"No authoritative FX market rate found for {from_curr}->{to_curr} "
        f"on or before {target_date}."
    )


def resolve_market_fx_rate(
    from_currency: str,
    to_currency: str,
    tt_side: str,
    effective_date: date | datetime | str | None = None,
    source: str | None = None,
) -> FxRateResult:
    """
    Resolve a specific single-side market rate ('BUY', 'SELL', or 'MID') for converting
    from_currency into to_currency as of effective_date.
    """
    side_normalized = tt_side.strip().upper()
    if side_normalized not in {"BUY", "SELL", "MID"}:
        raise FxResolutionError(f"Invalid tt_side '{tt_side}'. Must be 'BUY', 'SELL', or 'MID'.")

    pair_result = resolve_market_fx_pair(
        from_currency=from_currency,
        to_currency=to_currency,
        effective_date=effective_date,
        source=source,
    )

    if pair_result.is_identity:
        return FxRateResult(
            rate=Decimal("1.0"),
            from_currency=pair_result.from_currency,
            to_currency=pair_result.to_currency,
            base_currency=pair_result.from_currency,
            quote_currency=pair_result.to_currency,
            effective_date=pair_result.effective_date,
            source=pair_result.source,
            tt_side="IDENTITY",
            is_identity=True,
            raw_rate=Decimal("1.0"),
        )

    if side_normalized == "BUY":
        selected_rate = pair_result.tt_buy
    elif side_normalized == "SELL":
        selected_rate = pair_result.tt_sell
    else:
        selected_rate = pair_result.mid_rate

    return FxRateResult(
        rate=selected_rate,
        from_currency=pair_result.from_currency,
        to_currency=pair_result.to_currency,
        base_currency=pair_result.stored_base_currency or pair_result.from_currency,
        quote_currency=pair_result.stored_quote_currency or pair_result.to_currency,
        effective_date=pair_result.effective_date,
        source=pair_result.source,
        tt_side=side_normalized,
        is_inverse=pair_result.is_inverse,
        is_cross=pair_result.is_cross,
        raw_rate=(
            None if pair_result.is_cross else
            pair_result.raw_mid if side_normalized == "MID" else
            pair_result.raw_tt_sell if (side_normalized == "BUY") == pair_result.is_inverse else
            pair_result.raw_tt_buy
        ),
        cross_details=pair_result.cross_details,
    )
