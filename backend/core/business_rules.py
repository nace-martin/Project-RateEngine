from __future__ import annotations

PNG_COUNTRY_CODE = "PG"

def is_png_country(country_code: str | None) -> bool:
    """Check if the provided country code represents Papua New Guinea."""
    if not country_code:
        return False
    return country_code.strip().upper() == PNG_COUNTRY_CODE


def classify_png_shipment(origin_country_code: str | None, destination_country_code: str | None) -> str:
    """
    Authoritative classification matrix for RateEngine shipments.
    
    Rules:
      - PG -> PG = DOMESTIC
      - PG -> non-PG = EXPORT
      - non-PG -> PG = IMPORT
      - non-PG -> non-PG = unsupported (raises ValueError)
    
    Fails clearly and loudly if any required parameters are missing or invalid.
    """
    org = (origin_country_code or "").strip().upper()
    dest = (destination_country_code or "").strip().upper()

    if not org or not dest:
        raise ValueError("Missing country data: Both origin and destination country codes are required.")

    org_is_pg = org == PNG_COUNTRY_CODE
    dest_is_pg = dest == PNG_COUNTRY_CODE

    if org_is_pg and dest_is_pg:
        return "DOMESTIC"
    if org_is_pg:
        return "EXPORT"
    if dest_is_pg:
        return "IMPORT"

    raise ValueError(
        f"Out of scope: RateEngine only supports routes to or from PNG ({PNG_COUNTRY_CODE}). "
        f"Received lane: {org} -> {dest}."
    )
