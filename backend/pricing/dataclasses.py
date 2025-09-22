from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, List, Optional

from .services.utils import ZERO


@dataclass
class Piece:
    weight_kg: Decimal
    length_cm: Optional[Decimal] = None
    width_cm: Optional[Decimal] = None
    height_cm: Optional[Decimal] = None

    def volume_m3(self) -> Decimal:
        if self.length_cm is None or self.width_cm is None or self.height_cm is None:
            return ZERO
        return (self.length_cm * self.width_cm * self.height_cm) / Decimal(1_000_000)


@dataclass
class ShipmentInput:
    org_id: int
    origin_iata: str
    dest_iata: str
    service_scope: str
    payment_term: str = "PREPAID"
    shipment_type: Optional[str] = None
    incoterm: Optional[str] = None
    commodity_code: str = "GCR"
    is_urgent: bool = False
    airline_hint: Optional[str] = None
    via_hint: Optional[str] = None
    pieces: List[Piece] = field(default_factory=list)
    flags: Dict[str, bool] = field(default_factory=dict)
    duties_value_sell_ccy: Decimal = ZERO
    pallets: int = 0

    @property
    def actual_weight(self) -> Decimal:
        return sum((p.weight_kg for p in self.pieces), ZERO)

    @property
    def volume_m3(self) -> Decimal:
        return sum((p.volume_m3() for p in self.pieces), ZERO)


@dataclass
class Money:
    amount: Decimal
    currency: str


@dataclass
class CalcLine:
    code: str
    description: str
    qty: Decimal
    unit: str
    unit_price: Money
    extended: Money
    is_buy: bool
    is_sell: bool
    tax_pct: Decimal = ZERO
    source_ratecard_id: Optional[int] = None
    meta: Dict = field(default_factory=dict)


@dataclass
class CalcResult:
    buy_lines: List[CalcLine]
    sell_lines: List[CalcLine]
    totals: Dict[str, Money]
    snapshot: Dict


@dataclass
class PricingContext:
    """Context determined by business rules for pricing calculations"""
    currency: str
    charge_scope: List[str]  # e.g., ["ORIGIN", "AIR_FREIGHT", "DESTINATION"]
    applicable_services: List[str]  # Specific service codes to include
    requires_manual_review: bool = False
    rule_path: str = ""  # e.g., "IMPORT.COLLECT.D2D"
    description: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)