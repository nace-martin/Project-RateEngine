# backend/core/fx.py
"""
FX utility functions for rate management.

Provides:
- EnvProvider: Environment variable-based FX rate provider
- compute_tt_buy_sell: Calculate TT Buy/Sell from mid rate
- upsert_rate: Upsert currency rate to database
- d: Decimal conversion helper
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from django.utils import timezone as django_tz


def d(val) -> Decimal:
    """Convert value to Decimal."""
    if isinstance(val, Decimal):
        return val
    return Decimal(str(val))


class FxUnavailableError(Exception):
    """Raised when FX rates cannot be retrieved from any source (primary or fallback)."""
    pass


@dataclass
class MidRateResult:
    """Result from a mid rate lookup."""
    rate: Decimal
    as_of: datetime


class EnvProvider:
    """
    FX rate provider that reads rates from environment variables.
    Used as fallback when BSP scraper fails.
    
    Environment variables:
    - FX_{BASE}_{QUOTE}_MID: e.g., FX_USD_PGK_MID=3.85
    """
    
    def get_mid_rate(self, base: str, quote: str) -> MidRateResult:
        """Get mid rate from environment variable."""
        env_key = f"FX_{base.upper()}_{quote.upper()}_MID"
        rate_str = os.environ.get(env_key)
        
        if not rate_str:
            raise ValueError(f"Environment variable {env_key} not set")
        
        return MidRateResult(
            rate=d(rate_str),
            as_of=datetime.now(timezone.utc)
        )


def compute_tt_buy_sell(
    mid_rate: Decimal,
    spread_bps: int = 100
) -> tuple[Decimal, Decimal]:
    """
    Calculate TT Buy and TT Sell rates from a mid rate.
    
    Args:
        mid_rate: The mid-market rate
        spread_bps: Spread in basis points (e.g., 100 = 1%)
    
    Returns:
        Tuple of (tt_buy, tt_sell)
    """
    spread_pct = Decimal(spread_bps) / Decimal("10000")
    half_spread = spread_pct / 2
    
    tt_buy = mid_rate * (1 - half_spread)
    tt_sell = mid_rate * (1 + half_spread)
    
    # Round to 4 decimal places
    tt_buy = tt_buy.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    tt_sell = tt_sell.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    
    return tt_buy, tt_sell


def upsert_rate(
    as_of: datetime,
    base_ccy: str,
    quote_ccy: str,
    rate: Decimal,
    rate_type: str,
    source: str
) -> None:
    """
    Insert or update a currency rate in the database.
    
    This function updates FxSnapshot for the current snapshot
    and also updates/creates individual CurrencyRates records.
    """
    from core.models import FxSnapshot, Currency
    
    # Ensure we have Currency objects
    base_currency, _ = Currency.objects.get_or_create(
        code=base_ccy.upper(),
        defaults={'name': base_ccy.upper(), 'minor_units': 2}
    )
    quote_currency, _ = Currency.objects.get_or_create(
        code=quote_ccy.upper(),
        defaults={'name': quote_ccy.upper(), 'minor_units': 2}
    )
    
    # Get or create the latest snapshot for today
    today_start = django_tz.now().replace(hour=0, minute=0, second=0, microsecond=0)
    
    snapshot = FxSnapshot.objects.filter(
        source=source,
        as_of_timestamp__gte=today_start
    ).order_by('-as_of_timestamp').first()
    
    if not snapshot:
        # Create new snapshot
        snapshot = FxSnapshot.objects.create(
            as_of_timestamp=as_of,
            source=source,
            rates={},
            caf_percent=Decimal("0.0"),
            fx_buffer_percent=Decimal("0.0"),
        )
    
    # Update the rates JSON
    rates = snapshot.rates or {}
    
    # Determine the remote currency code for the dictionary key (e.g. 'USD')
    if base_ccy.upper() == 'PGK':
        curr_key = quote_ccy.upper()
    elif quote_ccy.upper() == 'PGK':
        curr_key = base_ccy.upper()
    else:
        # Fallback for cross-rates
        curr_key = f"{base_ccy.upper()}/{quote_ccy.upper()}"
        
    if curr_key not in rates:
        rates[curr_key] = {}
    
    if rate_type == 'BUY':
        rates[curr_key]['tt_buy'] = str(rate)
    elif rate_type == 'SELL':
        rates[curr_key]['tt_sell'] = str(rate)
    
    snapshot.rates = rates
    snapshot.as_of_timestamp = as_of
    snapshot.save()
