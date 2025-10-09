from dataclasses import dataclass, field
from typing import List, Optional, Dict
from pricing_v2.types_v2 import ProvenanceType, FeeBasis, Side

@dataclass
class Provenance:
    type: ProvenanceType
    ref: Optional[str] = None
    raw_blob_hash: Optional[str] = None

@dataclass
class BuyFee:
    code: str
    basis: FeeBasis
    rate: float
    minimum: float = 0.0
    depends_on: Optional[str] = None
    side: Optional[Side] = None

@dataclass
class BuyBreak:
    from_kg: float
    rate_per_kg: float

@dataclass
class BuyLane:
    origin: str
    dest: str
    carrier: Optional[str] = None
    min_charge: float = 0.0

@dataclass
class BuyOffer:
    lane: BuyLane
    ccy: str
    breaks: List[BuyBreak] = field(default_factory=list)
    fees: List[BuyFee] = field(default_factory=list)
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None
    provenance: Optional[Provenance] = None
    notes: Optional[str] = None

@dataclass
class BuyMenu:
    offers: List[BuyOffer] = field(default_factory=list)

@dataclass
class QuoteContext:
    mode: str = "AIR"
    scope: str = "A2A"
    payment_term: str = "COLLECT"
    origin_iata: str = ""
    dest_iata: str = ""
    pieces: List[Dict] = field(default_factory=list)
    commodity: str = "GCR"
    payer: Optional[Dict] = None
    spot_offers: List[Dict] = field(default_factory=list)
