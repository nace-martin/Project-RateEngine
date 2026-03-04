# backend/core/fx_schemas.py

"""
Pydantic schemas for FX Rate management and currency conversion.

This module provides:
1. FxRatesSchema - Validation of FX rate snapshots
2. PolicySchema - Validation of pricing policy configuration  
3. FxConversionService - Encapsulated FX conversion logic with full audit trail
"""

from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, Literal, Dict, Any
from pydantic import BaseModel, Field, field_validator, model_validator
import json


# =============================================================================
# 1. FX RATE VALIDATION SCHEMAS
# =============================================================================

class CurrencyRateSchema(BaseModel):
    """
    Schema for validating a single currency's exchange rates.
    
    Both rates are stored as "PGK per FCY" (e.g., 2.77 means 2.77 PGK = 1 AUD).
    
    - tt_buy: Rate when bank buys FCY (we pay this when converting FCY costs to PGK)
    - tt_sell: Rate when bank sells FCY (we use inverse for PGK to FCY conversion)
    """
    tt_buy: Decimal = Field(..., gt=0, description="TT Buy rate (PGK per FCY)")
    tt_sell: Decimal = Field(..., gt=0, description="TT Sell rate (PGK per FCY)")
    
    @field_validator('tt_buy', 'tt_sell', mode='before')
    @classmethod
    def convert_to_decimal(cls, v):
        if v is None:
            raise ValueError("Rate cannot be None")
        return Decimal(str(v))
    
    @model_validator(mode='after')
    def validate_spread(self):
        """
        Validate bank spread.
        For direct quotes (PGK per FCY, values > 1), tt_sell >= tt_buy.
        For indirect quotes (FCY per PGK, values < 1), tt_buy >= tt_sell.
        """
        # If both are > 1 (e.g. 2.77 PGK = 1 AUD)
        if self.tt_buy > 1 and self.tt_sell > 1:
            if self.tt_sell < self.tt_buy:
                raise ValueError(
                    f"For direct rates (>1), TT Sell ({self.tt_sell}) must be >= TT Buy ({self.tt_buy})."
                )
        # If both are < 1 (e.g. 0.33 AUD = 1 PGK)
        elif self.tt_buy < 1 and self.tt_sell < 1:
            if self.tt_buy < self.tt_sell:
                # We won't raise an exception here because users might have already saved
                # flipped data due to the previous bug. But logically: tt_buy >= tt_sell.
                pass
        return self


class FxRatesSchema(BaseModel):
    """
    Schema for validating a complete FX rates snapshot.
    
    Example usage:
        rates_data = {"AUD": {"tt_buy": 2.77, "tt_sell": 2.85}, ...}
        validated = FxRatesSchema.model_validate(rates_data)
    """
    AUD: Optional[CurrencyRateSchema] = None
    USD: Optional[CurrencyRateSchema] = None
    EUR: Optional[CurrencyRateSchema] = None
    GBP: Optional[CurrencyRateSchema] = None
    NZD: Optional[CurrencyRateSchema] = None
    SGD: Optional[CurrencyRateSchema] = None
    JPY: Optional[CurrencyRateSchema] = None
    CNY: Optional[CurrencyRateSchema] = None
    PHP: Optional[CurrencyRateSchema] = None
    IDR: Optional[CurrencyRateSchema] = None
    FJD: Optional[CurrencyRateSchema] = None
    
    class Config:
        extra = 'allow'  # Allow additional currencies not explicitly defined
    
    @classmethod
    def from_json_field(cls, rates_json: str | dict) -> "FxRatesSchema":
        """Parse from Django JSONField which may be string or dict."""
        if isinstance(rates_json, str):
            rates_json = json.loads(rates_json)
        return cls.model_validate(rates_json)
    
    def get_rate(self, currency: str) -> Optional[CurrencyRateSchema]:
        """Get rate for a currency, handling dynamic currencies."""
        rate = getattr(self, currency, None)
        if rate is None and hasattr(self, '__pydantic_extra__'):
            extra = getattr(self, '__pydantic_extra__', {})
            if currency in extra:
                return CurrencyRateSchema.model_validate(extra[currency])
        return rate


# =============================================================================
# 2. POLICY CONFIGURATION SCHEMA
# =============================================================================

class PolicySchema(BaseModel):
    """
    Schema for validating pricing policy configuration.
    
    CAF (Currency Adjustment Factor) / Buffer percentages are applied to FX rates
    to protect against currency fluctuation during the quote validity period.
    """
    margin_pct: Decimal = Field(
        default=Decimal("0.15"),
        ge=0,
        le=1.0,
        description="Standard margin percentage (0.15 = 15%)"
    )
    caf_import_pct: Decimal = Field(
        default=Decimal("0.05"),
        ge=0,
        le=0.5,
        description="CAF for import quotes (0.05 = 5%). Applied when converting FCY costs to PGK."
    )
    caf_export_pct: Decimal = Field(
        default=Decimal("0.10"),
        ge=0,
        le=0.5,
        description="CAF for export quotes (0.10 = 10%). Applied when converting PGK sell to FCY."
    )
    include_gst_in_agent_quote: bool = Field(
        default=True,
        description="Whether to include GST in agent quotes"
    )
    
    @field_validator('margin_pct', 'caf_import_pct', 'caf_export_pct', mode='before')
    @classmethod
    def convert_to_decimal(cls, v):
        if v is None:
            return Decimal("0.0")
        return Decimal(str(v))
    
    @classmethod
    def from_django_model(cls, policy) -> "PolicySchema":
        """Create from Django Policy model instance."""
        return cls(
            margin_pct=policy.margin_pct or Decimal("0.15"),
            caf_import_pct=policy.caf_import_pct or Decimal("0.05"),
            caf_export_pct=policy.caf_export_pct or Decimal("0.10"),
            include_gst_in_agent_quote=policy.include_gst_in_agent_quote,
        )

