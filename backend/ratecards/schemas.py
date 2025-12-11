
from decimal import Decimal
from typing import Optional, Literal
from pydantic import BaseModel, Field, model_validator, ValidationError

class SeededRateItem(BaseModel):
    """
    Validates a single rate item before seeding.
    """
    code: str = Field(..., description="Service Component Code")
    description: Optional[str] = None
    unit: str = Field(..., pattern=r'^(KG|PER_KG|SHIPMENT|AWB|PAGE|PERCENTAGE)$')
    
    # Cost Types
    cost_type: Literal['PARTNER_RATE', 'RATE_OFFER', 'DIRECT_SELL_RATE', 'PARTNER_TIERED'] = 'PARTNER_RATE'
    
    # Rate Values
    rate_per_kg: Optional[Decimal] = Field(None, ge=0)
    rate_per_shipment: Optional[Decimal] = Field(None, ge=0)
    min_charge: Optional[Decimal] = Field(None, ge=0)
    max_charge: Optional[Decimal] = Field(None, ge=0)
    
    # Fixed Sell Specifics
    is_fixed_sell: bool = False

    @model_validator(mode='after')
    def validate_fixed_sell(self):
        # If marked as Fixed Sell, must be RATE_OFFER or DIRECT_SELL_RATE
        if self.is_fixed_sell:
            if self.cost_type not in ['RATE_OFFER', 'DIRECT_SELL_RATE']:
                raise ValueError(f"Fixed Sell Item {self.code} must have cost_type RATE_OFFER or DIRECT_SELL_RATE, got {self.cost_type}")
        
        # If RATE_OFFER, generally should imply no margin logic in engine, 
        # but pure data val: check if we have value.
        if self.cost_type == 'RATE_OFFER':
            if self.rate_per_kg is None and self.rate_per_shipment is None:
                raise ValueError(f"RATE_OFFER {self.code} requires a rate value (per_kg or per_shipment)")
        
        return self

class SeededRateCard(BaseModel):
    """
    Validates the overall Rate Card config.
    """
    name: str
    currency: str = Field(..., min_length=3, max_length=3)
    supplier_name: str
    service_level: str = 'STANDARD'

# --- JSON Field Schemas (Area 3) ---

from typing import List

class TierBreak(BaseModel):
    min_kg: Decimal = Field(..., ge=0)
    rate_per_kg: Decimal = Field(..., ge=0)

class TieringJsonSchema(BaseModel):
    """
    Validates proper structure for 'tiering_json' field in database.
    Example: { "type": "weight_break", "currency": "AUD", "minimum_charge": "330.00", "breaks": [...] }
    """
    type: Literal['weight_break'] = 'weight_break'
    currency: str = Field(..., min_length=3, max_length=3)
    minimum_charge: Decimal = Field(..., ge=0)
    breaks: List[TierBreak]

    @model_validator(mode='after')
    def validate_breaks_order(self):
        # Sort validation could go here
        return self

# --- CSV Import Schemas (Area 2) ---

class RateCardImportRowSchema(BaseModel):
    """
    Validates a single row from a Rate Card CSV upload.
    """
    origin_code: str = Field(..., min_length=3, max_length=3)
    destination_code: str = Field(..., min_length=3, max_length=3)
    service_alias: str = Field(..., min_length=1) # e.g. "FRT" or "Local1"
    
    rate_val: Optional[Decimal] = None
    min_val: Optional[Decimal] = None
    currency: str = Field(..., min_length=3, max_length=3)
    
    # Weight breaks often come as separate columns in CSV, need handling logic outside schema
    # or a dynamic schema. For flat rate rows:
    
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None

    class Config:
        extra = 'ignore' # Allow extra columns in CSV
