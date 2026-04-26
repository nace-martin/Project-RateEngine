from typing import Optional

# Categories that represent local origin/destination tariffs and must not be stored per lane.
LOCAL_RATE_CATEGORIES = frozenset(
    {
        "CLEARANCE",
        "CARTAGE",
        "HANDLING",
        "DOCUMENTATION",
        "REGULATORY",
        "SCREENING",
        "AGENCY",
        "SURCHARGE",
    }
)

IMPORT_ORIGIN_LOCAL_CODES = frozenset(
    {
        "IMP-CUS-CLR",
        "IMP-CUS-CLR-ORIGIN",
        "IMP-PICKUP",
        "IMP-FSC-PICKUP",
    }
)

IMPORT_DESTINATION_LOCAL_CODES = frozenset(
    {
        "IMP-CLEAR",
        "IMP-CARTAGE-DEST",
        "IMP-FSC-CARTAGE-DEST",
    }
)

EXPORT_DESTINATION_LOCAL_CODES = frozenset(
    {
        "EXP-CLEAR-DEST",
        "EXP-DELIVERY-DEST",
    }
)


def is_local_rate_category(category: Optional[str]) -> bool:
    return (category or "").upper() in LOCAL_RATE_CATEGORIES


def is_import_origin_local_code(code: Optional[str], description: Optional[str] = None) -> bool:
    normalized_code = (code or "").upper()
    normalized_description = (description or "").upper()
    return (
        normalized_code in IMPORT_ORIGIN_LOCAL_CODES
        or "ORIGIN" in normalized_code
        or "(ORIGIN" in normalized_description
        or " ORIGIN" in normalized_description
        or "PICK-UP" in normalized_description
        or "PICK UP" in normalized_description
    )


def is_import_destination_local_code(code: Optional[str], description: Optional[str] = None) -> bool:
    normalized_code = (code or "").upper()
    normalized_description = (description or "").upper()
    return (
        normalized_code in IMPORT_DESTINATION_LOCAL_CODES
        or "DEST" in normalized_code
        or "(DEST" in normalized_description
        or " DEST" in normalized_description
        or "DESTINATION" in normalized_description
    )


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
    return (
        normalized_code in EXPORT_DESTINATION_LOCAL_CODES
        or "DEST" in normalized_code
        or "DESTINATION" in normalized_description
    )


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
