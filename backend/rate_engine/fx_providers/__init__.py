from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional


@dataclass
class RateRow:
    as_of_ts: datetime
    base_ccy: str
    quote_ccy: str
    rate: Decimal
    rate_type: str  # 'BUY' or 'SELL'
    source: str


def load(name: Optional[str]):
    """
    Lazy-load an FX provider by name.
    - 'bsp', 'bsp_html', 'bank_bsp' -> BspHtmlProvider
    - 'env', 'env_provider', None -> EnvProvider (from rate_engine.fx)
    """
    key = (name or "env").strip().lower()
    if key in {"bsp", "bsp_html", "bank_bsp"}:
        from .bsp_html import BspHtmlProvider  # local import to avoid circulars
        return BspHtmlProvider()
    if key in {"env", "env_provider"}:
        from rate_engine.fx import EnvProvider  # type: ignore
        return EnvProvider()
    # Default to env if unknown
    from rate_engine.fx import EnvProvider  # type: ignore
    return EnvProvider()

