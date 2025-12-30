"""
AI-Assisted Rate Intake Schemas

These schemas define the contract for AI-parsed charge lines.
All AI output MUST pass these validations before being shown to users.

Key Principles:
- AI never writes directly to database
- All output requires human acceptance
- Validation failures trigger retry or manual entry
"""

from decimal import Decimal
from typing import Literal, Optional, List
from pydantic import BaseModel, Field, model_validator, field_validator
from uuid import uuid4


# =============================================================================
# CURRENCY & BUCKET ENUMS
# =============================================================================

# Valid bucket types for charge categorization
SpotChargeBucket = Literal["ORIGIN", "FREIGHT", "DESTINATION"]

# Valid unit basis for charge calculation
# MIN_OR_PER_KG: Dual pricing - charge is MAX(minimum, rate_per_unit * weight)
UnitBasis = Literal["PER_KG", "PER_SHIPMENT", "PERCENTAGE", "MIN_OR_PER_KG"]

# Common currencies for validation (extendable)
VALID_CURRENCIES = {
    "PGK", "AUD", "USD", "NZD", "FJD", "SBD", "VUV", "EUR", "GBP", 
    "SGD", "HKD", "JPY", "CNY", "PHP", "IDR", "MYR", "THB", "INR"
}


# =============================================================================
# SPOT CHARGE LINE SCHEMA
# =============================================================================

