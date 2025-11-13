# backend/pricing_v2/dataclasses_v3.py

"""
Dataclasses for the V3 Pricing Service.

These objects are used internally by the PricingServiceV3 to hold structured
data during a calculation, separating it from the Django models.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import List, Optional, Dict, Any
import uuid

# --- Core Shipment & Quote Inputs ---

@dataclass(frozen=True)
class Piece:
    """Represents a single piece line item (e.g., 10 pieces @ 50x50x50cm)."""
    pieces: int
    length_cm: Decimal
    width_cm: Decimal
    height_cm: Decimal
    gross_weight_kg: Decimal

@dataclass(frozen=True)
class ShipmentDetails:
    """Holds all physical and routing details of the shipment."""
    mode: str                  # e.g., 'AIR'
    shipment_type: str         # e.g., 'IMPORT', 'EXPORT'
    origin_code: str           # Airport/Port code (e.g., 'BNE')
    destination_code: str      # Airport/Port code (e.g., 'POM')
    incoterm: str              # e.g., 'EXW'
    payment_term: str          # e.g., 'PREPAID'
    is_dangerous_goods: bool
    pieces: List[Piece]

@dataclass(frozen=True)
class ManualOverride:
    """Represents a manually provided cost (e.g., a spot rate)."""
    service_component_id: uuid.UUID
    cost_fcy: Decimal
    currency: str
    unit: str
    min_charge_fcy: Optional[Decimal] = None

@dataclass(frozen=True)
class QuoteInput:
    """
    The main input dataclass passed to PricingServiceV3 to start a calculation.
    """
    customer_id: uuid.UUID
    contact_id: uuid.UUID
    output_currency: str
    shipment: ShipmentDetails
    overrides: List[ManualOverride] = field(default_factory=list)

# --- Calculation & Output Dataclasses ---

@dataclass
class CalculatedChargeLine:
    """
    The result for a single line item, containing all cost, sell, and audit data.
    (Fields reordered to place non-defaults first)
    """
    # --- Fields WITHOUT default values ---
    service_component_id: uuid.UUID
    service_component_code: str
    service_component_desc: str
    cost_pgk: Decimal
    sell_pgk: Decimal
    sell_pgk_incl_gst: Decimal
    sell_fcy: Decimal
    sell_fcy_incl_gst: Decimal
    cost_source: str
    
    # --- Fields WITH default values ---
    cost_fcy: Optional[Decimal] = None
    cost_fcy_currency: Optional[str] = None
    sell_fcy_currency: Optional[str] = None
    exchange_rate: Optional[Decimal] = None
    cost_source_description: Optional[str] = None
    is_rate_missing: bool = False

@dataclass
class CalculatedTotals:
    """The final, summed totals for the quote."""
    total_cost_pgk: Decimal = Decimal("0.0")
    
    total_sell_pgk: Decimal = Decimal("0.0")
    total_sell_pgk_incl_gst: Decimal = Decimal("0.0")
    
    total_sell_fcy: Decimal = Decimal("0.0")
    total_sell_fcy_incl_gst: Decimal = Decimal("0.0")
    total_sell_fcy_currency: str = "PGK"
    
    has_missing_rates: bool = False
    notes: Optional[str] = None

@dataclass
class QuoteCharges:
    """The complete set of results from a calculation."""
    lines: List[CalculatedChargeLine]
    totals: CalculatedTotals