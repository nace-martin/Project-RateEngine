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
        """Ensure tt_sell >= tt_buy (bank always makes a spread)."""
        if self.tt_sell < self.tt_buy:
            raise ValueError(
                f"TT Sell ({self.tt_sell}) must be >= TT Buy ({self.tt_buy}). "
                "Bank's sell rate should be higher than buy rate."
            )
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


# =============================================================================
# 3. FX CONVERSION SERVICE
# =============================================================================

class FxConversionRequest(BaseModel):
    """Request schema for FX conversion."""
    amount: Decimal = Field(..., description="Amount to convert")
    from_currency: str = Field(..., min_length=3, max_length=3, description="Source currency code")
    to_currency: str = Field(..., min_length=3, max_length=3, description="Target currency code")
    direction: Literal["IMPORT", "EXPORT", "DOMESTIC"] = Field(
        default="IMPORT",
        description="Shipment direction (affects which CAF to use)"
    )
    apply_caf: bool = Field(default=True, description="Whether to apply CAF buffer")
    
    @field_validator('amount', mode='before')
    @classmethod
    def convert_amount(cls, v):
        return Decimal(str(v))
    
    @field_validator('from_currency', 'to_currency', mode='before')
    @classmethod
    def uppercase_currency(cls, v):
        return str(v).upper()


class FxConversionResult(BaseModel):
    """Result schema for FX conversion with full audit trail."""
    original_amount: Decimal
    original_currency: str
    converted_amount: Decimal
    converted_currency: str
    
    # Audit fields
    base_rate: Decimal = Field(..., description="Raw rate before CAF")
    caf_applied: Decimal = Field(..., description="CAF percentage applied (e.g., 0.05)")
    effective_rate: Decimal = Field(..., description="Final rate after CAF adjustment")
    conversion_type: str = Field(..., description="FCY_TO_PGK or PGK_TO_FCY")
    rate_source: str = Field(default="TT_BUY", description="TT_BUY or TT_SELL")
    
    class Config:
        json_encoders = {
            Decimal: lambda v: str(v.quantize(Decimal("0.0001")))
        }


