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
from pydantic import BaseModel, Field, computed_field


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
    # AssertionCategory.VALIDITY,
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
    rate_amount: Optional[Decimal] = Field(None, description="Flat amount or minimum for MIN_OR_PER_KG")
    rate_per_unit: Optional[Decimal] = Field(None, description="Per-unit rate (e.g., per kg)")
    rate_currency: Optional[str] = Field(None)
    rate_unit: Optional[str] = Field(None, description="per_kg, flat, min_or_per_kg, etc.")
    percentage_basis: Optional[str] = Field(None, description="What the percentage applies to")
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
    
    @computed_field
    @property
    def can_proceed(self) -> bool:
        """True if all mandatory fields are present (any status except MISSING)."""
        # Validity is no longer blocking - only rate and currency required
        return self.has_rate and self.has_currency
    
    @computed_field
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
    
    @computed_field
    @property
    def requires_acknowledgement(self) -> bool:
        """True if any assertions are IMPLICIT or CONDITIONAL."""
        return self.conditional_count > 0 or self.implicit_count > 0


class AnalysisSafetySignals(BaseModel):
    """Structured safety metadata derived from AI intake and critic output."""

    raw_charge_count: int = 0
    normalized_charge_count: int = 0
    imported_charge_count: int = 0
    unmapped_line_count: int = 0
    low_confidence_line_count: int = 0
    conditional_charge_count: int = 0
    critic_safe_to_proceed: Optional[bool] = None
    critic_missed_charges: List[str] = Field(default_factory=list)
    critic_hallucinations: List[str] = Field(default_factory=list)
    pdf_fallback_used: bool = False


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
    safety_signals: AnalysisSafetySignals = Field(
        default_factory=AnalysisSafetySignals,
        description="Structured AI safety metadata used for review gating"
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