class SpotChargeLine(BaseModel):
    """
    Single charge line parsed from agent/carrier quote.
    
    This is the core schema for AI rate intake. Each line represents
    one charge extracted from unstructured text/PDF.
    
    Examples:
        - "Pickup: AUD 85.00 min" → SpotChargeLine(bucket="ORIGIN", description="Pickup", amount=85.00, currency="AUD", unit_basis="PER_SHIPMENT", minimum=85.00)
        - "Fuel Surcharge: 10% of freight" → SpotChargeLine(bucket="FREIGHT", description="Fuel Surcharge", unit_basis="PERCENTAGE", percentage=10.00, percent_applies_to="FREIGHT")
    """
    
    # Optional ID for tracking (generated if not provided)
    id: Optional[str] = Field(default_factory=lambda: f"ai-{uuid4().hex[:8]}")
    
    # Required: Which bucket this charge belongs to
    bucket: SpotChargeBucket = Field(
        ..., 
        description="Cost bucket: ORIGIN (pickup/export), FREIGHT (air/sea), DESTINATION (delivery/import)"
    )
    
    # Required: Human-readable description
    description: str = Field(
        ..., 
        min_length=1, 
        max_length=200,
        description="Charge description as extracted from source"
    )
    
    # Amount in foreign currency (for flat charges or minimums)
    amount: Optional[Decimal] = Field(
        None, 
        ge=0,
        description="Charge amount in FCY. Required for PER_SHIPMENT. For MIN_OR_PER_KG, this is the minimum."
    )
    
    # Rate per unit (for PER_KG or MIN_OR_PER_KG charges)
    rate_per_unit: Optional[Decimal] = Field(
        None, 
        ge=0,
        description="Rate per kg/unit. Used for PER_KG and MIN_OR_PER_KG unit basis."
    )
    
    # Currency code (must be valid 3-letter ISO code)
    currency: Optional[str] = Field(
        None, 
        min_length=3, 
        max_length=3,
        description="ISO 4217 currency code (e.g., AUD, USD, PGK)"
    )
    
    # How the charge is calculated
    unit_basis: UnitBasis = Field(
        ...,
        description="PER_KG (weight-based), PER_SHIPMENT (flat fee), PERCENTAGE (% of another charge)"
    )
    
    # For percentage-based charges
    percentage: Optional[Decimal] = Field(
        None, 
        ge=0, 
        le=100,
        description="Percentage value (0-100). Required if unit_basis is PERCENTAGE."
    )
    
    # Minimum charge (for PER_KG with floor)
    minimum: Optional[Decimal] = Field(
        None, 
        ge=0,
        description="Minimum charge amount (floor)"
    )
    
    # Maximum charge (for capped charges)
    maximum: Optional[Decimal] = Field(
        None, 
        ge=0,
        description="Maximum charge amount (ceiling)"
    )
    
    # For percentage charges: what component it applies to
    percent_applies_to: Optional[str] = Field(
        None,
        description="Component code or bucket that this percentage applies to (e.g., 'FREIGHT', 'PICKUP')"
    )
    
    # AI extraction notes
    notes: Optional[str] = Field(
        None,
        max_length=500,
        description="AI notes about extraction or ambiguity"
    )
    
    # Conditional flag (e.g. "if applicable")
    conditional: bool = Field(
        default=False,
        description="True if charge is conditional or optional (e.g. 'if applicable')"
    )
    
    # Confidence score from AI (metadata only - does NOT drive logic in MVP)
    confidence: Optional[float] = Field(
        None,
        ge=0,
        le=1,
        description="AI confidence in this extraction. Metadata only - does not affect validation."
    )
    
    # Currency validation warning (populated by validator, not by AI)
    _currency_warning: Optional[str] = None

    @field_validator('currency')
    @classmethod
    def validate_currency(cls, v: Optional[str]) -> Optional[str]:
        """Validate currency format. Warn on unknown currencies but don't reject."""
        if v is None:
            return v
        v = v.upper()
        # Unknown currencies are allowed but will generate warning in model_validator
        return v

    @model_validator(mode='after')
    def validate_charge_type(self):
        """Ensure charge has required fields based on unit_basis."""
        
        # PER_SHIPMENT requires amount
        if self.unit_basis == "PER_SHIPMENT":
            if self.amount is None:
                raise ValueError(f"amount is required for unit_basis={self.unit_basis}")
        
        # PER_KG requires rate_per_unit (or amount as legacy support)
        if self.unit_basis == "PER_KG":
            # Accept either rate_per_unit or amount for per-kg rate
            if self.rate_per_unit is None and self.amount is None:
                raise ValueError("rate_per_unit or amount is required for unit_basis=PER_KG")
        
        # MIN_OR_PER_KG: Dual pricing structure (min OR per kg, whichever is greater)
        if self.unit_basis == "MIN_OR_PER_KG":
            # Must have either minimum or amount (both mean the same - the floor)
            min_value = self.minimum or self.amount
            
            # If missing required fields, downgrade to simpler unit type
            if min_value is None and self.rate_per_unit is None:
                # No data at all - let it through with warning
                pass
            elif min_value is None and self.rate_per_unit is not None:
                # Only has per-kg rate, downgrade to PER_KG
                object.__setattr__(self, 'unit_basis', 'PER_KG')
            elif min_value is not None and self.rate_per_unit is None:
                # Only has minimum, downgrade to PER_SHIPMENT
                object.__setattr__(self, 'unit_basis', 'PER_SHIPMENT')
                if self.amount is None:
                    object.__setattr__(self, 'amount', min_value)
            else:
                # Has both - normalize minimum field
                if self.minimum is None and self.amount is not None:
                    object.__setattr__(self, 'minimum', self.amount)
        
        # PERCENTAGE requires percentage value AND percent_applies_to
        if self.unit_basis == "PERCENTAGE":
            if self.percentage is None:
                raise ValueError("percentage is required for unit_basis=PERCENTAGE")
            if self.percent_applies_to is None:
                raise ValueError("percent_applies_to is required for unit_basis=PERCENTAGE (e.g., 'FREIGHT', 'PICKUP')")
        
        # Minimum cannot exceed maximum
        if self.minimum is not None and self.maximum is not None:
            if self.minimum > self.maximum:
                raise ValueError("minimum cannot exceed maximum")
        
        # Add warning for unknown currency (but don't reject)
        if self.currency and self.currency not in VALID_CURRENCIES:
            object.__setattr__(self, '_currency_warning', 
                f"Unknown currency '{self.currency}' - verify this is correct")
        
        return self
    
    def get_warnings(self) -> List[str]:
        """Return any validation warnings for this line."""
        warnings = []
        if self._currency_warning:
            warnings.append(self._currency_warning)
        return warnings

    class Config:
        json_schema_extra = {
            "example": {
                "bucket": "ORIGIN",
                "description": "Pickup & Collection",
                "amount": "85.00",
                "currency": "AUD",
                "unit_basis": "PER_SHIPMENT",
                "minimum": "85.00",
                "notes": "Extracted from 'Pick-up: AUD85.00'"
            }
        }


# =============================================================================
# AI RATE INTAKE RESPONSE SCHEMA
# =============================================================================

