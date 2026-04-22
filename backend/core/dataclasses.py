# backend/core/dataclasses.py

"""
Dataclasses (Pydantic Models) for the V3 Pricing Service.

These objects are used internally by the PricingServiceV3 to hold structured
data during a calculation, separating it from the Django models.
"""

from decimal import Decimal
from typing import List, Optional, Dict, Any
import uuid
from pydantic import BaseModel, Field, ConfigDict

from core.commodity import DEFAULT_COMMODITY_CODE

# --- Core Shipment & Quote Inputs ---

class LocationRef(BaseModel):
    """Normalized location reference passed into the pricing service."""
    model_config = ConfigDict(frozen=True, from_attributes=True)
    
    id: uuid.UUID
    code: Optional[str]
    name: str
    country_code: Optional[str]
    currency_code: Optional[str] = None

class Piece(BaseModel):
    """Represents a single piece line item (e.g., 10 pieces @ 50x50x50cm)."""
    model_config = ConfigDict(frozen=True, from_attributes=True)

    pieces: int
    length_cm: Decimal
    width_cm: Decimal
    height_cm: Decimal
    gross_weight_kg: Decimal
    package_type: str = "Box"

class ShipmentDetails(BaseModel):
    """Holds all physical and routing details of the shipment."""
    model_config = ConfigDict(frozen=True, from_attributes=True)

    mode: str                  # e.g., 'AIR'
    shipment_type: str         # e.g., 'IMPORT', 'EXPORT'
    incoterm: str              # e.g., 'EXW'
    payment_term: str          # e.g., 'PREPAID'
    commodity_code: str = DEFAULT_COMMODITY_CODE
    is_dangerous_goods: bool
    pieces: List[Piece]
    service_scope: Optional[str] = None  # e.g., 'D2D'
    direction: Optional[str] = None
    origin_location: Optional[LocationRef] = None
    destination_location: Optional[LocationRef] = None

class ManualOverride(BaseModel):
    """Represents a manually provided cost (e.g., a spot rate)."""
    model_config = ConfigDict(frozen=True, from_attributes=True)

    service_component_id: uuid.UUID
    cost_fcy: Decimal
    currency: str
    unit: str
    min_charge_fcy: Optional[Decimal] = None
    valid_until: Optional[str] = None

class QuoteInput(BaseModel):
    """
    The main input dataclass passed to PricingServiceV3 to start a calculation.
    """
    model_config = ConfigDict(frozen=True, from_attributes=True)

    customer_id: uuid.UUID
    contact_id: uuid.UUID
    output_currency: str
    buy_currency: Optional[str] = None
    agent_id: Optional[int] = None
    carrier_id: Optional[int] = None
    quote_date: Any = Field(default=None) # Use Any/None to avoid circular imports or strict validation issues for now
    shipment: ShipmentDetails
    overrides: List[ManualOverride] = Field(default_factory=list)
    spot_rates: Dict[str, Any] = Field(default_factory=dict)

# --- Calculation & Output Dataclasses ---

class CalculatedChargeLine(BaseModel):
    """
    The result for a single line item, containing all cost, sell, and audit data.
    """
    model_config = ConfigDict(from_attributes=True)

    # --- Fields WITHOUT default values ---
    service_component_id: uuid.UUID
    service_component_code: str
    service_component_desc: str
    leg: str  # 'ORIGIN', 'MAIN', 'DESTINATION'
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
    bucket: str = "origin_charges"
    product_code: Optional[str] = None
    component: Optional[str] = None
    basis: Optional[str] = None
    rule_family: Optional[str] = None
    service_family: Optional[str] = None
    unit_type: Optional[str] = None
    quantity: Optional[Decimal] = None
    rate: Optional[Decimal] = None
    rate_source: Optional[str] = None
    canonical_cost_source: Optional[str] = None
    calculation_notes: Optional[str] = None
    is_spot_sourced: bool = False
    is_manual_override: bool = False

    is_informational: bool = False
    conditional: bool = False

    # --- GST Fields ---
    gst_category: Optional[str] = None
    gst_rate: Decimal = Decimal("0.0")
    gst_amount: Decimal = Decimal("0.0")

class CalculatedTotals(BaseModel):
    """The final, summed totals for the quote."""
    model_config = ConfigDict(from_attributes=True)

    total_cost_pgk: Decimal = Decimal("0.0")
    
    total_sell_pgk: Decimal = Decimal("0.0")
    total_sell_pgk_incl_gst: Decimal = Decimal("0.0")
    
    total_sell_fcy: Decimal = Decimal("0.0")
    total_sell_fcy_incl_gst: Decimal = Decimal("0.0")
    total_sell_fcy_currency: str = "PGK"
    
    has_missing_rates: bool = False
    notes: Optional[str] = None
    service_notes: Optional[str] = None
    customer_notes: Optional[str] = None
    internal_notes: Optional[str] = None
    warnings: List[str] = Field(default_factory=list)
    audit_metadata: Dict[str, Any] = Field(default_factory=dict)

class QuoteCharges(BaseModel):
    """The complete set of results from a calculation."""
    model_config = ConfigDict(from_attributes=True)

    lines: List[CalculatedChargeLine]
    totals: CalculatedTotals
