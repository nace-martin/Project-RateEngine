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
    Final validated charge line emitted by the multi-agent intake pipeline.
    
    This combines normalized mapping data (v4 bucket/code, normalized confidence)
    with the validated charge calculation fields used by downstream pricing logic.
    
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

    # Raw extraction label preserved for traceability
    original_raw_label: Optional[str] = Field(
        None,
        min_length=1,
        max_length=200,
        description="Original raw label from extraction stage (defaults to description)"
    )

    # Normalized v4 product mapping
    v4_product_code: str = Field(
        default="UNMAPPED",
        min_length=1,
        max_length=64,
        description="Mapped v4 product code or 'UNMAPPED'"
    )

    # Explicit normalized bucket from mapping stage (mirrors bucket)
    v4_bucket: Optional[SpotChargeBucket] = Field(
        None,
        description="Normalized v4 bucket from mapping stage; mirrors bucket if omitted"
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

    # Canonical rule type for downstream evaluator (backward-compatible with unit_basis)
    calculation_type: Optional[Literal[
        "FLAT",
        "PER_UNIT",
        "MIN_OR_PER_UNIT",
        "PERCENT_OF",
        "PER_LINE_WITH_CAP",
        "MAX_OR_PER_UNIT",
    ]] = Field(
        None,
        description="Canonical calculation rule type"
    )

    # Canonical quantity basis for per-unit rules
    unit_type: Optional[Literal["KG", "SHIPMENT", "AWB", "TRIP", "SET", "LINE", "MAN", "CBM", "RT"]] = Field(
        None,
        description="Canonical unit for quantity lookup"
    )

    # Canonical structured rule fields
    rate: Optional[Decimal] = Field(
        None,
        ge=0,
        description="Per-unit or flat rate amount"
    )
    min_amount: Optional[Decimal] = Field(
        None,
        ge=0,
        description="Minimum amount for composite rules"
    )
    max_amount: Optional[Decimal] = Field(
        None,
        ge=0,
        description="Maximum amount for composite rules"
    )
    percent_basis: Optional[str] = Field(
        None,
        description="Basis key for percentage calculations (e.g., FREIGHT)"
    )
    rule_meta: Optional[dict] = Field(
        default_factory=dict,
        description="Extensible rule parameters (e.g., cap thresholds)"
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

    # Confidence produced by normalization/mapping stage
    normalization_confidence: Optional[Literal["HIGH", "LOW"]] = Field(
        None,
        description="Confidence from normalized mapping stage"
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

    @field_validator("rule_meta", mode="before")
    @classmethod
    def coerce_rule_meta(cls, v):
        """Accept null or invalid rule_meta from AI and normalize to empty dict."""
        if v is None:
            return {}
        if isinstance(v, dict):
            return v
        return {}

    @model_validator(mode='after')
    def validate_charge_type(self):
        """Ensure charge has required fields based on unit_basis."""
        unit_type_map = {
            "PER_KG": "KG",
            "PER_SHIPMENT": "SHIPMENT",
            "MIN_OR_PER_KG": "KG",
            "PERCENTAGE": "LINE",
        }

        # Normalize multi-agent mapping fields onto the final output.
        if not self.original_raw_label:
            object.__setattr__(self, "original_raw_label", self.description)
        if self.v4_bucket is None:
            object.__setattr__(self, "v4_bucket", self.bucket)
        elif self.v4_bucket != self.bucket:
            object.__setattr__(self, "bucket", self.v4_bucket)
        
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

        # Canonical mapping for downstream rule engine (backward-compatible)
        if self.unit_type is None:
            object.__setattr__(self, "unit_type", unit_type_map.get(self.unit_basis, "SHIPMENT"))

        if self.calculation_type is None:
            if self.unit_basis == "MIN_OR_PER_KG":
                object.__setattr__(self, "calculation_type", "MIN_OR_PER_UNIT")
            elif self.unit_basis == "PER_KG":
                object.__setattr__(self, "calculation_type", "PER_UNIT")
            elif self.unit_basis == "PERCENTAGE":
                object.__setattr__(self, "calculation_type", "PERCENT_OF")
            else:
                object.__setattr__(self, "calculation_type", "FLAT")

        if self.rate is None:
            if self.unit_basis in {"PER_KG", "MIN_OR_PER_KG"}:
                object.__setattr__(self, "rate", self.rate_per_unit or self.amount)
            else:
                object.__setattr__(self, "rate", self.amount)

        if self.min_amount is None and (self.minimum is not None or self.amount is not None):
            if self.unit_basis == "MIN_OR_PER_KG":
                object.__setattr__(self, "min_amount", self.minimum or self.amount)

        if self.max_amount is None and self.maximum is not None:
            object.__setattr__(self, "max_amount", self.maximum)

        if self.percent_basis is None and self.percent_applies_to is not None:
            object.__setattr__(self, "percent_basis", self.percent_applies_to)

        if self.rule_meta is None:
            object.__setattr__(self, "rule_meta", {})
        
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
                "original_raw_label": "Pick-up",
                "v4_product_code": "PICKUP",
                "v4_bucket": "ORIGIN",
                "amount": "85.00",
                "currency": "AUD",
                "unit_basis": "PER_SHIPMENT",
                "minimum": "85.00",
                "notes": "Extracted from 'Pick-up: AUD85.00'"
            }
        }


class QuoteInputPayload(BaseModel):
    """Validated AI-produced pricing input handed to the pricing engines."""

    quote_currency: Optional[str] = Field(
        None,
        description="Detected quote currency for the imported rate sheet.",
    )
    charge_lines: List[SpotChargeLine] = Field(
        default_factory=list,
        description="Structured charge inputs ready for downstream engine pricing.",
    )


# =============================================================================
# MULTI-AGENT PIPELINE STAGE SCHEMAS
# =============================================================================

class RawExtractedCharge(BaseModel):
    """Raw charge candidate emitted by the extraction agent."""

    raw_label: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Raw label text as extracted from the quote"
    )
    raw_amount_string: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Unparsed amount text exactly as extracted (e.g., 'AUD 85.00 min')"
    )
    currency_hint: Optional[str] = Field(
        None,
        max_length=10,
        description="Optional currency hint from extraction stage (e.g., 'AUD', '$')"
    )
    is_conditional: bool = Field(
        default=False,
        description="True if raw text indicates the charge is conditional/optional"
    )

    @field_validator("currency_hint")
    @classmethod
    def normalize_currency_hint(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip()
        return v.upper() if len(v) == 3 else v


class NormalizedCharge(BaseModel):
    """Normalized and mapped charge candidate emitted by the mapping agent."""

    original_raw_label: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Original raw label that was normalized"
    )
    v4_product_code: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Mapped v4 product code, or 'UNMAPPED'"
    )
    v4_bucket: SpotChargeBucket = Field(
        ...,
        description="Mapped v4 charge bucket"
    )
    unit_basis: UnitBasis = Field(
        ...,
        description="Normalized charging basis"
    )
    amount: Decimal = Field(
        ...,
        ge=0,
        description="Primary normalized amount (flat amount, per-kg rate, or duplicated percentage/per-kg-rate for composite rules)"
    )
    rate_per_unit: Optional[Decimal] = Field(
        None,
        ge=0,
        description="Per-unit rate for PER_KG and MIN_OR_PER_KG"
    )
    minimum_amount: Optional[Decimal] = Field(
        None,
        ge=0,
        description="Minimum amount for MIN_OR_PER_KG"
    )
    percentage: Optional[Decimal] = Field(
        None,
        ge=0,
        le=100,
        description="Percentage value for PERCENTAGE charges"
    )
    percent_applies_to: Optional[str] = Field(
        None,
        max_length=100,
        description="Basis/component the percentage applies to"
    )
    currency: str = Field(
        ...,
        min_length=3,
        max_length=3,
        description="Normalized ISO 4217 currency code"
    )
    confidence: Literal["HIGH", "LOW"] = Field(
        ...,
        description="Normalization confidence"
    )

    @field_validator("currency")
    @classmethod
    def validate_normalized_currency(cls, v: str) -> str:
        return v.upper()

    @model_validator(mode="after")
    def validate_by_unit_basis(self):
        """Enforce specialized fields for percentage and min-or-per-kg rules."""
        if self.unit_basis == "PER_KG" and self.rate_per_unit is None:
            object.__setattr__(self, "rate_per_unit", self.amount)

        if self.unit_basis == "PERCENTAGE":
            if self.percentage is None:
                object.__setattr__(self, "percentage", self.amount)

        if self.unit_basis == "MIN_OR_PER_KG":
            if self.rate_per_unit is None:
                object.__setattr__(self, "rate_per_unit", self.amount)

        return self


class ExtractionAuditResult(BaseModel):
    """Audit outcome from the QA/safety agent."""

    is_safe_to_proceed: bool = Field(
        ...,
        description="True if extraction/normalization is safe to proceed to final validation"
    )
    missed_charges: List[str] = Field(
        default_factory=list,
        description="Charge labels or notes the audit agent believes were missed"
    )
    hallucinations_detected: List[str] = Field(
        default_factory=list,
        description="Items detected as likely hallucinated charges or unsupported values"
    )


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
