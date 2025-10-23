# backend/pricing_v2/dataclasses_v3.py

from dataclasses import dataclass, field
from decimal import Decimal
from typing import List, Dict, Any, Optional

# Import relevant models
from core.models import Policy, FxSnapshot, Currency
from parties.models import Company, Contact, CustomerCommercialProfile
from services.models import ServiceComponent


@dataclass
class V3QuoteRequest:
    """ Inputs derived directly from the API request for V3 """
    customer: Company
    contact: Optional[Contact]
    mode: str
    shipment_type: str
    incoterm: Optional[str]
    payment_term: str
    origin_code: str
    destination_code: str
    pieces: List[Dict[str, Any]]
    is_dangerous_goods: bool
    output_currency_override: Optional[str]
    # Add other flags/inputs as needed


@dataclass
class CalculationContext:
    """ Holds all necessary context for a V3 calculation """
    request: V3QuoteRequest
    customer_profile: Optional[CustomerCommercialProfile]
    policy: Policy # Fallback policy
    fx_snapshot: FxSnapshot
    output_currency: Currency # Final determined output currency object
    chargeable_kg: Decimal # Calculated chargeable weight (or W/M etc. later)
    # user: Any # User object for permissions/audit


@dataclass
class ServiceCostLine:
    """ Represents a calculated cost/sell line item """
    service_component: ServiceComponent
    cost_pgk: Decimal = Decimal("0.0")
    source_info: str = "" # How cost was derived (e.g., base, rate card, manual)
    is_incomplete: bool = False # Add flag to dataclass
    margin_applied_pct: Optional[Decimal] = None
    sell_price_pgk: Decimal = Decimal("0.0")
    gst_pct: Decimal = Decimal("0.0")
    gst_pgk: Decimal = Decimal("0.0")
    output_currency: Optional[str] = None
    sell_price_output: Decimal = Decimal("0.0")
    gst_output: Decimal = Decimal("0.0")
