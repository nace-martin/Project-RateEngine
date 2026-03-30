from typing import Optional

# Categories that represent local origin/destination tariffs and must not be stored per lane.
LOCAL_RATE_CATEGORIES = frozenset(
    {
        "CLEARANCE",
        "CARTAGE",
        "HANDLING",
        "DOCUMENTATION",
        "SCREENING",
        "AGENCY",
        "SURCHARGE",
    }
)


def is_local_rate_category(category: Optional[str]) -> bool:
    return (category or "").upper() in LOCAL_RATE_CATEGORIES


def is_export_destination_local_code(
    code: Optional[str],
    description: Optional[str] = None,
) -> bool:
    """
    Export destination-local ProductCodes are stored centrally, but they belong
    to the overseas destination station rather than the PNG origin station.

    Current launch codes consistently include ``DEST`` in the code and
    "Destination" in the human-readable label.
    """
    normalized_code = (code or "").upper()
    normalized_description = (description or "").upper()
    return "DEST" in normalized_code or "DESTINATION" in normalized_description


def resolve_export_local_location(
    *,
    code: Optional[str],
    description: Optional[str] = None,
    origin_airport: str,
    destination_airport: str,
) -> str:
    if is_export_destination_local_code(code, description):
        return destination_airport
    return origin_airport
