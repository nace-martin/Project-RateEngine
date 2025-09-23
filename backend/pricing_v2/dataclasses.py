from dataclasses import dataclass
from typing import Callable, List, Dict

@dataclass
class Rule:
    name: str
    condition: Callable
    action: Callable

@dataclass
class Policy:
    name: str
    rules: List[Rule]

@dataclass
class Recipe:
    name: str
    action: Callable

@dataclass
class Snapshot:
    policy_name: str
    recipe_executions: List[Dict]
