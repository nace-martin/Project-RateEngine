
from decimal import Decimal
from typing import Optional, List, Dict, Any
from uuid import UUID
from pydantic import BaseModel, Field, model_validator

# --- INPUT SCHEMAS (API Layer) ---

class DimensionInput(BaseModel):
    pieces: int = Field(..., gt=0)
    length_cm: Decimal = Field(..., gt=0)
    width_cm: Decimal = Field(..., gt=0)
    height_cm: Decimal = Field(..., gt=0)
    gross_weight_kg: Decimal = Field(..., gt=0)

class OverrideInput(BaseModel):
    service_component_id: UUID
    cost_fcy: Decimal
    currency: str = Field(..., min_length=3, max_length=3)
    unit: str
    min_charge_fcy: Optional[Decimal] = None
    valid_until: Optional[str] = None # Date string

class QuoteComputeRequest(BaseModel):
    """
    Validates the flat structure received from the frontend API.
    Used in views.py `post` method.
    """
    quote_id: Optional[UUID] = None
    customer_id: UUID
    contact_id: UUID
    mode: str
    service_scope: str
    origin_location_id: UUID
    destination_location_id: UUID
    incoterm: str
    payment_term: str
    is_dangerous_goods: bool = False
    dimensions: List[DimensionInput]
    overrides: List[OverrideInput] = []
    spot_rates: Dict[str, Any] = {}

    @model_validator(mode='after')
    def validate_rules(self):
        if self.mode == 'AIR' and not self.dimensions:
             raise ValueError("Dimensions are required for AIR mode")
        return self

# --- RESPONSE SCHEMAS (API Layer) ---

class QuoteResponse(BaseModel):
    """
    Placeholder for Pydantic-based response serialization if needed.
    Currently used in views.py imports but potentially unused in logic?
    """
    quote_id: UUID
    total_sell: Decimal

# --- DOMAIN SCHEMAS (Service Layer - Optional Migration) ---
# These were proposed for QuoteInput refactor. 
# Currently dataclasses_v3.py handles this, but we can define them here for future use.

class LocationRefSchema(BaseModel):
    id: UUID
    code: str
    name: str
    country_code: str
    currency_code: str

    class Config:
        from_attributes = True

class PieceSchema(BaseModel):
    pieces: int
    weight_kg: Decimal
    gross_weight_kg: Decimal
    length_cm: Decimal
    width_cm: Decimal
    height_cm: Decimal
    
    class Config:
        from_attributes = True

class ShipmentDetailsSchema(BaseModel):
    mode: str
    shipment_type: str
    incoterm: str
    payment_term: str
    service_scope: str
    is_dangerous_goods: bool
    direction: Optional[str] = None
    origin_location: Optional[LocationRefSchema] = None
    destination_location: Optional[LocationRefSchema] = None
    pieces: List[PieceSchema]
    
    class Config:
        from_attributes = True
