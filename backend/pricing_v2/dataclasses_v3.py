# In: backend/pricing_v2/dataclasses_v3.py

from dataclasses import dataclass, field
from decimal import Decimal
from typing import List, Optional, Dict
from uuid import UUID
from parties.models import CustomerCommercialProfile
from core.models import FxSnapshot, Airport
from services.models import ServiceComponent

@dataclass
class DimensionLine:
    """
    Represents one line of dimensions, which may contain multiple pieces.
    e.g., 2 pieces @ 100x50x50cm, 20kg each
    """
    pieces: int
    length_cm: Decimal
    width_cm: Decimal
    height_cm: Decimal
    gross_weight_kg: Decimal # Assumed to be weight PER PIECE

@dataclass
class ServiceCostLine:
    """
    Represents a single line item in a quote calculation, holding cost data.
    """
    service_component: ServiceComponent
    cost_pgk: Decimal
    sell_pgk: Decimal
    cost_source: str
    cost_fcy: Optional[Decimal] = None
    cost_fcy_currency: Optional[str] = None
    sell_fcy: Optional[Decimal] = None
    sell_fcy_currency: Optional[str] = None
    sell_pgk_incl_gst: Optional[Decimal] = None
    sell_fcy_incl_gst: Optional[Decimal] = None
    exchange_rate: Optional[Decimal] = None
    is_rate_missing: bool = False
    cost_source_description: Optional[str] = None

@dataclass
class CalculationContext:
    """
    Holds all the necessary data for a quote calculation.
    """
    request: 'V3QuoteRequest'
    customer: 'Company'
    customer_profile: CustomerCommercialProfile
    fx_snapshot: FxSnapshot
    output_currency: str
    chargeable_weight_kg: Decimal
    origin_airport: Airport
    destination_airport: Airport
    incoterm_rule_key: tuple
    overrides: Dict[UUID, 'ManualCostOverride']

@dataclass
class ManualCostOverride:
    """
    Represents a single spot rate manually provided by the user
    to override database lookups for a COGS service.
    """
    service_component_id: UUID
    cost_fcy: Decimal
    currency: str  # e.g., 'USD', 'AUD'
    unit: str      # e.g., 'PER_KG', 'PER_SHIPMENT'
    min_charge_fcy: Optional[Decimal] = None
    # We can add tiering_json here later if needed for complex overrides


@dataclass
class V3QuoteRequest:
    """
    All input data required to compute a V3 Quote.
    NOW ACCEPTS DIMENSION LINES instead of totals.
    """
    customer_id: UUID
    contact_id: UUID
    mode: str
    shipment_type: str
    incoterm: str
    origin_airport_code: str
    destination_airport_code: str
    
    # --- THESE FIELDS ARE NEW ---
    dimensions: List[DimensionLine]
    
    # --- THESE FIELDS ARE REMOVED ---
    # pieces: int
    # gross_weight_kg: Decimal
    # volume_cbm: Decimal
    
    # Optional fields (unchanged)
    payment_term: str = "PREPAID"
    output_currency: Optional[str] = None
    is_dangerous_goods: bool = False
    
    overrides: List[ManualCostOverride] = field(default_factory=list)

@dataclass
class V3QuoteResponse:
    """
    The response from a V3 quote calculation.
    """
    quote_id: int
    quote_version_id: int
    lines: List[ServiceCostLine]
