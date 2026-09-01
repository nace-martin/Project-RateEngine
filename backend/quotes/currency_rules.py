from typing import Optional


PARTNER_QUOTE_CURRENCY_BY_COUNTRY = {
    "AU": "AUD",
    "NZ": "AUD",
    "SB": "PGK",
    "FJ": "PGK",
}


def _partner_quote_currency(country_code: str) -> str:
    """Return the agreed customer quote currency for a foreign partner country."""
    return PARTNER_QUOTE_CURRENCY_BY_COUNTRY.get(country_code, "USD")


def determine_quote_currency(
    shipment_type: Optional[str],
    payment_term: Optional[str],
    origin_country_code: Optional[str],
    destination_country_code: Optional[str],
) -> str:
    """
    Resolve quote output currency using global business rules.

    EXPORT:
    - Prepaid => PGK
    - Collect to AU/NZ => AUD
    - Collect to SB/FJ => PGK
    - Collect to other countries => USD

    IMPORT:
    - Collect => PGK
    - Prepaid from AU/NZ => AUD
    - Prepaid from SB/FJ => PGK
    - Prepaid from other countries => USD

    DOMESTIC:
    - Always PGK
    """
    shipment = (shipment_type or "").upper()
    term = (payment_term or "").upper()
    origin = (origin_country_code or "").upper()
    destination = (destination_country_code or "").upper()

    if shipment == "IMPORT":
        if term == "COLLECT":
            return "PGK"
        return _partner_quote_currency(origin)

    if shipment == "EXPORT":
        if term == "PREPAID":
            return "PGK"
        return _partner_quote_currency(destination)

    return "PGK"
