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
    """
    key = (name or "bsp_html").strip().lower()
    if key in {"bsp", "bsp_html", "bank_bsp"}:
        from .bsp_html import BspHtmlProvider  # local import to avoid circulars
        return BspHtmlProvider()
    raise ValueError(f"Unknown FX provider: {name}")

