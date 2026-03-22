
from decimal import Decimal
from typing import Optional, List, Dict, Any
from uuid import UUID
from pydantic import BaseModel, Field, field_validator, model_validator

from core.commodity import (
    COMMODITY_CODE_DG,
    DEFAULT_COMMODITY_CODE,
    validate_commodity_code,
)

# --- INPUT SCHEMAS (API Layer) ---

class DimensionInput(BaseModel):
    pieces: int = Field(..., gt=0)
    length_cm: Decimal = Field(..., gt=0)
    width_cm: Decimal = Field(..., gt=0)
    height_cm: Decimal = Field(..., gt=0)
    gross_weight_kg: Decimal = Field(..., gt=0)
    package_type: str = "Box"

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
    commodity_code: str = DEFAULT_COMMODITY_CODE
    is_dangerous_goods: bool = False
    dimensions: List[DimensionInput]
    overrides: List[OverrideInput] = []
    spot_rates: Dict[str, Any] = {}

    @field_validator('commodity_code', mode='before')
    @classmethod
    def validate_commodity_code_field(cls, value):
        return validate_commodity_code(value)

    @model_validator(mode='after')
    def validate_rules(self):
        if self.mode == 'AIR' and not self.dimensions:
             raise ValueError("Dimensions are required for AIR mode")
        if self.is_dangerous_goods and self.commodity_code == DEFAULT_COMMODITY_CODE:
            self.commodity_code = COMMODITY_CODE_DG
        elif self.commodity_code == COMMODITY_CODE_DG:
            self.is_dangerous_goods = True
        elif self.is_dangerous_goods:
            raise ValueError("is_dangerous_goods can only be true when commodity_code is DG.")
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
    package_type: str = "Box"
    
    class Config:
        from_attributes = True

class ShipmentDetailsSchema(BaseModel):
    mode: str
    shipment_type: str
    incoterm: str
    payment_term: str
    service_scope: str
    commodity_code: str = DEFAULT_COMMODITY_CODE
    is_dangerous_goods: bool
    direction: Optional[str] = None
    origin_location: Optional[LocationRefSchema] = None
    destination_location: Optional[LocationRefSchema] = None
    pieces: List[PieceSchema]
    
    class Config:
        from_attributes = True
