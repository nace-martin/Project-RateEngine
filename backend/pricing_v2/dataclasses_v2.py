# backend/pricing_v2/dataclasses_v2.py

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import List, Optional, Dict, Any

from core.models import Policy, FxSnapshot
from parties.models import Company

from .types_v2 import FeeBasis, Payer, PaymentTerm, ProvenanceType, Scope, Side


@dataclass
class QuoteRequest:
    """
    A structured data object representing a validated and enriched quote request,
    ready for use by the pricing service.
    """
    scenario: str
    policy: Policy
    fx_snapshot: FxSnapshot
    bill_to: Company
    shipper: Company
    consignee: Company
    chargeable_kg: Decimal
    buy_lines: List[Dict[str, Any]]
    origin_code: Optional[str] = None
    destination_code: Optional[str] = None
    agent_dest_lines_aud: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class QuoteContext:
    """The input payload for a v2 pricing request."""
    # customer_id will link the quote to a customer in the address book
    customer_id: Optional[int] = None
    origin_iata: str = "BNE"
    dest_iata: str = "POM"
    pieces: List[Dict[str, Any]] = field(default_factory=list)
    scope: Scope = Scope.IMPORT_A2D
    payer: Payer = Payer.PNG_CUSTOMER
    payment_term: PaymentTerm = PaymentTerm.PREPAID
    spot_offers: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class BuyLane:
    """Represents the lane for a BUY offer."""
    origin: str
    dest: str
    min_charge: Decimal = Decimal("0.00")


@dataclass
class BuyBreak:
    """Represents a single weight break in a BUY offer."""
    from_kg: Decimal
    rate_per_kg: Decimal
    total: Optional[Decimal] = None


@dataclass
class BuyFee:
    """Represents a single fee in a BUY offer."""
    code: str
    basis: FeeBasis
    rate: Decimal
    minimum: Decimal = Decimal("0.00")
    maximum: Decimal = Decimal("0.00")
    side: Side = Side.UNSPECIFIED


@dataclass
class Provenance:
    """Represents the source of a BUY offer."""
    type: ProvenanceType
    ref: str


@dataclass
class BuyOffer:
    """Represents a single, complete BUY offer from an adapter."""
    lane: BuyLane
    ccy: str
    breaks: List[BuyBreak] = field(default_factory=list)
    fees: List[BuyFee] = field(default_factory=list)
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None
    provenance: Optional[Provenance] = None


@dataclass
class BuyMenu:
    """Represents a collection of BUY offers."""
    offers: List[BuyOffer]
