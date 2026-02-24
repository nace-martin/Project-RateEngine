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

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Optional, Tuple, List
from uuid import uuid4

from django.conf import settings

logger = logging.getLogger(__name__)

from quotes.spot_schemas import (
    SpotPricingEnvelope,
    SPEShipmentContext,
    SPEChargeLine,
    SPEConditions,
    SPEAcknowledgement,
    SPEManagerApproval,
    SPEStatus,
)
from quotes.completeness import (
    evaluate_from_availability,
    COMPONENT_DESTINATION_LOCAL,
    COMPONENT_FREIGHT,
    COMPONENT_ORIGIN_LOCAL,
)


# =============================================================================
# SPOT TRIGGER REASON CODES (Tweak #5 - Audit Trail)
# =============================================================================

class SpotTriggerReason:
    """Machine-readable SPOT trigger reason codes."""
    # Canonical Code (Deterministic Logic)
    MISSING_SCOPE_RATES = "MISSING_SCOPE_RATES"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"
    
    # Legacy codes (retained for backward compatibility in DB)
    SCR_COMMODITY = "SCR_COMMODITY"
    DG_COMMODITY = "DG_COMMODITY"
    AVI_COMMODITY = "AVI_COMMODITY"
    PER_COMMODITY = "PER_COMMODITY"
    HVC_COMMODITY = "HVC_COMMODITY"
    HUM_COMMODITY = "HUM_COMMODITY"
    OOG_COMMODITY = "OOG_COMMODITY"
    VUL_COMMODITY = "VUL_COMMODITY"
    TTS_COMMODITY = "TTS_COMMODITY"
    NON_PX_ROUTE = "NON_PX_ROUTE"
    MISSING_COGS = "MISSING_COGS"
    MISSING_SELL = "MISSING_SELL"
    MULTI_LEG_ROUTING = "MULTI_LEG_ROUTING"
    NO_BUY_RATE = "NO_BUY_RATE"
    REQUIRES_ASSUMPTIONS = "REQUIRES_ASSUMPTIONS"
    INTERNATIONAL_D2D = "INTERNATIONAL_D2D"
    INTERNATIONAL_D2A = "INTERNATIONAL_D2A"


