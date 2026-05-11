from __future__ import annotations

from decimal import Decimal


BUCKET_TO_LEG = {
    "origin_charges": "ORIGIN",
    "airfreight": "MAIN",
    "destination_charges": "DESTINATION",
}


def normalize_bucket(raw_bucket) -> str | None:
    value = str(raw_bucket or "").strip().lower()
    return BUCKET_TO_LEG.get(value)


def normalize_leg(raw_leg) -> str | None:
    value = str(raw_leg or "").strip().upper()
    if value in {"ORIGIN", "DESTINATION"}:
        return value
    if value in {"MAIN", "FREIGHT"}:
        return "MAIN"
    return None


def resolve_quote_line_leg(line) -> str:
    """
    Resolve the persisted quote-line leg.

    QuoteLine.bucket/leg is authoritative. ServiceComponent metadata is not,
    because it can be resynced independently of saved quote results.
    """
    return normalize_bucket(getattr(line, "bucket", None)) or normalize_leg(getattr(line, "leg", None)) or "MAIN"


def resolve_quote_line_sell_value(line, quote_currency: str) -> Decimal:
    """Return the customer-facing sell amount for the quote output currency."""
    currency = str(quote_currency or "PGK").upper()
    if currency != "PGK":
        line_currency = str(getattr(line, "sell_fcy_currency", "") or "").upper()
        if line_currency == currency and getattr(line, "sell_fcy", None) is not None:
            return line.sell_fcy
    return getattr(line, "sell_pgk", None) or Decimal("0")


def should_display_quote_line(line, quote_currency: str) -> bool:
    """Return whether a line should appear in the customer/public breakdown."""
    if getattr(line, "is_informational", False):
        return False
    if getattr(line, "conditional", False):
        return False
    if getattr(line, "is_rate_missing", False):
        return False
    return resolve_quote_line_sell_value(line, quote_currency) > Decimal("0")


def should_include_quote_line_in_subtotal(line, quote_currency: str) -> bool:
    """Return whether a line contributes to customer-facing subtotals/totals."""
    if getattr(line, "is_informational", False):
        return False
    if getattr(line, "conditional", False):
        return False
    if getattr(line, "is_rate_missing", False):
        return False
    return resolve_quote_line_sell_value(line, quote_currency) > Decimal("0")
