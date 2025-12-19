# backend/quotes/spot_services.py
"""
SPOT Mode Business Logic Services

ScopeValidator:
    PNG-only enforcement at request boundary.
    Must be called BEFORE any SPOT logic.

SpotTriggerEvaluator:
    Centralised SPOT trigger logic.
    Returns explicit reason when SPOT is required.

SpotEnvelopeService:
    SPE lifecycle: create, validate, acknowledge, approve, expire.

SpotApprovalPolicy:
    Manager approval thresholds as policy, not if-statements.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Optional, Tuple, List
from uuid import uuid4

from django.conf import settings

from quotes.spot_schemas import (
    SpotPricingEnvelope,
    SPEShipmentContext,
    SPEChargeLine,
    SPEConditions,
    SPEAcknowledgement,
    SPEManagerApproval,
    SPEStatus,
)


# =============================================================================
# SPOT TRIGGER REASON CODES (Tweak #5 - Audit Trail)
# =============================================================================

class SpotTriggerReason:
    """Machine-readable SPOT trigger reason codes."""
    # Special cargo commodities
    SCR_COMMODITY = "SCR_COMMODITY"  # Special Cargo (catch-all)
    DG_COMMODITY = "DG_COMMODITY"    # Dangerous Goods
    AVI_COMMODITY = "AVI_COMMODITY"  # Live Animals
    PER_COMMODITY = "PER_COMMODITY"  # Perishables
    HVC_COMMODITY = "HVC_COMMODITY"  # High Value Cargo
    HUM_COMMODITY = "HUM_COMMODITY"  # Human Remains
    OOG_COMMODITY = "OOG_COMMODITY"  # Oversized/Heavy
    VUL_COMMODITY = "VUL_COMMODITY"  # Vulnerable Cargo
    TTS_COMMODITY = "TTS_COMMODITY"  # Time/Temp Sensitive
    
    # Route and rate issues
    NON_PX_ROUTE = "NON_PX_ROUTE"
    MISSING_COGS = "MISSING_COGS"
    MISSING_SELL = "MISSING_SELL"
    MULTI_LEG_ROUTING = "MULTI_LEG_ROUTING"
    NO_BUY_RATE = "NO_BUY_RATE"
    REQUIRES_ASSUMPTIONS = "REQUIRES_ASSUMPTIONS"


@dataclass
class TriggerResult:
    """Result of SPOT trigger evaluation."""
    code: str
    text: str


# =============================================================================
# SCOPE VALIDATOR (Tweak #1 - Request Boundary Enforcement)
# =============================================================================

class ScopeValidator:
    """
    PNG-only scope enforcement.
    
    MUST be called at the request boundary BEFORE any SPOT logic.
    This prevents:
    - Wasted AI calls
    - Draft SPE creation for invalid shipments
    - Scope creep by accident
    """
    
    # Papua New Guinea country code
    PNG_COUNTRY_CODE = "PG"
    
    @classmethod
    def validate(
        cls,
        origin_country: str,
        destination_country: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate shipment is within PNG scope.
        
        Args:
            origin_country: ISO 2-letter country code
            destination_country: ISO 2-letter country code
            
        Returns:
            (is_valid, error_message)
            - (True, None) if valid
            - (False, "error message") if out of scope
        """
        if origin_country == cls.PNG_COUNTRY_CODE:
            return True, None
        
        if destination_country == cls.PNG_COUNTRY_CODE:
            return True, None
        
        return False, (
            f"Out of scope: RateEngine only supports shipments to or from "
            f"Papua New Guinea (PNG). Received {origin_country} → {destination_country}. "
            f"No pricing can be generated for this route."
        )


# =============================================================================
# SPOT TRIGGER EVALUATOR
# =============================================================================

