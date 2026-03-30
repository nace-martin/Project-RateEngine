from string import ascii_uppercase

from core.models import Location


def create_location(**kwargs) -> Location:
    location = Location(**kwargs)
    location.full_clean()
    location.save()
    return location


def indexed_iata_code(index: int, prefix: str = "A") -> str:
    if index < 0 or index >= 26 * 26:
        raise ValueError("index must be between 0 and 675 inclusive")

    normalized_prefix = str(prefix or "").strip().upper()
    if len(normalized_prefix) != 1 or not normalized_prefix.isalpha():
        raise ValueError("prefix must be a single alphabetic character")

    return f"{normalized_prefix}{ascii_uppercase[index // 26]}{ascii_uppercase[index % 26]}"
