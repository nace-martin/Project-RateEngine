from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

@dataclass
class Piece:
    weight_kg: float
    length_cm: Optional[float] = None
    width_cm: Optional[float] = None
    height_cm: Optional[float] = None

@dataclass
class QuoteContext:
    mode: str  # "AIR"
    origin_iata: str
    dest_iata: str
    scope: str  # A2A|A2D|D2A|D2D
    payment_term: str  # PREPAID|COLLECT
    pieces: List[Piece]
    commodity: str = "GCR"
    incoterm: Optional[str] = None
    hints: Dict[str, Any] = field(default_factory=dict)

@dataclass
class NormalizedContext:
    direction: str                 # IMPORT|EXPORT|DOMESTIC
    audience: str                  # e.g., PNG_CUSTOMER_PREPAID
    invoice_ccy: str               # PGK|ORIGIN_CCY|DEST_CCY
    segments: List[str]            # ["ORIGIN","PRIMARY","DEST"]
    legs: List[Dict[str, Any]]     # [{origin:"BNE", dest:"POM", type:"INTL"}, ...]
    chargeable_kg: float
    gst_segment: str = "DEST"
    snapshot: Dict[str, Any] = field(default_factory=dict)

@dataclass
class BuyComponent:
    code: str
    segment: str
    basis: str            # PER_KG|PER_SHIPMENT|PERCENT_OF
    unit_qty: float
    native_amount: float
    native_ccy: str
    meta: Dict[str, Any] = field(default_factory=dict)

@dataclass
class BuyResult:
    components: List[BuyComponent]
    manual: bool = False
    reasons: List[str] = field(default_factory=list)

@dataclass
class SellLine:
    sell_code: str
    segment: str
    basis: str
    unit_qty: float
    amount: float
    ccy: str
    meta: Dict[str, Any] = field(default_factory=dict)

@dataclass
class SellResult:
    lines: List[SellLine]
    manual: bool = False
    reasons: List[str] = field(default_factory=list)

@dataclass
class Totals:
    buy_pgk: float
    tax: float
    final_sell: float
    client_ccy: str