@dataclass
class TriggerResult:
    """Result of SPOT trigger evaluation."""
    code: str
    text: str
    missing_components: List[str] = field(default_factory=list)


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
    OTHER_COUNTRY_CODE = "OTHER"

    # Fallback map for lanes where country is omitted but airport code is known.
    DEFAULT_AIRPORT_COUNTRY_MAP = {
        "POM": "PG",
        "LAE": "PG",
        "MTV": "PG",
        "SIN": "SG",
        "HKG": "HK",
        "BNE": "AU",
        "SYD": "AU",
        "CNS": "AU",
        "NAN": "FJ",
        "HIR": "SB",
        "VLI": "VU",
    }

    @classmethod
    def _normalize_country_code(cls, country_code: Optional[str]) -> str:
        code = (country_code or "").strip().upper()
        return code or cls.OTHER_COUNTRY_CODE

    @classmethod
    def _lookup_country_by_airport(cls, airport_code: Optional[str]) -> Optional[str]:
        code = (airport_code or "").strip().upper()
        if len(code) != 3:
            return None

        try:
            from core.models import Airport, Location

            location = (
                Location.objects.filter(code=code)
                .select_related("country", "city__country", "airport__city__country")
                .first()
            )
            if location:
                if location.country and location.country.code:
                    return location.country.code.upper()
                if location.city and location.city.country and location.city.country.code:
                    return location.city.country.code.upper()
                if (
                    location.airport
                    and location.airport.city
                    and location.airport.city.country
                    and location.airport.city.country.code
                ):
                    return location.airport.city.country.code.upper()

            airport = Airport.objects.select_related("city__country").filter(iata_code=code).first()
            if airport and airport.city and airport.city.country and airport.city.country.code:
                return airport.city.country.code.upper()
        except Exception:
            pass

        settings_map = getattr(settings, "SPOT_AIRPORT_COUNTRY_MAP", {}) or {}
        mapped = settings_map.get(code) or cls.DEFAULT_AIRPORT_COUNTRY_MAP.get(code)
        return (mapped or "").upper() or None

    @classmethod
    def normalize_countries(
        cls,
        origin_country: Optional[str],
        destination_country: Optional[str],
        origin_airport: Optional[str] = None,
        destination_airport: Optional[str] = None,
    ) -> tuple[str, str]:
        origin = cls._normalize_country_code(origin_country)
        destination = cls._normalize_country_code(destination_country)

        if origin == cls.OTHER_COUNTRY_CODE:
            origin = cls._lookup_country_by_airport(origin_airport) or cls.OTHER_COUNTRY_CODE
        if destination == cls.OTHER_COUNTRY_CODE:
            destination = cls._lookup_country_by_airport(destination_airport) or cls.OTHER_COUNTRY_CODE

        return origin, destination
    
    @classmethod
    def validate(
        cls,
        origin_country: str,
        destination_country: str,
        origin_airport: Optional[str] = None,
        destination_airport: Optional[str] = None,
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
        origin_country, destination_country = cls.normalize_countries(
            origin_country=origin_country,
            destination_country=destination_country,
            origin_airport=origin_airport,
            destination_airport=destination_airport,
        )

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
    Deterministic SPOT trigger logic.
    
    // SPOT is triggered whenever the database cannot fully satisfy
    // the required BUY rate components for the selected service scope.
    """
    
    @classmethod
    def evaluate(
        cls,
        origin_country: str,
        destination_country: str,
        direction: str,
        service_scope: str,
        # A dictionary mapping component codes to their availability in the DB
        # { "FREIGHT": True, "ORIGIN_LOCAL": False, "DESTINATION_LOCAL": True, ... }
        component_availability: dict[str, bool]
    ) -> Tuple[bool, Optional[TriggerResult]]:
        """
        Determine deterministically whether a quote must enter SPOT mode.
        Based on service-scope rate coverage, not routing.
        """
        origin_country, destination_country = ScopeValidator.normalize_countries(
            origin_country=origin_country,
            destination_country=destination_country,
        )

        # 1️⃣ Scope Validation (Hard Stop)
        # Note: ScopeValidator.validate is already called at the request boundary,
        # but we keep this here for logic completeness.
        if origin_country != "PG" and destination_country != "PG":
            return True, TriggerResult(
                code=SpotTriggerReason.OUT_OF_SCOPE,
                text="RateEngine only supports shipments to or from PNG."
            )

        coverage = evaluate_from_availability(
            component_availability=component_availability,
            shipment_type=direction,
            service_scope=service_scope,
        )

        # 2️⃣ SPOT Decision
        if coverage.missing_required:
            return True, TriggerResult(
                code=SpotTriggerReason.MISSING_SCOPE_RATES,
                text=(
                    "Missing required rate components for selected service scope: "
                    f"{', '.join(coverage.missing_required)}"
                ),
                missing_components=coverage.missing_required,
            )

        # 5️⃣ Normal Pricing Path
        return False, None

class RateAvailabilityService:
    """
    Check availability of required rate components in the database.
    """
    
    @classmethod
    def get_availability(
        cls,
        origin_airport: str,
        destination_airport: str,
        direction: str,
        service_scope: str,
    ) -> dict[str, bool]:
        """
        Build component availability map by querying V4 tables.
        """
        # Import models here to avoid circular imports
        from pricing_v4.models import (
            ExportCOGS,
            ImportCOGS,
            Surcharge,
            ProductCode,
            DomesticCOGS,
            LocalCOGSRate,
        )
        from datetime import date
        
        today = date.today()
        availability = {
            COMPONENT_FREIGHT: False,
            COMPONENT_ORIGIN_LOCAL: False,
            COMPONENT_DESTINATION_LOCAL: False,
        }
        
        # 1. Freight Coverage (AIRFREIGHT)
        if direction == 'DOMESTIC':
            availability[COMPONENT_FREIGHT] = DomesticCOGS.objects.filter(
                origin_zone=origin_airport,
                destination_zone=destination_airport,
                product_code__category=ProductCode.CATEGORY_FREIGHT,
                valid_from__lte=today,
                valid_until__gte=today
            ).exists()
            return availability
        if direction == 'EXPORT':
            availability[COMPONENT_FREIGHT] = ExportCOGS.objects.filter(
                origin_airport=origin_airport,
                destination_airport=destination_airport,
                product_code__category=ProductCode.CATEGORY_FREIGHT,
                valid_from__lte=today,
                valid_until__gte=today
            ).exists()
        else:
            availability[COMPONENT_FREIGHT] = ImportCOGS.objects.filter(
                origin_airport=origin_airport,
                destination_airport=destination_airport,
                product_code__category=ProductCode.CATEGORY_FREIGHT,
                valid_from__lte=today,
                valid_until__gte=today
            ).exists()

        def classify_export_component(code: str, category: str) -> str:
            code = (code or "").upper()
            if category == ProductCode.CATEGORY_FREIGHT:
                return COMPONENT_FREIGHT
            if "DEST" in code:
                return COMPONENT_DESTINATION_LOCAL
            return COMPONENT_ORIGIN_LOCAL

        def classify_import_component(code: str, category: str) -> str:
            code = (code or "").upper()
            if category == ProductCode.CATEGORY_FREIGHT or "FRT" in code or "FREIGHT" in code:
                return COMPONENT_FREIGHT
            if "DEST" in code or code in {"IMP-CLEAR", "IMP-CARTAGE-DEST", "IMP-FSC-CARTAGE-DEST"}:
                return COMPONENT_DESTINATION_LOCAL
            if "ORIGIN" in code or code in {"IMP-PICKUP", "IMP-FSC-PICKUP"}:
                return COMPONENT_ORIGIN_LOCAL
            if category in {ProductCode.CATEGORY_CARTAGE, ProductCode.CATEGORY_CLEARANCE}:
                return COMPONENT_DESTINATION_LOCAL
            return COMPONENT_ORIGIN_LOCAL

        if direction == 'EXPORT':
            export_codes = ExportCOGS.objects.filter(
                origin_airport=origin_airport,
                destination_airport=destination_airport,
                valid_from__lte=today,
                valid_until__gte=today
            ).values_list('product_code__code', 'product_code__category')
            for code, category in export_codes:
                availability[classify_export_component(code, category)] = True

            if LocalCOGSRate.objects.filter(
                location=origin_airport,
                direction='EXPORT',
                valid_from__lte=today,
                valid_until__gte=today
            ).exists():
                availability[COMPONENT_ORIGIN_LOCAL] = True

            if Surcharge.objects.filter(
                service_type='EXPORT_ORIGIN',
                origin_filter=origin_airport,
                valid_from__lte=today,
                valid_until__gte=today
            ).exists():
                availability[COMPONENT_ORIGIN_LOCAL] = True

            if Surcharge.objects.filter(
                service_type='EXPORT_DEST',
                destination_filter=destination_airport,
                valid_from__lte=today,
                valid_until__gte=today
            ).exists():
                availability[COMPONENT_DESTINATION_LOCAL] = True
        else:
            import_codes = ImportCOGS.objects.filter(
                origin_airport=origin_airport,
                destination_airport=destination_airport,
                valid_from__lte=today,
                valid_until__gte=today
            ).values_list('product_code__code', 'product_code__category')
            for code, category in import_codes:
                availability[classify_import_component(code, category)] = True

            if LocalCOGSRate.objects.filter(
                location=destination_airport,
                direction='IMPORT',
                valid_from__lte=today,
                valid_until__gte=today
            ).exists():
                availability[COMPONENT_DESTINATION_LOCAL] = True

            if Surcharge.objects.filter(
                service_type='IMPORT_ORIGIN',
                origin_filter=origin_airport,
                valid_from__lte=today,
                valid_until__gte=today
            ).exists():
                availability[COMPONENT_ORIGIN_LOCAL] = True

            if Surcharge.objects.filter(
                service_type='IMPORT_DEST',
                destination_filter=destination_airport,
                valid_from__lte=today,
                valid_until__gte=today
            ).exists():
                availability[COMPONENT_DESTINATION_LOCAL] = True
            
        lane_key = f"{origin_airport.upper()}-{destination_airport.upper()}"
        config = getattr(settings, 'SPOT_ROUTE_COVERAGE', {})
        export_d2a_lanes = set(config.get('export_d2a_lanes', []))
        import_d2a_lanes = set(config.get('import_d2a_lanes', []))
        import_a2d_destination_global = config.get('import_a2d_destination_global', False)

        if direction == 'EXPORT' and lane_key in export_d2a_lanes:
            availability[COMPONENT_FREIGHT] = True
            availability[COMPONENT_ORIGIN_LOCAL] = True

        if direction == 'IMPORT':
            if import_a2d_destination_global:
                availability[COMPONENT_DESTINATION_LOCAL] = True
            if lane_key in import_d2a_lanes:
                availability[COMPONENT_FREIGHT] = True

        return availability


class StandardChargeService:
    """
    Fetch standard charges from DB for hybrid SPOT pre-population.
    
    Returns charge lines where DB coverage exists, allowing the Rate Entry
    page to show airfreight/origin charges from standard rates while only
    requiring manual entry for destination charges.
    """
    
    @classmethod
    def get_standard_charges(
        cls,
        origin_code: str,
        destination_code: str,
        direction: str,
        service_scope: str,
        weight_kg: float,
        commodity: str = "GCR",
    ) -> list[dict]:
        """
        Get standard charges for a lane where DB coverage exists.
        
        Returns list of charge dicts in SPEChargeLine format:
        {
            "code": str,
            "description": str,
            "amount": str,
            "currency": str,
            "unit": str,
            "bucket": str,
            "is_primary_cost": bool,
            "source_reference": str,
        }
        """
        from datetime import date
        from decimal import Decimal
        from uuid import uuid4
        
        from core.dataclasses import (
            QuoteInput, ShipmentDetails, LocationRef, Piece
        )
        from pricing_v4.adapter import PricingServiceV4Adapter
        
        # Check availability first
        availability = RateAvailabilityService.get_availability(
            origin_airport=origin_code,
            destination_airport=destination_code,
            direction=direction,
            service_scope=service_scope,
        )
        
        # If no standard coverage at all, return empty
        if not any(availability.values()):
            return []
        
        try:
            # Build minimal QuoteInput for V4 adapter
            # Look up location IDs using Location model (has IATA code)
            from core.models import Location
            
            origin_loc = Location.objects.filter(code=origin_code).first()
            dest_loc = Location.objects.filter(code=destination_code).first()
            
            if not origin_loc or not dest_loc:
                logger.warning(f"Location not found for {origin_code} or {destination_code}")
                return []
            
            origin_ref = LocationRef(
                id=origin_loc.id,
                code=origin_code,
                name=origin_loc.name,
                country_code=origin_loc.country.code if origin_loc.country else "PG",
                currency_code="PGK"
            )
            dest_ref = LocationRef(
                id=dest_loc.id,
                code=destination_code,
                name=dest_loc.name,
                country_code=dest_loc.country.code if dest_loc.country else "XX",
                currency_code="USD"
            )
            
            # Determine shipment type
            shipment_type = "EXPORT" if direction == "EXPORT" else "IMPORT"
            if direction == "DOMESTIC":
                shipment_type = "DOMESTIC"
            
            shipment = ShipmentDetails(
                mode="AIR",
                shipment_type=shipment_type,
                incoterm="EXW" if direction == "EXPORT" else "DDU",
                payment_term="PREPAID",
                is_dangerous_goods=(commodity == "DG"),
                pieces=[Piece(
                    pieces=1,
                    length_cm=Decimal("50"),
                    width_cm=Decimal("50"),
                    height_cm=Decimal("50"),
                    gross_weight_kg=Decimal(str(weight_kg))
                )],
                service_scope=service_scope,
                direction=direction,
                origin_location=origin_ref,
                destination_location=dest_ref,
            )
            
            quote_input = QuoteInput(
                customer_id=uuid4(),  # Dummy for calculation
                contact_id=uuid4(),
                output_currency="PGK",
                quote_date=date.today(),
                shipment=shipment,
            )
            
            # Run V4 adapter to get standard lines
            adapter = PricingServiceV4Adapter(quote_input)
            standard_lines = adapter._calculate_standard_lines()
            
            # Convert to SPEChargeLine format
            result = []
            for line in standard_lines:
                # Skip lines with missing rates
                if line.is_rate_missing:
                    continue
                
                # Map bucket
                bucket_map = {
                    "airfreight": "airfreight",
                    "origin_charges": "origin_charges",
                    "destination_charges": "destination_charges",
                }
                bucket = bucket_map.get(line.bucket, "origin_charges")
                
                # Determine unit type
                unit = "per_shipment"
                if "per_kg" in line.cost_source.lower() or line.service_component_code in ["FREIGHT", "AIRFREIGHT"]:
                    unit = "per_kg"
                
                # Determine amount to show
                amount = str(float(line.cost_fcy)) if line.cost_fcy else str(float(line.cost_pgk))
                currency = line.cost_fcy_currency or "PGK"
                
                result.append({
                    "code": line.service_component_code,
                    "description": line.service_component_desc,
                    "amount": amount,
                    "currency": currency,
                    "unit": unit,
                    "bucket": bucket,
                    "is_primary_cost": line.service_component_code in ["FREIGHT", "AIRFREIGHT", "DOMESTIC_FREIGHT"],
                    "conditional": False,
                    "source_reference": f"Standard Rate ({line.cost_source})",
                })
            
            return result
            
        except Exception as e:
            logger.error(f"Error fetching standard charges: {e}")
            return []


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

    @classmethod
    def update_envelope(
        cls,
        spe: SpotPricingEnvelope,
        charges: Optional[List[SPEChargeLine]] = None,
        conditions: Optional[SPEConditions] = None,
    ) -> SpotPricingEnvelope:
        """
        Update an existing DRAFT SPE.
        
        Allows enriching a draft with extracted charges or updated conditions.
        """
        if spe.status != SPEStatus.DRAFT:
            raise ValueError(f"Cannot update SPE in status '{spe.status.value}'. Only DRAFT can be updated.")
            
        updated_data = spe.model_dump()
        
        if charges is not None:
            updated_data["charges"] = charges
            
        if conditions is not None:
            updated_data["conditions"] = conditions
            
        return SpotPricingEnvelope(**updated_data)


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


# =============================================================================
# REPLY ANALYSIS SERVICE
# =============================================================================

class ReplyAnalysisService:
    """
    Analyze agent rate replies and build SPE assertions.
    
    Phase 1: Manual classification (user adds assertions)
    Phase 2: AI-assisted extraction (coming soon)
    
    Workflow:
    1. User pastes agent reply text
    2. System (or AI) extracts assertions
    3. User reviews/adjusts classifications
    4. System validates mandatory fields
    5. System builds SPE from assertions
    """
    
    # Import here to avoid circular imports at module level
    from quotes.reply_schemas import (
        AssertionStatus,
        AssertionCategory,
        ExtractedAssertion,
        AnalysisSummary,
        ReplyAnalysisResult,
        MANDATORY_CATEGORIES,
        OPTIONAL_CATEGORIES,
    )
    
    @classmethod
    def analyze_manual(
        cls,
        raw_text: str,
        assertions: List[dict],
    ) -> 'ReplyAnalysisResult':
        """
        Analyze with manually provided assertions.
        
        Args:
            raw_text: Original pasted reply text
            assertions: List of assertion dicts from user input
            
        Returns:
            ReplyAnalysisResult with summary and warnings
        """
        from quotes.reply_schemas import (
            AssertionStatus,
            AssertionCategory,
            ExtractedAssertion,
            AnalysisSummary,
            ReplyAnalysisResult,
            MANDATORY_CATEGORIES,
        )
        
        parsed_assertions = []
        for a in assertions:
            parsed_assertions.append(ExtractedAssertion(
                text=a.get('text', ''),
                category=AssertionCategory(a.get('category', 'rate')),
                value=a.get('value'),
                status=AssertionStatus(a.get('status', 'confirmed')),
                confidence=a.get('confidence', 1.0),
                source_line=a.get('source_line'),
                rate_amount=a.get('rate_amount'),
                rate_currency=a.get('rate_currency'),
                rate_unit=a.get('rate_unit'),
                validity_date=a.get('validity_date'),
            ))
        
        # Build summary
        summary = cls._build_summary(parsed_assertions)
        
        # Generate warnings
        warnings = cls._generate_warnings(summary, parsed_assertions)
        
        return ReplyAnalysisResult(
            raw_text=raw_text,
            assertions=parsed_assertions,
            summary=summary,
            warnings=warnings,
        )
    
    @classmethod
    def analyze_with_ai(
        cls,
        raw_text: str,
        shipment_context: Optional[dict] = None,
        availability: Optional[dict[str, bool]] = None,
    ) -> 'ReplyAnalysisResult':
        """
        Analyze using Gemini AI for extraction.
        
        Phase 2: Use LLM to identify charges, currency, and validity.
        """
        from quotes.ai_intake_service import parse_rate_quote_text, get_gemini_client
        from quotes.reply_schemas import (
            AssertionStatus,
            AssertionCategory,
            ExtractedAssertion,
            AnalysisSummary,
            ReplyAnalysisResult,
        )

        genai = get_gemini_client()
        ai_unavailable = genai is None
        ai_assertions = []
        ai_result = None
        
        if genai:
            # Call existing AI service with context to help it categorize
            ai_result = parse_rate_quote_text(raw_text, context=shipment_context)
            logger.info(
                "AI analysis result: success=%s lines=%s warnings=%s",
                getattr(ai_result, "success", None),
                len(getattr(ai_result, "lines", []) or []),
                len(getattr(ai_result, "warnings", []) or []),
            )
            if ai_result.success:
                # Add global currency assertion if present
                if ai_result.quote_currency:
                    ai_assertions.append(ExtractedAssertion(
                        text=f"Quote Currency: {ai_result.quote_currency}",
                        category=AssertionCategory.CURRENCY,
                        status=AssertionStatus.CONFIRMED,
                        confidence=0.95,
                        rate_currency=ai_result.quote_currency
                    ))

                for line in ai_result.lines:
                    # Map SpotChargeLine to ExtractedAssertion
                    category = AssertionCategory.RATE
                    if line.bucket == "ORIGIN":
                        category = AssertionCategory.ORIGIN_CHARGES
                    elif line.bucket == "DESTINATION":
                        category = AssertionCategory.DEST_CHARGES
                    
                    # Fallback to quote currency if line currency is missing
                    final_currency = line.currency or ai_result.quote_currency
                    
                    # For MIN_OR_PER_KG, use minimum as the display amount
                    display_amount = line.minimum if line.minimum is not None else line.amount
                    # For PERCENTAGE, use percentage value as the display amount
                    if line.unit_basis == "PERCENTAGE" and line.percentage is not None:
                        display_amount = line.percentage

                    ai_assertions.append(ExtractedAssertion(
                        text=line.description,
                        category=category,
                        status=AssertionStatus.CONFIRMED if not line.conditional else AssertionStatus.CONDITIONAL,
                        confidence=line.confidence or 0.9,
                        rate_amount=display_amount,
                        rate_per_unit=line.rate_per_unit,
                        rate_currency=final_currency,
                        rate_unit=line.unit_basis.lower() if line.unit_basis else "per_kg",
                    ))
        
        # Add Standard Rate suggestions if context is provided
        standard_assertions = []
        if shipment_context:
            standard_assertions = cls._get_standard_rate_assertions(
                shipment_context, 
                availability=availability
            )
            
        # Combine all assertions
        all_assertions = ai_assertions + standard_assertions
        
        # Build summary
        summary = cls._build_summary(all_assertions, availability=availability)
        
        # FALLBACK: If no currency was detected from AI or assertions, try to infer from raw text
        if not summary.has_currency:
            from quotes.ai_intake_service import _infer_quote_currency_from_text
            inferred_currency = _infer_quote_currency_from_text(raw_text)
            if inferred_currency:
                # Add a currency assertion based on text inference
                all_assertions.append(ExtractedAssertion(
                    text=f"Currency inferred from text: {inferred_currency}",
                    category=AssertionCategory.CURRENCY,
                    status=AssertionStatus.IMPLICIT,  # Mark as implicit since it wasn't explicitly from AI
                    confidence=0.8,
                    rate_currency=inferred_currency,
                ))
                # Update summary to reflect the discovered currency
                summary.has_currency = True
        
        # Generate warnings
        warnings = cls._generate_warnings(summary, all_assertions)
        if ai_unavailable:
            warnings.append(
                "AI analysis unavailable: Gemini client not configured. "
                "Install google-generativeai and set GEMINI_API_KEY."
            )
        
        # Add AI warnings to our warnings list
        if genai and ai_result:
            if not ai_result.success:
                warnings.append(f"⚠️ AI analysis failed: {ai_result.error}. Falling back to standard rates.")
            elif ai_result.warnings:
                for w in ai_result.warnings:
                    warnings.append(f"⚠️ AI: {w}")

        return ReplyAnalysisResult(
            raw_text=raw_text,
            assertions=all_assertions,
            summary=summary,
            warnings=warnings,
        )

    @classmethod
    def _get_standard_rate_assertions(
        cls, 
        ctx: dict,
        availability: Optional[dict[str, bool]] = None
    ) -> List['ExtractedAssertion']:
        """Lookup existing rates in DB to provide as implicit suggestions."""
        from quotes.reply_schemas import AssertionStatus, AssertionCategory, ExtractedAssertion
        from pricing_v4.models import ExportCOGS, ImportCOGS, ProductCode
        from datetime import date
        
        origin = ctx.get('origin_code')
        dest = ctx.get('destination_code')
        origin_country = ctx.get('origin_country')
        dest_country = ctx.get('destination_country')
        today = date.today()
        
        suggestions = []
        
        # 1. Query DB for rates (COGS is usually the base for SPOT review)
        if origin_country == 'PG':
            rates = ExportCOGS.objects.filter(
                origin_airport=origin,
                destination_airport=dest,
                valid_from__lte=today,
                valid_until__gte=today
            ).select_related('product_code')
        else:
            rates = ImportCOGS.objects.filter(
                origin_airport=origin,
                destination_airport=dest,
                valid_from__lte=today,
                valid_until__gte=today
            ).select_related('product_code')
            
        # 2. Convert to assertions
        for r in rates:
            category = AssertionCategory.RATE if r.product_code.category == ProductCode.CATEGORY_FREIGHT else AssertionCategory.ORIGIN_CHARGES
            # If import, destination charges might be relevant
            if origin_country != 'PG' and r.product_code.category != ProductCode.CATEGORY_FREIGHT:
                category = AssertionCategory.DEST_CHARGES
                
            suggestions.append(ExtractedAssertion(
                text=f"Standard Rate: {r.product_code.description}",
                category=category,
                status=AssertionStatus.IMPLICIT,
                confidence=0.8,
                rate_amount=r.rate_per_kg or r.rate_per_shipment,
                rate_currency=r.currency,
            rate_unit="per_kg" if r.rate_per_kg else "flat",
            ))
            
        # 3. Filter if availability metadata is provided
        if availability:
            filtered = []
            for a in suggestions:
                # Map assertion category to availability keys
                should_skip = False
                if a.category == AssertionCategory.RATE and availability.get(COMPONENT_FREIGHT):
                    should_skip = True
                elif a.category == AssertionCategory.ORIGIN_CHARGES:
                    if availability.get(COMPONENT_ORIGIN_LOCAL):
                        should_skip = True
                elif a.category == AssertionCategory.DEST_CHARGES:
                    if availability.get(COMPONENT_DESTINATION_LOCAL):
                        should_skip = True
                
                if not should_skip:
                    filtered.append(a)
            return filtered
            
        return suggestions

    @classmethod
    def _build_summary(cls, assertions: List['ExtractedAssertion'], availability: Optional[dict[str, bool]] = None) -> 'AnalysisSummary':
        """Build summary from assertions."""
        from quotes.reply_schemas import (
            AssertionStatus,
            AssertionCategory,
            AnalysisSummary,
        )
        
        summary = AnalysisSummary()
        
        # 1️⃣ Pre-populate from DB availability (if provided)
        # This ensures we don't show "Missing rate" if DB has rates for this lane
        if availability:
            # If DB has airfreight rate, we have a rate
            if availability.get(COMPONENT_FREIGHT):
                summary.has_rate = True
            # Destination charges count as rate for Import A2D/D2D
            if availability.get(COMPONENT_DESTINATION_LOCAL):
                summary.has_rate = True
            # Origin charges count as rate for Export D2A/D2D  
            if availability.get(COMPONENT_ORIGIN_LOCAL):
                summary.has_rate = True
        
        # 2️⃣ Enrich from assertions
        for a in assertions:
            # Count by status
            if a.status == AssertionStatus.CONFIRMED:
                summary.confirmed_count += 1
            elif a.status == AssertionStatus.CONDITIONAL:
                summary.conditional_count += 1
            elif a.status == AssertionStatus.IMPLICIT:
                summary.implicit_count += 1
            elif a.status == AssertionStatus.MISSING:
                summary.missing_count += 1
            
            # Check field presence (any status except MISSING counts as "has")
            if a.status != AssertionStatus.MISSING:
                if a.category == AssertionCategory.RATE:
                    summary.has_rate = True
                    if a.rate_currency:
                        summary.has_currency = True
                
                elif a.category == AssertionCategory.CURRENCY:
                    summary.has_currency = True
                
                elif a.category == AssertionCategory.VALIDITY:
                    summary.has_validity = True
                
                elif a.category == AssertionCategory.ROUTING:
                    summary.has_routing = True
                
                elif a.category == AssertionCategory.ACCEPTANCE:
                    summary.has_acceptance = True
                
                # Dest/Origin charges also count as rate and may have currency
                elif a.category == AssertionCategory.DEST_CHARGES:
                    summary.has_rate = True
                    if a.rate_currency:
                        summary.has_currency = True
                
                elif a.category == AssertionCategory.ORIGIN_CHARGES:
                    summary.has_rate = True
                    if a.rate_currency:
                        summary.has_currency = True
        
        return summary
    
    @classmethod
    def _generate_warnings(
        cls,
        summary: 'AnalysisSummary',
        assertions: List['ExtractedAssertion'],
    ) -> List[str]:
        """Generate user-facing warnings."""
        from quotes.reply_schemas import AssertionStatus
        
        warnings = []
        
        # Mandatory field warnings
        if not summary.has_rate:
            warnings.append("⛔ MISSING: Airfreight rate is required")
        if not summary.has_currency:
            warnings.append("⛔ MISSING: Rate currency is required")
        if not summary.has_validity:
            warnings.append("⚠️ Validity not specified - assuming 72 hours")
        
        # Optional field warnings
        if not summary.has_routing:
            warnings.append("⚠️ Routing not specified - may involve multiple legs")
        if not summary.has_acceptance:
            warnings.append("⚠️ Space/acceptance not confirmed")
        
        # Conditional/implicit warnings
        conditional = [a for a in assertions if a.status == AssertionStatus.CONDITIONAL]
        if conditional:
            warnings.append(f"⚠️ {len(conditional)} item(s) are conditional - requires acknowledgement")
        
        implicit = [a for a in assertions if a.status == AssertionStatus.IMPLICIT]
        if implicit:
            warnings.append(f"⚠️ {len(implicit)} item(s) are implicit assumptions - verify before proceeding")
        
        return warnings
    
    @classmethod
    def build_spe_charges_from_analysis(
        cls,
        analysis: 'ReplyAnalysisResult',
        source_reference: str = "Agent reply",
        shipment_context: Optional[dict] = None,
    ) -> List[dict]:
        """
        Convert analysis assertions to SPE charge line inputs.
        
        Args:
            analysis: Completed analysis result
            source_reference: Source reference for charge lines
            
        Returns:
            List of charge line dicts ready for SPE creation
        """
        from decimal import Decimal, InvalidOperation
        from quotes.reply_schemas import AssertionStatus, AssertionCategory
        from quotes.completeness import (
            COMPONENT_ORIGIN_LOCAL,
            COMPONENT_FREIGHT,
            COMPONENT_DESTINATION_LOCAL,
            required_components,
        )

        charges: List[dict] = []

        component_map = {
            AssertionCategory.RATE: (COMPONENT_FREIGHT, "airfreight"),
            AssertionCategory.ORIGIN_CHARGES: (COMPONENT_ORIGIN_LOCAL, "origin_charges"),
            AssertionCategory.DEST_CHARGES: (COMPONENT_DESTINATION_LOCAL, "destination_charges"),
        }
        unit_to_unit_type = {
            "per_kg": "kg",
            "flat": "shipment",
            "per_shipment": "shipment",
            "per_awb": "awb",
            "per_trip": "trip",
            "per_set": "set",
            "per_man": "man",
            "percentage": "line",
        }

        def _parse_decimal(value) -> Optional[Decimal]:
            if value is None:
                return None
            try:
                return Decimal(str(value))
            except (InvalidOperation, ValueError, TypeError):
                return None

        def _normalize_scope(scope: Optional[str]) -> str:
            if not scope:
                return "A2A"
            scope_up = str(scope).upper()
            return "A2A" if scope_up == "P2P" else scope_up

        def _shipment_type_from_context(ctx: dict) -> str:
            origin_country = (ctx.get("origin_country") or "").upper()
            dest_country = (ctx.get("destination_country") or "").upper()
            if origin_country == "PG" and dest_country == "PG":
                return "DOMESTIC"
            if origin_country == "PG":
                return "EXPORT"
            return "IMPORT"

        required_for_scope = None
        shipment_type = None
        missing_components_set: set[str] = set()
        if shipment_context:
            shipment_type = _shipment_type_from_context(shipment_context)
            required_for_scope = required_components(
                shipment_type,
                _normalize_scope(shipment_context.get("service_scope")),
            )
            raw_missing = shipment_context.get("missing_components") or []
            if isinstance(raw_missing, (list, tuple, set)):
                missing_components_set = {str(item).upper() for item in raw_missing if item}

        for a in analysis.assertions:
            # Skip missing assertions. For implicit assertions, allow DB-backed standard-rate
            # suggestions (tagged by the service with "Standard Rate:") to support hybrid prefill.
            if a.status == AssertionStatus.MISSING:
                continue
            if a.status == AssertionStatus.IMPLICIT and not str(a.text or "").startswith("Standard Rate:"):
                continue

            category = a.category

            # Heuristic re-bucketing:
            # AI may classify "import charges" style tables as destination charges based on wording,
            # even when the quoted local charges are at the route origin (e.g. SIN->POM import into PG).
            # When only one local side is missing, bias local-charge assertions to that missing side.
            if shipment_type == "IMPORT":
                if (
                    category == AssertionCategory.DEST_CHARGES
                    and "ORIGIN_LOCAL" in missing_components_set
                    and "DESTINATION_LOCAL" not in missing_components_set
                ):
                    logger.info(
                        "Reclassifying AI local charge to origin for IMPORT lane: %s",
                        a.text,
                    )
                    category = AssertionCategory.ORIGIN_CHARGES
            elif shipment_type == "EXPORT":
                if (
                    category == AssertionCategory.ORIGIN_CHARGES
                    and "DESTINATION_LOCAL" in missing_components_set
                    and "ORIGIN_LOCAL" not in missing_components_set
                ):
                    logger.info(
                        "Reclassifying AI local charge to destination for EXPORT lane: %s",
                        a.text,
                    )
                    category = AssertionCategory.DEST_CHARGES

            if category not in component_map:
                continue

            component_code, bucket = component_map[category]

            # Scope guardrail: keep only components required for this quote context.
            if required_for_scope is not None and component_code not in required_for_scope:
                continue

            unit_raw = (a.rate_unit or "").lower().strip()
            default_unit = "per_kg" if category == AssertionCategory.RATE else "flat"

            min_charge = None
            exclude_from_totals = False
            calculation_type = None
            unit_type = None
            rate = None
            min_amount = None
            max_amount = None
            percent = None
            percent_basis = None
            rule_meta = {}

            # Normalize unit to SPE-supported values
            if unit_raw in {"per_kg", "per_shipment", "flat", "per_awb", "per_trip", "per_set", "per_man", "percentage"}:
                unit = unit_raw
            elif unit_raw.startswith("min_or_per_"):
                unit = unit_raw.replace("min_or_per_", "per_")
            elif unit_raw in {"min-per-kg"}:
                unit = "per_kg"
            else:
                unit = default_unit

            amount = None
            rate_amount = _parse_decimal(a.rate_amount)
            rate_per_unit = _parse_decimal(a.rate_per_unit)
            value_amount = _parse_decimal(a.value)

            if unit_raw.startswith("min_or_per_") or unit_raw in {"min-per-kg"}:
                # Min OR per unit: keep both per-unit rate and minimum floor.
                amount = rate_per_unit or rate_amount
                min_charge = rate_amount
                calculation_type = "min_or_per_unit"
                unit_type = unit_to_unit_type.get(unit, "shipment")
                rate = amount
                min_amount = min_charge
            elif unit == "per_kg":
                amount = rate_per_unit or rate_amount
                calculation_type = "per_unit"
                unit_type = "kg"
                rate = amount
            elif unit == "percentage":
                amount = rate_amount or rate_per_unit or value_amount
                exclude_from_totals = True
                calculation_type = "percent_of"
                unit_type = "line"
                percent = amount
                percent_basis = "freight"
            else:
                amount = rate_amount or value_amount
                if unit == "flat":
                    calculation_type = "flat"
                    unit_type = "shipment"
                    rate = amount
                else:
                    calculation_type = "per_unit"
                    unit_type = unit_to_unit_type.get(unit, "shipment")
                    rate = amount

            if amount is None or amount <= 0:
                continue

            # Contextual applicability guardrail for known opposite-direction taxes.
            desc_lower = (a.text or "").lower()
            if shipment_type == "EXPORT" and "import gst" in desc_lower:
                continue
            if shipment_type == "IMPORT" and "export declaration" in desc_lower:
                continue

            charges.append({
                "code": component_code,
                "description": a.text,
                "amount": str(amount),
                "currency": (a.rate_currency or "USD").upper(),
                "unit": unit,
                "bucket": bucket,
                "is_primary_cost": category == AssertionCategory.RATE,
                "conditional": a.status == AssertionStatus.CONDITIONAL,
                "min_charge": str(min_charge) if min_charge else None,
                "exclude_from_totals": exclude_from_totals,
                "calculation_type": calculation_type,
                "unit_type": unit_type,
                "rate": str(rate) if rate is not None else None,
                "min_amount": str(min_amount) if min_amount is not None else None,
                "max_amount": str(max_amount) if max_amount is not None else None,
                "percent": str(percent) if percent is not None else None,
                "percent_basis": percent_basis,
                "rule_meta": rule_meta,
                "source_reference": source_reference,
            })

        return charges

