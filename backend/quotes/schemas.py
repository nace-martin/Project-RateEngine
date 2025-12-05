from decimal import Decimal
from typing import List, Optional, Dict, Any
from uuid import UUID
from datetime import datetime, date

from pydantic import BaseModel, Field, field_validator

# --- Request Schemas ---

class V3DimensionInput(BaseModel):
    pieces: int = Field(..., ge=1)
    length_cm: Decimal = Field(..., gt=0)
    width_cm: Decimal = Field(..., gt=0)
    height_cm: Decimal = Field(..., gt=0)
    gross_weight_kg: Decimal = Field(..., gt=0)

class V3ManualOverride(BaseModel):
    service_component_id: UUID
    cost_fcy: Decimal
    currency: str = Field(..., min_length=3, max_length=3)
    unit: str
    min_charge_fcy: Optional[Decimal] = None
    valid_until: Optional[date] = None

class QuoteComputeRequest(BaseModel):
    quote_id: Optional[UUID] = None
    customer_id: UUID
    contact_id: UUID
    mode: str
    service_scope: str
    origin_location_id: UUID
    destination_location_id: UUID
    incoterm: str = Field(..., min_length=3, max_length=3)
    payment_term: str
    is_dangerous_goods: bool = False
    dimensions: List[V3DimensionInput]
    overrides: Optional[List[V3ManualOverride]] = None
    spot_rates: Optional[Dict[str, Any]] = None

    @field_validator('dimensions')
    def validate_dimensions(cls, v):
        if not v:
            raise ValueError("At least one dimension line is required.")
        return v

# --- Response Schemas ---

class V3ServiceComponentSchema(BaseModel):
    id: UUID
    code: str
    description: str
    category: Optional[str] = None
    unit: str

    class Config:
        from_attributes = True

class V3QuoteLineSchema(BaseModel):
    service_component: V3ServiceComponentSchema
    cost_pgk: Decimal
    cost_fcy: Optional[Decimal] = None
    cost_fcy_currency: Optional[str] = None
    sell_pgk: Decimal
    sell_pgk_incl_gst: Decimal
    sell_fcy: Decimal
    sell_fcy_incl_gst: Decimal
    sell_fcy_currency: Optional[str] = None
    exchange_rate: Decimal
    cost_source: str
    cost_source_description: Optional[str] = None
    is_rate_missing: bool

    class Config:
        from_attributes = True

class V3QuoteTotalSchema(BaseModel):
    total_cost_pgk: Decimal
    total_sell_pgk: Decimal
    total_sell_pgk_incl_gst: Decimal
    total_sell_fcy: Decimal
    total_sell_fcy_incl_gst: Decimal
    total_sell_fcy_currency: str
    has_missing_rates: bool
    notes: Optional[List[str]] = None

    class Config:
        from_attributes = True

    @field_validator('notes', mode='before')
    def normalize_notes(cls, v):
        # Handle notes stored as a plain string in the database
        if v is None:
            return None
        if isinstance(v, str):
            return [v] if v else None
        return v

class V3QuoteVersionSchema(BaseModel):
    id: UUID
    version_number: int
    lines: List[V3QuoteLineSchema]
    totals: V3QuoteTotalSchema
    status: str
    reason: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True

    @field_validator('lines', mode='before')
    def serialize_lines(cls, v):
        # Handle Django RelatedManager
        if hasattr(v, 'all'):
            return list(v.all())
        return v

class CustomerSchema(BaseModel):
    id: UUID
    name: str
    company_type: str
    tax_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class ContactSchema(BaseModel):
    id: UUID
    first_name: str
    last_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    is_primary: bool
    company_id: UUID
    company_name: str

    class Config:
        from_attributes = True

    @field_validator('company_name', mode='before')
    def get_company_name(cls, v, info):
        # If v is missing, we might need to fetch it from the object if possible, 
        # but Pydantic's from_attributes usually handles 'company.name' if mapped.
        # However, for simple ORM mapping, 'company_name' isn't a direct attribute of Contact unless annotated.
        # The serializer used source='company.name'.
        # For Pydantic v2, we can use a computed_field or a validator if we are constructing from ORM.
        # But for simplicity, let's assume the ORM object passed has these attributes or we handle it in the view.
        # Actually, let's just make it optional or handle it in the view if it's complex.
        return v

class QuoteResponse(BaseModel):
    id: UUID
    quote_number: str
    customer: CustomerSchema
    contact: ContactSchema
    mode: str
    shipment_type: str
    incoterm: str
    payment_term: str
    service_scope: str
    output_currency: str
    origin_location: str # String representation
    destination_location: str # String representation
    status: str
    valid_until: Optional[date] = None
    created_at: datetime
    latest_version: Optional[V3QuoteVersionSchema] = None

    class Config:
        from_attributes = True

    @field_validator('origin_location', mode='before')
    def serialize_origin(cls, v):
        return str(v) if v else None

    @field_validator('destination_location', mode='before')
    def serialize_destination(cls, v):
        return str(v) if v else None