class FxConversionService:
    """
    Encapsulated FX conversion service with Pydantic validation.
    
    Usage:
        fx_service = FxConversionService(fx_rates_schema, policy_schema)
        result = fx_service.convert(FxConversionRequest(
            amount=Decimal("100.00"),
            from_currency="AUD",
            to_currency="PGK",
            direction="IMPORT",
            apply_caf=True
        ))
        print(result.converted_amount)  # 290.85
        print(result.effective_rate)    # 2.9085
    """
    
    HOME_CURRENCY = "PGK"
    
    def __init__(self, fx_rates: FxRatesSchema, policy: PolicySchema):
        self.fx_rates = fx_rates
        self.policy = policy
    
    @classmethod
    def from_django_models(cls, fx_snapshot, policy) -> "FxConversionService":
        """Create from Django model instances."""
        fx_rates = FxRatesSchema.from_json_field(fx_snapshot.rates)
        policy_schema = PolicySchema.from_django_model(policy)
        return cls(fx_rates, policy_schema)
    
    def convert(self, request: FxConversionRequest) -> FxConversionResult:
        """
        Perform currency conversion with CAF application.
        
        FCY -> PGK (Buy-side/Cost):
            - Use TT BUY rate
            - Apply CAF by MULTIPLYING: TT_BUY * (1 + CAF)
            - Example: 2.77 * 1.05 = 2.91
            
        PGK -> FCY (Sell-side):
            - Use TT SELL rate (inverted: 1/TT_SELL)
            - Apply CAF by DIVIDING: (1/TT_SELL) / (1 + CAF)
            - Example: (1/2.85) / 1.10 = 0.318
        """
        if request.from_currency == request.to_currency:
            return FxConversionResult(
                original_amount=request.amount,
                original_currency=request.from_currency,
                converted_amount=request.amount,
                converted_currency=request.to_currency,
                base_rate=Decimal("1.0"),
                caf_applied=Decimal("0.0"),
                effective_rate=Decimal("1.0"),
                conversion_type="SAME_CURRENCY",
                rate_source="N/A"
            )
        
        caf = self._get_caf(request.direction)
        
        if request.from_currency != self.HOME_CURRENCY and request.to_currency == self.HOME_CURRENCY:
            # FCY -> PGK (Cost conversion)
            return self._convert_fcy_to_pgk(request, caf)
        
        elif request.from_currency == self.HOME_CURRENCY and request.to_currency != self.HOME_CURRENCY:
            # PGK -> FCY (Sell conversion)
            return self._convert_pgk_to_fcy(request, caf)
        
        else:
            # Cross-currency (FCY -> FCY): Go through PGK
            intermediate = self._convert_fcy_to_pgk(
                FxConversionRequest(
                    amount=request.amount,
                    from_currency=request.from_currency,
                    to_currency=self.HOME_CURRENCY,
                    direction=request.direction,
                    apply_caf=request.apply_caf
                ),
                caf
            )
            return self._convert_pgk_to_fcy(
                FxConversionRequest(
                    amount=intermediate.converted_amount,
                    from_currency=self.HOME_CURRENCY,
                    to_currency=request.to_currency,
                    direction=request.direction,
                    apply_caf=request.apply_caf
                ),
                caf
            )
    
    def _convert_fcy_to_pgk(self, request: FxConversionRequest, caf: Decimal) -> FxConversionResult:
        """
        Convert FCY to PGK using TT BUY rate.
        
        Formula: FCY_amount * TT_BUY * (1 + CAF) = PGK
        """
        currency_rate = self.fx_rates.get_rate(request.from_currency)
        if not currency_rate:
            raise ValueError(f"No FX rate found for {request.from_currency}")
        
        base_rate = currency_rate.tt_buy
        caf_applied = caf if request.apply_caf else Decimal("0.0")
        effective_rate = base_rate * (Decimal("1.0") + caf_applied)
        
        converted = (request.amount * effective_rate).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        
        return FxConversionResult(
            original_amount=request.amount,
            original_currency=request.from_currency,
            converted_amount=converted,
            converted_currency=self.HOME_CURRENCY,
            base_rate=base_rate,
            caf_applied=caf_applied,
            effective_rate=effective_rate.quantize(Decimal("0.0001")),
            conversion_type="FCY_TO_PGK",
            rate_source="TT_BUY"
        )
    
    def _convert_pgk_to_fcy(self, request: FxConversionRequest, caf: Decimal) -> FxConversionResult:
        """
        Convert PGK to FCY using inverted TT SELL rate.
        
        Formula: PGK_amount * (1/TT_SELL) / (1 + CAF) = FCY
        """
        currency_rate = self.fx_rates.get_rate(request.to_currency)
        if not currency_rate:
            raise ValueError(f"No FX rate found for {request.to_currency}")
        
        # TT_SELL is stored as PGK per FCY, we need FCY per PGK
        tt_sell_pgk_per_fcy = currency_rate.tt_sell
        base_rate = Decimal("1.0") / tt_sell_pgk_per_fcy  # Invert to get FCY per PGK
        
        caf_applied = caf if request.apply_caf else Decimal("0.0")
        effective_rate = base_rate / (Decimal("1.0") + caf_applied)
        
        converted = (request.amount * effective_rate).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        
        return FxConversionResult(
            original_amount=request.amount,
            original_currency=self.HOME_CURRENCY,
            converted_amount=converted,
            converted_currency=request.to_currency,
            base_rate=base_rate.quantize(Decimal("0.0001")),
            caf_applied=caf_applied,
            effective_rate=effective_rate.quantize(Decimal("0.0001")),
            conversion_type="PGK_TO_FCY",
            rate_source="TT_SELL"
        )
    
    def _get_caf(self, direction: str) -> Decimal:
        """Get CAF percentage based on shipment direction."""
        if direction == "IMPORT":
            return self.policy.caf_import_pct
        elif direction == "EXPORT":
            return self.policy.caf_export_pct
        return Decimal("0.0")
    
    def get_audit_info(self) -> Dict[str, Any]:
        """Get audit information about current FX rates and policy."""
        return {
            "policy": {
                "margin_pct": str(self.policy.margin_pct),
                "caf_import_pct": str(self.policy.caf_import_pct),
                "caf_export_pct": str(self.policy.caf_export_pct),
                "include_gst_in_agent_quote": self.policy.include_gst_in_agent_quote,
            },
            "fx_rates": self.fx_rates.model_dump(exclude_none=True)
        }