class SpotTriggerEvaluator:
    """
    Centralised SPOT trigger logic.
    
    Returns a single explicit reason string when SPOT is required.
    
    SPOT Mode is triggered when ANY of the following are true:
    - Commodity = Dangerous Goods (DG)
    - Commodity = International Live Animals (AVI)
    - Commodity = International Perishables (PER)
    - Export route not flown directly by Air Niugini (PX)
    - Import D2A route with missing COGS or SELL rates
    - Multi-leg or interline routing required
    - No valid BUY rate exists
    - Pricing requires assumptions not encoded in rules
    """
    
    # Air Niugini (PX) direct destinations from PNG
    PX_DIRECT_DESTINATIONS = {
        "AU": ["BNE", "SYD", "CNS"],  # Brisbane, Sydney, Cairns
        "PH": ["MNL"],                 # Manila
        "SG": ["SIN"],                 # Singapore
        "JP": ["NRT", "HND"],          # Tokyo
        "HK": ["HKG"],                 # Hong Kong
        "ID": ["CGK"],                 # Jakarta
        "FJ": ["SUV"],                 # Suva
        "SB": ["HIR"],                 # Honiara
        "PG": ["POM", "LAE", "RAB", "WWK", "GKA", "HGU", "MAS"],  # Domestic PNG
    }
    
    @classmethod
    def evaluate(
        cls,
        origin_country: str,
        destination_country: str,
        commodity: str,
        origin_airport: Optional[str] = None,
        destination_airport: Optional[str] = None,
        has_valid_buy_rate: bool = True,
        has_valid_cogs: bool = True,
        has_valid_sell: bool = True,
        is_multi_leg: bool = False,
    ) -> Tuple[bool, Optional[TriggerResult]]:
        """
        Evaluate whether SPOT mode is required.
        
        Args:
            origin_country: Origin country code
            destination_country: Destination country code
            commodity: Commodity type (GCR, DG, AVI, PER, OTHER)
            origin_airport: Origin airport IATA code
            destination_airport: Destination airport IATA code
            has_valid_buy_rate: Whether valid BUY rate exists
            has_valid_cogs: Whether COGS data exists
            has_valid_sell: Whether SELL rate exists
            is_multi_leg: Whether multi-leg routing required
            
        Returns:
            (is_spot_required, trigger_result)
            - (True, TriggerResult) if SPOT required
            - (False, None) if normal pricing applies
        """
        # Check commodity triggers - any special cargo triggers SPOT
        # Map of commodity codes to their trigger info
        SPECIAL_CARGO_TRIGGERS = {
            "SCR": (SpotTriggerReason.SCR_COMMODITY, "Special Cargo (SCR)"),
            "DG": (SpotTriggerReason.DG_COMMODITY, "Dangerous Goods (DG)"),
            "AVI": (SpotTriggerReason.AVI_COMMODITY, "Live Animals (AVI)"),
            "PER": (SpotTriggerReason.PER_COMMODITY, "Perishables (PER)"),
            "HVC": (SpotTriggerReason.HVC_COMMODITY, "High Value Cargo (HVC)"),
            "HUM": (SpotTriggerReason.HUM_COMMODITY, "Human Remains (HUM)"),
            "OOG": (SpotTriggerReason.OOG_COMMODITY, "Oversized/Heavy (OOG)"),
            "VUL": (SpotTriggerReason.VUL_COMMODITY, "Vulnerable Cargo (VUL)"),
            "TTS": (SpotTriggerReason.TTS_COMMODITY, "Time/Temp Sensitive (TTS)"),
        }
        
        if commodity in SPECIAL_CARGO_TRIGGERS:
            code, label = SPECIAL_CARGO_TRIGGERS[commodity]
            return True, TriggerResult(
                code=code,
                text=f"Commodity = {label}. Manual rate sourcing required."
            )
        
        # Check export route (from PNG to non-PX destination)
        if origin_country == "PG" and destination_country != "PG":
            if not cls._is_px_direct_route(destination_country, destination_airport):
                return True, TriggerResult(
                    code=SpotTriggerReason.NON_PX_ROUTE,
                    text="Export route not flown directly by Air Niugini (PX). "
                         "Manual rate sourcing per leg is required."
                )
        
        # Check missing rate data
        if not has_valid_buy_rate:
            return True, TriggerResult(
                code=SpotTriggerReason.NO_BUY_RATE,
                text="No valid BUY rate exists for this route. Manual rate sourcing required."
            )
        
        if not has_valid_cogs:
            return True, TriggerResult(
                code=SpotTriggerReason.MISSING_COGS,
                text="Missing COGS data for this route. Manual rate sourcing required."
            )
        
        if not has_valid_sell:
            return True, TriggerResult(
                code=SpotTriggerReason.MISSING_SELL,
                text="Missing SELL rate for this route. Manual rate sourcing required."
            )
        
        # Check multi-leg routing
        if is_multi_leg:
            return True, TriggerResult(
                code=SpotTriggerReason.MULTI_LEG_ROUTING,
                text="Multi-leg or interline routing required. Manual rate sourcing required."
            )
        
        # No SPOT trigger - normal pricing applies
        return False, None
    
    @classmethod
    def _is_px_direct_route(
        cls,
        destination_country: str,
        destination_airport: Optional[str]
    ) -> bool:
        """Check if destination is served directly by Air Niugini."""
        if destination_country not in cls.PX_DIRECT_DESTINATIONS:
            return False
        
        if destination_airport is None:
            # If no specific airport, assume not direct
            # (conservative approach - triggers SPOT for review)
            return False
        
        return destination_airport in cls.PX_DIRECT_DESTINATIONS[destination_country]


