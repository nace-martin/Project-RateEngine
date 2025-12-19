# backend/quotes/spot_schemas.py
"""
SPOT Mode Pydantic Schemas

AI Extraction Output (untrusted, assistive only):
- AIExtractedCharge
- AISpotExtractionResult

Spot Pricing Envelope (authoritative):
- SPEShipmentContext (frozen, immutable)
- SPEChargeLine
- SPEConditions
- SPEAcknowledgement
- SPEManagerApproval
- SpotPricingEnvelope

Hard Guardrails (model-level):
- PNG-only scope validation
- Exactly one primary airfreight charge
- Shipment context hash for integrity verification
"""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import List, Optional, Literal
import hashlib
import json

from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict


# =============================================================================
# ENUMS
# =============================================================================

class SPEStatus(str, Enum):
    """SPE lifecycle status."""
    DRAFT = "draft"
    READY = "ready"
    EXPIRED = "expired"
    REJECTED = "rejected"


class ChargeBucket(str, Enum):
    """Canonical charge buckets - locked enum, UI cannot fudge."""
    AIRFREIGHT = "airfreight"
    ORIGIN_CHARGES = "origin_charges"
    DESTINATION_CHARGES = "destination_charges"


class ChargeUnit(str, Enum):
    """Charge unit basis."""
    PER_KG = "per_kg"
    FLAT = "flat"
    PER_AWB = "per_awb"
    PER_SHIPMENT = "per_shipment"
    PERCENTAGE = "percentage"
    UNKNOWN = "unknown"


class Commodity(str, Enum):
    """
    Commodity types based on EFM cargo classification.
    
    GCR = General Cargo (normal pricing)
    All others = Special Cargo (SPOT mode required)
    """
    # General Cargo - deterministic pricing possible
    GCR = "GCR"   # Electronics, textiles, hardware, consumer goods, etc.
    
    # Special Cargo - SPOT mode required
    SCR = "SCR"   # Special Cargo (catch-all)
    DG = "DG"     # Dangerous Goods (explosives, gases, flammables, toxics, etc.)
    AVI = "AVI"   # Live Animals (pets, livestock, day-old chicks)
    PER = "PER"   # Perishables (flowers, produce, seafood, vaccines)
    HVC = "HVC"   # High Value Cargo (gold, diamonds, art, luxury goods)
    HUM = "HUM"   # Human Remains (cremated or uncremated)
    OOG = "OOG"   # Oversized/Heavy (aircraft parts, large machinery)
    VUL = "VUL"   # Vulnerable Cargo (phones, SIMs, brand clothing)
    TTS = "TTS"   # Time/Temp Sensitive (pharma, medical supplies)
    
    OTHER = "OTHER"


class Currency(str, Enum):
    """Supported currencies."""
    USD = "USD"
    AUD = "AUD"
    PGK = "PGK"


# =============================================================================
# AI EXTRACTION OUTPUT SCHEMAS (Untrusted, Assistive Only)
# =============================================================================

class AIExtractedCharge(BaseModel):
    """
    Single charge line extracted by AI from unstructured text.
    
    This is UNTRUSTED input. AI output feeds UI review only.
    AI must NOT:
    - Price shipments
    - Apply margins
    - Confirm acceptance
    - Decide SPOT vs normal mode
    """
    raw_text: str = Field(
        description="Exact text snippet from the source message"
    )
    
    amount: Optional[float] = Field(
        default=None,
        description="Numeric value if present, else null"
    )
    
    currency: Optional[Literal["USD", "AUD", "PGK"]] = None
    
    unit: Literal[
        "per_kg",
        "flat",
        "per_awb",
        "per_shipment",
        "percentage",
        "unknown"
    ] = "unknown"
    
    suggested_code: Optional[str] = Field(
        default=None,
        description="LLM-suggested canonical code (non-authoritative)"
    )
    
    suggested_bucket: Literal[
        "airfreight",
        "origin_charges",
        "destination_charges",
        "unknown"
    ] = "unknown"
    
    conditional: bool = Field(
        default=False,
        description="True if language indicates conditionality (e.g. 'if required')"
    )
    
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="LLM confidence in its own suggestion"
    )


class AISpotExtractionResult(BaseModel):
    """
    Complete AI extraction response.
    
    This model:
    - Does NOT calculate totals
    - Does NOT decide SPOT vs normal
    - Does NOT confirm anything
    
    It only *suggests*.
    """
    source_type: Literal["email", "pdf", "text"]
    extracted_at: datetime
    
    charges: List[AIExtractedCharge] = Field(default_factory=list)
    
    warnings: List[str] = Field(
        default_factory=list,
        description="LLM-identified ambiguities or missing context"
    )
    
    notes: Optional[str] = Field(
        default=None,
        description="Free-form notes highlighting uncertainty"
    )


# =============================================================================
# SPOT PRICING ENVELOPE (SPE) — AUTHORITATIVE MODELS
# =============================================================================

