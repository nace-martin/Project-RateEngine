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