# =============================================================================
# SPOT ENVELOPE SERVICE (Tweak #3 - Lifecycle Enforcement)
# =============================================================================

class SpotEnvelopeService:
    """
    SPE lifecycle management.
    
    Enforces:
    - Status must be READY before pricing
    - SPE must not be expired
    - Acknowledgement must be present
    - Manager approval required when thresholds exceeded
    """
    
    @classmethod
    def validate_for_pricing(
        cls,
        spe: SpotPricingEnvelope
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate SPE is ready for pricing.
        
        Returns (is_valid, error_message).
        Returns is_incomplete=true with reason string. No 500s.
        """
        # Check status
        if spe.status != SPEStatus.READY:
            return False, (
                f"SPE status is '{spe.status.value}', must be 'ready' for pricing. "
                f"Complete all required steps before proceeding."
            )
        
        # Check expiry
        if spe.is_expired:
            return False, (
                f"SPE has expired at {spe.expires_at.isoformat()}. "
                f"SPOT quotes are non-reusable after expiry. "
                f"Create a new SPOT quote with fresh rates."
            )
        
        # Check acknowledgement
        if spe.acknowledgement is None:
            return False, (
                "Sales acknowledgement is required before pricing can proceed. "
                "Acknowledge the conditions and uncertainty before continuing."
            )
        
        # Check manager approval if required
        if cls._requires_manager_approval(spe) and spe.manager_approval is None:
            return False, (
                "Manager approval is required for this SPOT quote but has not been provided. "
                f"Reason: {cls._get_approval_reason(spe)}"
            )
        
        if spe.manager_approval is not None and not spe.manager_approval.approved:
            return False, (
                "Manager has rejected this SPOT quote. "
                f"Reason: {spe.manager_approval.comment or 'No comment provided'}"
            )
        
        return True, None
    
    @classmethod
    def _requires_manager_approval(cls, spe: SpotPricingEnvelope) -> bool:
        """Check if SPE requires manager approval per policy."""
        return SpotApprovalPolicy.requires_manager_approval(
            commodity=spe.shipment.commodity,
            margin_percent=None,  # Not calculated yet at this stage
            is_multi_leg=spe.spot_trigger_reason_code == SpotTriggerReason.MULTI_LEG_ROUTING,
            trigger_code=spe.spot_trigger_reason_code
        )
    
    @classmethod
    def _get_approval_reason(cls, spe: SpotPricingEnvelope) -> str:
        """Get human-readable reason for required approval."""
        reasons = []
        
        if spe.shipment.commodity == "DG":
            reasons.append("Dangerous Goods shipment")
        
        if spe.spot_trigger_reason_code == SpotTriggerReason.MULTI_LEG_ROUTING:
            reasons.append("Multi-leg routing")
        
        return ", ".join(reasons) if reasons else "Policy requires approval"
    
    @classmethod
    def create_envelope(
        cls,
        shipment: SPEShipmentContext,
        charges: List[SPEChargeLine],
        conditions: SPEConditions,
        trigger_code: str,
        trigger_text: str,
        created_by_user_id: str,
        validity_hours: int = 72,
    ) -> SpotPricingEnvelope:
        """
        Create a new SPE in DRAFT status.
        
        The envelope must be acknowledged and approved (if required)
        before transitioning to READY status.
        """
        now = datetime.now()
        
        return SpotPricingEnvelope(
            id=str(uuid4()),
            status=SPEStatus.DRAFT,
            shipment=shipment,
            charges=charges,
            conditions=conditions,
            acknowledgement=None,
            manager_approval=None,
            spot_trigger_reason_code=trigger_code,
            spot_trigger_reason_text=trigger_text,
            created_by_user_id=created_by_user_id,
            created_at=now,
            expires_at=now + timedelta(hours=validity_hours),
        )
    
    @classmethod
    def acknowledge(
        cls,
        spe: SpotPricingEnvelope,
        user_id: str,
    ) -> SpotPricingEnvelope:
        """Add Sales acknowledgement to SPE."""
        if spe.status != SPEStatus.DRAFT:
            raise ValueError(f"Cannot acknowledge SPE in status '{spe.status.value}'")
        
        return SpotPricingEnvelope(
            **{
                **spe.model_dump(),
                "acknowledgement": SPEAcknowledgement(
                    acknowledged_by_user_id=user_id,
                    acknowledged_at=datetime.now(),
                    statement="I acknowledge this is a conditional SPOT quote and not guaranteed"
                ),
            }
        )
    
    @classmethod
    def approve(
        cls,
        spe: SpotPricingEnvelope,
        manager_user_id: str,
        approved: bool,
        comment: Optional[str] = None,
    ) -> SpotPricingEnvelope:
        """Add Manager approval to SPE."""
        return SpotPricingEnvelope(
            **{
                **spe.model_dump(),
                "manager_approval": SPEManagerApproval(
                    approved=approved,
                    manager_user_id=manager_user_id,
                    decision_at=datetime.now(),
                    comment=comment,
                ),
                "status": SPEStatus.READY if approved else SPEStatus.REJECTED,
            }
        )
    
    @classmethod
    def mark_ready(cls, spe: SpotPricingEnvelope) -> SpotPricingEnvelope:
        """
        Transition SPE to READY status.
        
        Only valid if:
        - Currently in DRAFT
        - Acknowledgement present
        - Manager approval present (if required)
        """
        if spe.status != SPEStatus.DRAFT:
            raise ValueError(f"Cannot mark SPE as ready from status '{spe.status.value}'")
        
        if spe.acknowledgement is None:
            raise ValueError("Cannot mark SPE as ready without acknowledgement")
        
        if cls._requires_manager_approval(spe) and spe.manager_approval is None:
            raise ValueError("Cannot mark SPE as ready - manager approval required")
        
        return SpotPricingEnvelope(
            **{**spe.model_dump(), "status": SPEStatus.READY}
        )


# =============================================================================
# SPOT APPROVAL POLICY (Tweak #6 - Policy, Not If-Statements)
# =============================================================================

class SpotApprovalPolicy:
    """
    Manager approval thresholds as policy configuration.
    
    Can be backed by settings/env for MVP, extensible to DB config later.
    """
    
    # Default policy values (can be overridden via settings)
    DEFAULT_MARGIN_THRESHOLD_PCT = Decimal("15.0")
    
    @classmethod
    def get_config(cls) -> dict:
        """
        Get approval policy configuration.
        
        Extensible to settings/env/database lookup.
        """
        return getattr(settings, 'SPOT_APPROVAL_POLICY', {
            # All special cargo requires approval
            'special_cargo_requires_approval': True,
            'multi_leg_requires_approval': True,
            'margin_below_pct': cls.DEFAULT_MARGIN_THRESHOLD_PCT,
            # Explicit list of commodities requiring approval (all non-GCR)
            'approval_required_commodities': ['SCR', 'DG', 'AVI', 'PER', 'HVC', 'HUM', 'OOG', 'VUL', 'TTS'],
        })
    
    @classmethod
    def requires_manager_approval(
        cls,
        commodity: str,
        margin_percent: Optional[Decimal],
        is_multi_leg: bool = False,
        trigger_code: Optional[str] = None,
    ) -> bool:
        """
        Determine if manager approval is required per policy.
        
        Args:
            commodity: Commodity type
            margin_percent: Calculated margin percentage (may be None if not yet calculated)
            is_multi_leg: Whether multi-leg routing is involved
            trigger_code: SPOT trigger reason code
            
        Returns:
            True if manager approval required
        """
        config = cls.get_config()
        
        # Special cargo commodities require approval
        approval_commodities = config.get(
            'approval_required_commodities', 
            ['SCR', 'DG', 'AVI', 'PER', 'HVC', 'HUM', 'OOG', 'VUL', 'TTS']
        )
        if commodity in approval_commodities and config.get('special_cargo_requires_approval', True):
            return True
        
        # Multi-leg requires approval
        if is_multi_leg and config.get('multi_leg_requires_approval', True):
            return True
        
        # Low margin requires approval
        if margin_percent is not None:
            threshold = Decimal(str(config.get('margin_below_pct', cls.DEFAULT_MARGIN_THRESHOLD_PCT)))
            if margin_percent < threshold:
                return True
        
        return False


# =============================================================================
# SPOT EMAIL DRAFT GENERATOR
# =============================================================================

@dataclass
class SpotEmailDraft:
    """Generated SPOT rate request email draft."""
    subject: str
    body: str


class SpotEmailDraftGenerator:
    """
    Generate standardized SPOT rate request emails.
    
    HARD RULES:
    - No send button
    - No email integration
    - No rate guessing
    - No commitments
    - Only in SPOT mode
    - Never for out-of-scope shipments
    """
    
    # Commodity display names
    COMMODITY_NAMES = {
        'GCR': 'General Cargo',
        'DG': 'Dangerous Goods',
        'PER': 'Perishables',
        'AVI': 'Live Animals',
        'HVC': 'High Value Cargo',
        'HUM': 'Human Remains',
        'OOG': 'Oversized/Heavy',
        'VUL': 'Vulnerable Cargo',
        'TTS': 'Time/Temperature Sensitive',
        'SCR': 'Special Cargo',
    }
    
    @classmethod
    def generate(
        cls,
        origin_code: str,
        destination_code: str,
        commodity: str,
        weight_kg: float,
        pieces: int,
        dimensions: Optional[List[dict]] = None,
        trigger_code: Optional[str] = None,
        user_name: Optional[str] = None,
        recipient_name: Optional[str] = None,
    ) -> SpotEmailDraft:
        """
        Generate a SPOT rate request email draft.
        
        Args:
            origin_code: Airport/location code (e.g., SYD)
            destination_code: Airport/location code (e.g., POM)
            commodity: Commodity code (GCR, DG, PER, etc.)
            weight_kg: Total weight in kg
            pieces: Number of pieces
            dimensions: Optional list of piece dimensions
            trigger_code: SPOT trigger reason code
            user_name: Name for signature
            recipient_name: Agent/carrier name
            
        Returns:
            SpotEmailDraft with subject and body
        """
        # Build subject
        subject = f"SPOT Rate Request – {origin_code} → {destination_code} – {weight_kg}kg Airfreight"
        
        # Resolve names
        sender = user_name or "[Your Name]"
        recipient = recipient_name or "[Agent / Carrier Name]"
        commodity_display = cls.COMMODITY_NAMES.get(commodity, commodity)
        
        # Build dimensions list
        dimensions_text = ""
        if dimensions:
            for i, dim in enumerate(dimensions, 1):
                pcs = dim.get('pieces', 1)
                l = dim.get('length_cm', 0)
                w = dim.get('width_cm', 0)
                h = dim.get('height_cm', 0)
                wt = dim.get('gross_weight_kg', 0)
                dimensions_text += f"  - {pcs}x: {l}×{w}×{h} cm, {wt} kg\n"
        else:
            dimensions_text = f"  - {pieces} piece(s), {weight_kg} kg total\n"
        
        # Build conditional notes
        notes = []
        if commodity == 'DG':
            notes.append("This shipment is Dangerous Goods. Please advise acceptance and surcharges.")
        elif commodity in ('PER', 'AVI', 'TTS'):
            notes.append("This shipment requires special handling. Please advise conditions.")
        elif commodity in ('HVC', 'VUL'):
            notes.append("This shipment contains high-value/vulnerable cargo. Please advise security requirements.")
        elif commodity in ('OOG',):
            notes.append("This shipment is oversized. Please advise dimensional constraints and surcharges.")
        elif commodity == 'HUM':
            notes.append("This shipment contains human remains. Please advise handling requirements.")
        
        # Check for multi-leg trigger
        if trigger_code == 'MULTI_LEG_ROUTING':
            notes.append("If multiple legs apply, please quote per leg.")
        
        notes_text = ""
        if notes:
            notes_text = "\n" + "\n".join(notes) + "\n"
        
        # Build body
        body = f"""Hi {recipient},

Please provide a SPOT airfreight rate for the shipment below:

Origin: {origin_code}
Destination: {destination_code}
Commodity: {commodity_display}
Weight: {weight_kg} kg
Pieces / Dimensions:
{dimensions_text.rstrip()}
{notes_text}
Please include:
- Airfreight rate (per kg)
- Origin charges (if any)
- Routing / number of legs
- Rate validity
- Any conditions or exclusions

If acceptance or capacity is subject to confirmation, please advise.

Thank you,
{sender}"""
        
        return SpotEmailDraft(subject=subject.strip(), body=body.strip())