class AIRateIntakeResponse(BaseModel):
    """
    Validated response from AI rate extraction.
    
    This schema wraps the complete AI extraction result, including
    all parsed lines, warnings, and extraction metadata.
    """
    
    # Overall success flag
    success: bool = Field(
        ...,
        description="True if extraction completed without critical errors"
    )
    
    # Extracted charge lines (may be empty on failure)
    lines: List[SpotChargeLine] = Field(
        default_factory=list,
        description="List of extracted charge lines"
    )
    
    # Document-level currency fallback
    quote_currency: Optional[str] = Field(
        None,
        min_length=3,
        max_length=3,
        description="Default currency for the entire quote (if not specified per line)"
    )
    
    # Non-fatal warnings (e.g., ambiguous currency, low confidence)
    warnings: List[str] = Field(
        default_factory=list,
        description="Warnings about extraction quality or ambiguity"
    )
    
    # Error message if success=False
    error: Optional[str] = Field(
        None,
        description="Error message if extraction failed"
    )
    
    # Input metadata
    raw_text_length: int = Field(
        ...,
        ge=0,
        description="Character count of input text"
    )
    
    # Overall extraction confidence (optional metadata - does NOT drive logic in MVP)
    extraction_confidence: Optional[float] = Field(
        None,
        ge=0,
        le=1,
        description="Overall confidence score. Metadata only - does not affect validation."
    )
    
    # Source type
    source_type: Literal["TEXT", "PDF", "EMAIL"] = Field(
        default="TEXT",
        description="Type of source document"
    )
    
    # AI model used
    model_used: Optional[str] = Field(
        None,
        description="AI model identifier (e.g., 'gemini-2.0-flash')"
    )

    # Pricing Analysis from AI
    analysis_text: Optional[str] = Field(
        None,
        max_length=2000,
        description="Pricing and rate analysis provided by the AI"
    )

    @model_validator(mode='after')
    def validate_response(self):
        """Ensure response is internally consistent."""
        
        # If success but no lines, add informational warning
        if self.success and len(self.lines) == 0 and "No charge lines extracted" not in str(self.warnings):
            self.warnings.append("No charge lines extracted from input")
        
        # If failed, should have error message
        if not self.success and not self.error:
            self.error = "Extraction failed without specific error"
        
        # Validate currency requirements
        # If line lacks currency, quote_currency MUST be present
        for i, line in enumerate(self.lines):
            # Skip percentage as it might not strictly need currency (it's ratio)
            if line.unit_basis == "PERCENTAGE":
                continue
            
            if line.currency is None:
                if self.quote_currency is None:
                    raise ValueError(f"Line {i+1} ({line.description}): Currency is missing and no global quote_currency provided")
            
            # Determine effective currency
            eff_eur = line.currency or self.quote_currency
            if eff_eur and eff_eur not in VALID_CURRENCIES:
                 if f"Unknown currency '{eff_eur}'" not in str(self.warnings):
                    self.warnings.append(f"Line {i+1}: Unknown currency '{eff_eur}'")

        # Collect currency warnings from lines
        for line in self.lines:
            line_warnings = line.get_warnings()
            for w in line_warnings:
                if w not in self.warnings:
                    self.warnings.append(w)
        
        return self

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "lines": [
                    {
                        "bucket": "ORIGIN",
                        "description": "Pickup",
                        "amount": "85.00",
                        "currency": "AUD",
                        "unit_basis": "PER_SHIPMENT"
                    }
                ],
                "warnings": [],
                "raw_text_length": 450,
                "extraction_confidence": 0.85,
                "source_type": "TEXT",
                "model_used": "gemini-2.0-flash"
            }
        }


# =============================================================================
# PDF EXTRACTION RESULT SCHEMA
# =============================================================================

class PDFExtractionResult(BaseModel):
    """
    Result of PDF text extraction (before AI processing).
    
    This schema captures the deterministic text extraction step,
    separate from AI parsing.
    """
    
    success: bool = Field(
        ...,
        description="True if text extraction succeeded"
    )
    
    text: str = Field(
        default="",
        description="Extracted text content"
    )
    
    page_count: int = Field(
        default=0,
        ge=0,
        description="Number of pages in PDF"
    )
    
    method_used: Literal["PDFPLUMBER", "PYMUPDF", "OCR"] = Field(
        default="PDFPLUMBER",
        description="Extraction method that succeeded"
    )
    
    ocr_used: bool = Field(
        default=False,
        description="Whether OCR was required (implies lower confidence)"
    )
    
    ocr_confidence: Optional[float] = Field(
        None,
        ge=0,
        le=1,
        description="OCR confidence if applicable"
    )
    
    error: Optional[str] = Field(
        None,
        description="Error message if extraction failed"
    )
    
    warnings: List[str] = Field(
        default_factory=list,
        description="Extraction warnings (e.g., 'Low OCR confidence')"
    )

    @model_validator(mode='after')
    def add_ocr_warning(self):
        """Add warning if OCR confidence is low."""
        if self.ocr_used and self.ocr_confidence is not None:
            if self.ocr_confidence < 0.7:
                self.warnings.append(
                    f"Low OCR confidence ({self.ocr_confidence:.0%}). "
                    "Extracted text may contain errors."
                )
        return self
