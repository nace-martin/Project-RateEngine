from dataclasses import dataclass
from enum import Enum

@dataclass(frozen=True)
class Currency:
    code: str
    name: str

@dataclass(frozen=True)
class Unit:
    code: str
    label: str

class AudienceId(int, Enum):
    # This will be populated from the database or a predefined list
    # For now, we can add some placeholders or leave it to be dynamically populated
    # Example:
    # RETAIL = 1
    # WHOLESALE = 2
    pass