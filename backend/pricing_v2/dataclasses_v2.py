from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Callable


@dataclass
class Recipe:
    name: str
    action: Callable


@dataclass
class QuoteContext:
    mode: str
    direction: str
    scope: str
    payment_term: str
    origin_iata: str
    dest_iata: str
    pieces: List[Dict[str, Any]]
    commodity: str
    margins: Dict[str, Any]
    policy: Dict[str, Any]
    origin_country_currency: str
    destination_country_currency: str
    audience: Optional[str] = None  # Optional, can be derived


@dataclass
class NormalizedContext:
    audience: str
    invoice_ccy: str
    origin_iata: str
    # Add other normalized fields as needed


@dataclass
class CalcLine:
    code: str
    description: str
    amount: float
    currency: str
    # Add other fields relevant to a calculation line


@dataclass
class BuyResult:
    buy_lines: List[CalcLine] = field(default_factory=list)
    buy_total_pgk: float = 0.0
    is_incomplete: bool = False
    reasons: List[str] = field(default_factory=list)
    # Add other fields relevant to buy results


@dataclass
class Totals:
    invoice_ccy: str
    sell_subtotal: float = 0.0
    sell_tax: float = 0.0
    sell_total: float = 0.0
    buy_total_pgk: float = 0.0
    is_incomplete: bool = False
    reasons: List[str] = field(default_factory=list)
    sell_lines: List[CalcLine] = field(default_factory=list)  # NEW


@dataclass
class Snapshot:
    policy_key: str = ""
    policy_version: str = "v1"
    golden_inputs: Dict[str, Any] = field(default_factory=dict)
    chosen_breaks_fees: List[str] = field(default_factory=list)
    caf_fx_pairs: List[str] = field(default_factory=list)
    rounding_notes: List[str] = field(default_factory=list)
    skipped_fees: List[Dict[str, Any]] = field(default_factory=list)
    # Add other fields to record policy decisions, skipped fees, and reasons


@dataclass
class SellResult:
    sell_lines: List[CalcLine] = field(default_factory=list)
    sell_subtotal: float = 0.0
    sell_tax: float = 0.0
    sell_total: float = 0.0
    snapshot: Snapshot = field(default_factory=Snapshot)
    buy_total_pgk: float = 0.0
    is_incomplete: bool = False
    reasons: List[str] = field(default_factory=list)
    # Add other fields relevant to sell results


@dataclass
class CalcResultV2:
    # Represents the detailed result of a V2 calculation
    pass
