# backend/quotes/reply_schemas.py
"""
Agent Reply Analysis Schemas

Structures for extracting, classifying, and building SPE from agent rate replies.

4-Bucket Classification:
- CONFIRMED: Explicit, unconditional statements
- CONDITIONAL: "Subject to", "if required", etc.
- IMPLICIT: Implied but not stated (danger zone)
- MISSING: Expected but absent

Field Rules:
- MANDATORY (missing = block): rate, currency, validity
- OPTIONAL (missing = warn): routing, acceptance, charges
"""

from enum import Enum
from typing import Optional, List
from decimal import Decimal
from pydantic import BaseModel, Field


class AssertionStatus(str, Enum):
    """Classification of certainty for extracted assertions."""
    CONFIRMED = "confirmed"       # Explicit, unconditional
    CONDITIONAL = "conditional"   # "Subject to", "if required"
    IMPLICIT = "implicit"         # Implied but not stated
    MISSING = "missing"           # Expected but absent


class AssertionCategory(str, Enum):
    """Categories of information we expect in agent replies."""
    # Mandatory fields (missing = block)
    RATE = "rate"                 # Airfreight rate per kg
    CURRENCY = "currency"         # Rate currency
    VALIDITY = "validity"         # Rate validity period
    
    # Optional fields (missing = warn)
    ROUTING = "routing"           # Routing / legs  
    ACCEPTANCE = "acceptance"     # Space/acceptance confirmation
    ORIGIN_CHARGES = "origin_charges"   # Origin charges
    DEST_CHARGES = "dest_charges"       # Destination charges
    CONDITIONS = "conditions"     # Conditions or exclusions
    TRANSIT_TIME = "transit_time" # Estimated transit time


# Fields that MUST be present to proceed
MANDATORY_CATEGORIES = {
    AssertionCategory.RATE,
    AssertionCategory.CURRENCY,
    AssertionCategory.VALIDITY,
}

# Fields that are nice to have
OPTIONAL_CATEGORIES = {
    AssertionCategory.ROUTING,
    AssertionCategory.ACCEPTANCE,
    AssertionCategory.ORIGIN_CHARGES,
    AssertionCategory.DEST_CHARGES,
    AssertionCategory.CONDITIONS,
    AssertionCategory.TRANSIT_TIME,
}


class ExtractedAssertion(BaseModel):
    """Single claim extracted from agent reply."""
    
    text: str = Field(
        ...,
        description="Original text snippet from the reply"
    )
    category: AssertionCategory = Field(
        ...,
        description="What type of information this is"
    )
    value: Optional[str] = Field(
        None,
        description="Parsed/normalized value if applicable"
    )
    status: AssertionStatus = Field(
        ...,
        description="Classification of certainty"
    )
    confidence: float = Field(
        1.0,
        ge=0.0,
        le=1.0,
        description="AI confidence score (1.0 for manual entry)"
    )
    source_line: Optional[int] = Field(
        None,
        description="Line number in original text"
    )
    
    # Parsed values for specific categories
    rate_amount: Optional[Decimal] = Field(None)
    rate_currency: Optional[str] = Field(None)
    rate_unit: Optional[str] = Field(None, description="per_kg, flat, etc.")
    validity_date: Optional[str] = Field(None, description="ISO date string")


class AnalysisSummary(BaseModel):
    """Quick status check of analysis results."""
    
    confirmed_count: int = 0
    conditional_count: int = 0
    implicit_count: int = 0
    missing_count: int = 0
    
    # Required field status
    has_rate: bool = False
    has_currency: bool = False
    has_validity: bool = False
    
    # Optional field status
    has_routing: bool = False
    has_acceptance: bool = False
    
    @property
    def can_proceed(self) -> bool:
        """True if all mandatory fields are present (any status except MISSING)."""
        return self.has_rate and self.has_currency and self.has_validity
    
    @property
    def mandatory_missing(self) -> List[str]:
        """List of mandatory fields that are missing."""
        missing = []
        if not self.has_rate:
            missing.append("rate")
        if not self.has_currency:
            missing.append("currency")
        if not self.has_validity:
            missing.append("validity")
        return missing
    
    @property
    def requires_acknowledgement(self) -> bool:
        """True if any assertions are IMPLICIT or CONDITIONAL."""
        return self.conditional_count > 0 or self.implicit_count > 0


class ReplyAnalysisResult(BaseModel):
    """Full analysis of an agent reply."""
    
    raw_text: str = Field(
        ...,
        description="Original pasted reply text"
    )
    assertions: List[ExtractedAssertion] = Field(
        default_factory=list,
        description="Extracted assertions with classifications"
    )
    summary: AnalysisSummary = Field(
        default_factory=AnalysisSummary,
        description="Quick status check"
    )
    warnings: List[str] = Field(
        default_factory=list,
        description="User-facing warnings about the analysis"
    )
    
    @property
    def can_proceed(self) -> bool:
        """True if SPE can be built from this analysis."""
        return self.summary.can_proceed
    
    @property
    def blocked_reason(self) -> Optional[str]:
        """Reason why SPE cannot be built, if blocked."""
        if self.summary.can_proceed:
            return None
        missing = self.summary.mandatory_missing
        return f"Missing required fields: {', '.join(missing)}"


class ManualAssertionInput(BaseModel):
    """Input for manually adding an assertion."""
    
    text: str = Field(..., min_length=1)
    category: AssertionCategory
    status: AssertionStatus
    value: Optional[str] = None
    rate_amount: Optional[Decimal] = None
    rate_currency: Optional[str] = None
    rate_unit: Optional[str] = None
    validity_date: Optional[str] = None


class ReplyAnalysisRequest(BaseModel):
    """Request to analyze a pasted agent reply."""
    
    text: str = Field(
        ...,
        min_length=10,
        description="Raw agent reply text"
    )
    use_ai: bool = Field(
        False,
        description="Whether to use AI extraction (Phase 2)"
    )