class SPEShipmentContext(BaseModel):
    """
    Immutable shipment context. Cannot be changed after SPE creation.
    
    Frozen model - any mutation attempt raises an error.
    Includes context_hash for integrity verification.
    """
    model_config = ConfigDict(frozen=True)
    
    origin_country: Literal["PG", "AU", "US", "SG", "NZ", "ID", "PH", "JP", "CN", "HK", "OTHER"]
    destination_country: Literal["PG", "AU", "US", "SG", "NZ", "ID", "PH", "JP", "CN", "HK", "OTHER"]
    
    origin_code: str = Field(min_length=3, max_length=3)
    destination_code: str = Field(min_length=3, max_length=3)
    
    commodity: Literal["GCR", "SCR", "DG", "AVI", "PER", "HVC", "HUM", "OOG", "VUL", "TTS", "OTHER"]
    
    total_weight_kg: float = Field(gt=0)
    pieces: int = Field(ge=1)
    
    @property
    def context_hash(self) -> str:
        """
        SHA256 hash of normalized context for integrity verification.
        
        Protects against accidental update-in-place if stored in JSONField.
        """
        normalized = json.dumps({
            "origin_country": self.origin_country,
            "destination_country": self.destination_country,
            "origin_code": self.origin_code,
            "destination_code": self.destination_code,
            "commodity": self.commodity,
            "total_weight_kg": self.total_weight_kg,
            "pieces": self.pieces,
        }, sort_keys=True)
        return hashlib.sha256(normalized.encode()).hexdigest()


class SPEChargeLine(BaseModel):
    """
    Authoritative charge line in SPE.
    
    Requires source + timestamp. Anonymous values rejected.
    """
    code: str = Field(
        description="Canonical internal charge code (e.g., AIRFREIGHT_SPOT)"
    )
    
    description: str
    
    amount: float = Field(gt=0)
    currency: Literal["USD", "AUD", "PGK"]
    
    unit: Literal[
        "per_kg",
        "flat",
        "per_awb",
        "per_shipment",
        "percentage"
    ]
    
    bucket: Literal["airfreight", "origin_charges", "destination_charges"]
    
    is_primary_cost: bool = Field(
        default=False,
        description="True if this is the primary airfreight cost line"
    )
    
    conditional: bool = False
    
    source_reference: str = Field(
        min_length=1,
        description="Email ID, filename, or manual note - REQUIRED"
    )
    
    entered_by_user_id: str
    entered_at: datetime


class SPEConditions(BaseModel):
    """
    Explicit uncertainty tracking.
    
    These conditions affect final pricing and execution.
    They must be acknowledged before proceeding.
    """
    space_not_confirmed: bool = True
    airline_acceptance_not_confirmed: bool = True
    rate_validity_hours: int = Field(default=72, ge=1, le=168)
    conditional_charges_present: bool = False
    
    notes: Optional[str] = None


class SPEAcknowledgement(BaseModel):
    """
    Sales acknowledgement. Required before pricing can proceed.
    """
    acknowledged_by_user_id: str
    acknowledged_at: datetime
    
    statement: Literal[
        "I acknowledge this is a conditional SPOT quote and not guaranteed"
    ]


class SPEManagerApproval(BaseModel):
    """
    Manager approval gate. Required for high-risk SPOT quotes.
    """
    approved: bool
    manager_user_id: str
    decision_at: datetime
    comment: Optional[str] = None


class SpotPricingEnvelope(BaseModel):
    """
    Main SPE container with hard guardrails.
    
    Guardrails enforced at model level:
    1. PNG-only scope (origin OR destination must be PG)
    2. Exactly one primary airfreight charge
    3. Spot trigger reason persisted for audit trail
    """
    id: str
    status: SPEStatus
    
    shipment: SPEShipmentContext
    
    charges: List[SPEChargeLine]
    
    conditions: SPEConditions
    
    acknowledgement: Optional[SPEAcknowledgement] = None
    manager_approval: Optional[SPEManagerApproval] = None
    
    # Audit trail: persist the reason SPOT was triggered (Tweak #5)
    spot_trigger_reason_code: str = Field(
        description="Machine-readable trigger code for policy/reporting"
    )
    spot_trigger_reason_text: str = Field(
        description="Human-readable trigger reason for UI display"
    )
    
    created_by_user_id: str
    created_at: datetime
    
    expires_at: datetime
    
    @model_validator(mode='after')
    def enforce_png_scope(self) -> 'SpotPricingEnvelope':
        """
        GUARDRAIL 1: PNG-only scope.
        
        RateEngine only supports shipments TO or FROM Papua New Guinea.
        If both origin and destination are outside PNG, reject outright.
        """
        origin = self.shipment.origin_country
        dest = self.shipment.destination_country
        
        if origin != "PG" and dest != "PG":
            raise ValueError(
                "Out of scope: RateEngine only supports shipments to or from "
                "Papua New Guinea (PNG). This shipment cannot be quoted."
            )
        
        return self
    
    @model_validator(mode='after')
    def enforce_single_primary_airfreight(self) -> 'SpotPricingEnvelope':
        """
        GUARDRAIL 2: Exactly one primary airfreight charge.
        
        Uses is_primary_cost=True OR code==AIRFREIGHT_SPOT to identify.
        Prevents slipping in two "airfreight-ish" lines.
        """
        primary_charges = [
            c for c in self.charges
            if c.is_primary_cost or c.code == "AIRFREIGHT_SPOT"
        ]
        
        if len(primary_charges) == 0:
            raise ValueError(
                "SPE requires exactly one primary airfreight charge. "
                "No charge with is_primary_cost=True or code='AIRFREIGHT_SPOT' found."
            )
        
        if len(primary_charges) > 1:
            raise ValueError(
                f"SPE requires exactly one primary airfreight charge. "
                f"Found {len(primary_charges)} charges marked as primary. "
                "Only one is allowed."
            )
        
        return self
    
    @property
    def is_expired(self) -> bool:
        """Check if SPE has expired."""
        return datetime.now() >= self.expires_at
    
    @property
    def shipment_context_hash(self) -> str:
        """Get hash of shipment context for integrity verification."""
        return self.shipment.context_hash
