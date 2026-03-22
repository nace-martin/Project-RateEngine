from typing import Optional


def determine_quote_currency(
    shipment_type: Optional[str],
    payment_term: Optional[str],
    origin_country_code: Optional[str],
    destination_country_code: Optional[str],
) -> str:
    """
    Resolve quote output currency using global business rules.

    EXPORT:
    - PREPAID => PGK
    - COLLECT to AU => AUD
    - COLLECT non-AU => USD

    IMPORT:
    - Collect => PGK
    - Prepaid from AU => AUD
    - Prepaid non-AU => USD

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
        return "AUD" if origin == "AU" else "USD"

    if shipment == "EXPORT":
        if term == "PREPAID":
            return "PGK"
        return "AUD" if destination == "AU" else "USD"

    return "PGK"
