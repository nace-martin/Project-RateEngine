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
    SPE lifecycle: create, validate, acknowledge, and expire.
"""

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Optional, Tuple, List
from uuid import uuid4

from django.conf import settings
from django.db.models import Q

logger = logging.getLogger(__name__)

from core.commodity import DEFAULT_COMMODITY_CODE
from quotes.branding import QuoteBrandingContext
from quotes.spot_schemas import (
    SpotPricingEnvelope,
    SPEShipmentContext,
    SPEChargeLine,
    SPEConditions,
    SPEAcknowledgement,
    SPEStatus,
)
from quotes.completeness import (
    evaluate_from_availability,
    COMPONENT_DESTINATION_LOCAL,
    COMPONENT_FREIGHT,
    COMPONENT_ORIGIN_LOCAL,
)
from pricing_v4.category_rules import (
    is_import_destination_local_code,
    is_import_origin_local_code,
)


# =============================================================================
# SPOT TRIGGER REASON CODES (Tweak #5 - Audit Trail)
# =============================================================================

class SpotTriggerReason:
    """Machine-readable SPOT trigger reason codes."""
    # Canonical Code (Deterministic Logic)
    MISSING_SCOPE_RATES = "MISSING_SCOPE_RATES"
    MISSING_COMMODITY_RATES = "MISSING_COMMODITY_RATES"
    COMMODITY_REQUIRES_SPOT = "COMMODITY_REQUIRES_SPOT"
    COMMODITY_REQUIRES_MANUAL = "COMMODITY_REQUIRES_MANUAL"
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
    missing_product_codes: List[str] = field(default_factory=list)
    spot_required_product_codes: List[str] = field(default_factory=list)
    manual_required_product_codes: List[str] = field(default_factory=list)


@dataclass
class CommodityCoverageResult:
    """Commodity-specific pricing coverage for the selected lane/scope."""
    missing_product_codes: List[str] = field(default_factory=list)
    spot_required_product_codes: List[str] = field(default_factory=list)
    manual_required_product_codes: List[str] = field(default_factory=list)

    @property
    def is_spot_required(self) -> bool:
        return bool(
            self.missing_product_codes
            or self.spot_required_product_codes
            or self.manual_required_product_codes
        )

    @property
    def unresolved_product_codes(self) -> List[str]:
        ordered: list[str] = []
        for code in (
            self.missing_product_codes
            + self.spot_required_product_codes
            + self.manual_required_product_codes
        ):
            normalized = str(code or "").upper()
            if normalized and normalized not in ordered:
                ordered.append(normalized)
        return ordered


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
        component_availability: dict[str, bool],
        commodity_code: str = DEFAULT_COMMODITY_CODE,
        commodity_coverage: Optional[CommodityCoverageResult] = None,
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

        commodity_trigger = cls.build_commodity_trigger(commodity_coverage)
        if commodity_trigger:
            return True, commodity_trigger

        # 5️⃣ Normal Pricing Path
        return False, None

    @classmethod
    def build_commodity_trigger(
        cls,
        commodity_coverage: Optional[CommodityCoverageResult],
    ) -> Optional[TriggerResult]:
        commodity_result = commodity_coverage or CommodityCoverageResult()
        if not commodity_result.is_spot_required:
            return None

        missing = commodity_result.missing_product_codes
        spot_required = commodity_result.spot_required_product_codes
        manual_required = commodity_result.manual_required_product_codes

        if manual_required:
            code = SpotTriggerReason.COMMODITY_REQUIRES_MANUAL
        elif spot_required:
            code = SpotTriggerReason.COMMODITY_REQUIRES_SPOT
        else:
            code = SpotTriggerReason.MISSING_COMMODITY_RATES

        message_parts: list[str] = []
        if manual_required:
            message_parts.append(
                "Commodity requires manual charge entry for: "
                + cls._format_product_codes(manual_required)
            )
        if spot_required:
            message_parts.append(
                "Commodity requires SPOT rate sourcing for: "
                + cls._format_product_codes(spot_required)
            )
        if missing:
            message_parts.append(
                "Commodity-specific DB coverage is missing for: "
                + cls._format_product_codes(missing)
            )

        return TriggerResult(
            code=code,
            text=" ".join(message_parts),
            missing_product_codes=commodity_result.unresolved_product_codes,
            spot_required_product_codes=spot_required,
            manual_required_product_codes=manual_required,
        )

    @staticmethod
    def _format_product_codes(codes: List[str]) -> str:
        ordered_codes: list[str] = []
        for code in codes:
            normalized = str(code or "").strip().upper()
            if normalized and normalized not in ordered_codes:
                ordered_codes.append(normalized)

        if not ordered_codes:
            return ""

        try:
            from pricing_v4.models import ProductCode
            description_map = {
                product.code.upper(): product.description
                for product in ProductCode.objects.filter(code__in=ordered_codes)
            }
        except Exception:
            description_map = {}

        formatted: list[str] = []
        for code in ordered_codes:
            description = description_map.get(code)
            if description:
                formatted.append(f"{description} ({code})")
            else:
                formatted.append(code)
        return ", ".join(formatted)

class RateAvailabilityService:
    """
    Check selector-aware availability of required rate components.
    """

    STATUS_COVERED_EXACT = "covered_exact"
    STATUS_COVERED_FALLBACK = "covered_fallback"
    STATUS_MISSING_DIMENSION = "missing_dimension"
    STATUS_AMBIGUOUS = "ambiguous"
    STATUS_MISSING_RATE = "missing_rate"

    @classmethod
    def get_component_outcomes(
        cls,
        origin_airport: str,
        destination_airport: str,
        direction: str,
        service_scope: str,
        payment_term: Optional[str] = None,
        *,
        agent_id: Optional[int] = None,
        carrier_id: Optional[int] = None,
        buy_currency: Optional[str] = None,
        quote_currency: Optional[str] = None,
        quote_date: Optional[date] = None,
    ) -> dict[str, dict]:
        from pricing_v4.models import (
            ExportCOGS,
            ExportSellRate,
            ImportCOGS,
            ImportSellRate,
            Surcharge,
            ProductCode,
            DomesticCOGS,
            DomesticSellRate,
            LocalCOGSRate,
            LocalSellRate,
        )
        from pricing_v4.services.rate_selector import (
            RateAmbiguityError,
            RateNotFoundError,
            RateSelectionContext,
            RateSelectionResult,
            build_rate_selection_error_payload,
            select_domestic_cogs_rate,
            select_domestic_sell_rate,
            select_export_cogs_rate,
            select_export_sell_rate,
            select_import_cogs_rate,
            select_import_sell_rate,
            select_local_cogs_rate,
            select_local_sell_rate,
        )

        origin_airport = (origin_airport or "").strip().upper()
        destination_airport = (destination_airport or "").strip().upper()
        direction = (direction or "").strip().upper()
        payment_term_normalized = (payment_term or "").strip().upper()
        if payment_term_normalized not in {"PREPAID", "COLLECT"}:
            payment_term_normalized = None
        buy_currency = (buy_currency or "").strip().upper() or None
        quote_currency = (quote_currency or "").strip().upper() or None

        today = quote_date or date.today()
        outcomes = {
            COMPONENT_FREIGHT: cls._missing_rate_outcome(COMPONENT_FREIGHT),
            COMPONENT_ORIGIN_LOCAL: cls._missing_rate_outcome(COMPONENT_ORIGIN_LOCAL),
            COMPONENT_DESTINATION_LOCAL: cls._missing_rate_outcome(COMPONENT_DESTINATION_LOCAL),
        }

        def matching_surcharge(
            component: str,
            service_type: str,
            *,
            origin: Optional[str] = None,
            destination: Optional[str] = None,
        ) -> Optional[dict]:
            qs = Surcharge.objects.filter(
                service_type=service_type,
                rate_side='COGS',
                is_active=True,
                valid_from__lte=today,
                valid_until__gte=today,
            )
            if origin is not None:
                qs = qs.filter(
                    Q(origin_filter=origin) | Q(origin_filter__isnull=True) | Q(origin_filter='')
                )
            if destination is not None:
                qs = qs.filter(
                    Q(destination_filter=destination) | Q(destination_filter__isnull=True) | Q(destination_filter='')
                )
            surcharge = qs.order_by('-valid_from', '-id').first()
            if not surcharge:
                return None
            return {
                'component': component,
                'status': cls.STATUS_COVERED_EXACT,
                'detail': f'Surcharge {surcharge.product_code.code} covers this component.',
                'match_type': 'surcharge',
                'selector_model': 'Surcharge',
                'selector_context': {
                    'product_code_id': surcharge.product_code_id,
                    'quote_date': today.isoformat(),
                },
                'missing_dimensions': [],
                'conflicting_rows': [],
                'fallback_applied': False,
            }

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
            if is_import_origin_local_code(code):
                return COMPONENT_ORIGIN_LOCAL
            if is_import_destination_local_code(code):
                return COMPONENT_DESTINATION_LOCAL
            if category in {ProductCode.CATEGORY_CARTAGE, ProductCode.CATEGORY_CLEARANCE}:
                return COMPONENT_DESTINATION_LOCAL
            return COMPONENT_ORIGIN_LOCAL

        def selection_outcome(component: str, error: Exception) -> dict:
            if isinstance(error, RateAmbiguityError):
                payload = build_rate_selection_error_payload(error, component=component)
                status_value = (
                    cls.STATUS_MISSING_DIMENSION
                    if payload.get('missing_dimensions')
                    else cls.STATUS_AMBIGUOUS
                )
                return {
                    'component': component,
                    'status': status_value,
                    'detail': payload.get('detail'),
                    'match_type': None,
                    'selector_model': payload.get('model'),
                    'selector_context': payload.get('selector_context', {}),
                    'missing_dimensions': payload.get('missing_dimensions', []),
                    'conflicting_rows': payload.get('conflicting_rows', []),
                    'fallback_applied': False,
                }
            if isinstance(error, RateNotFoundError):
                payload = build_rate_selection_error_payload(error, component=component)
                return {
                    'component': component,
                    'status': cls.STATUS_MISSING_RATE,
                    'detail': payload.get('detail'),
                    'match_type': None,
                    'selector_model': payload.get('model'),
                    'selector_context': payload.get('selector_context', {}),
                    'missing_dimensions': [],
                    'conflicting_rows': [],
                    'fallback_applied': False,
                }
            raise error

        def success_outcome(component: str, result: RateSelectionResult) -> dict:
            return {
                'component': component,
                'status': cls.STATUS_COVERED_FALLBACK if result.fallback_applied else cls.STATUS_COVERED_EXACT,
                'detail': f'{result.record.__class__.__name__} matched via {result.match_type}.',
                'match_type': result.match_type,
                'selector_model': result.record.__class__.__name__,
                'selector_context': getattr(result.context, '__dict__', {}),
                'missing_dimensions': [],
                'conflicting_rows': [],
                'fallback_applied': result.fallback_applied,
            }

        def choose_best(component: str, candidate_outcomes: list[dict]) -> dict:
            if not candidate_outcomes:
                return cls._missing_rate_outcome(component)

            priority = {
                cls.STATUS_COVERED_EXACT: 5,
                cls.STATUS_COVERED_FALLBACK: 4,
                cls.STATUS_MISSING_DIMENSION: 3,
                cls.STATUS_AMBIGUOUS: 2,
                cls.STATUS_MISSING_RATE: 1,
            }
            return max(candidate_outcomes, key=lambda outcome: priority[outcome['status']])

        def apply_payment_term_gate(current_outcome: dict, component: str, sell_rows: list) -> dict:
            if payment_term_normalized is None:
                return current_outcome
            if current_outcome['status'] not in {cls.STATUS_COVERED_EXACT, cls.STATUS_COVERED_FALLBACK}:
                return current_outcome
            if not sell_rows:
                return current_outcome

            sell_outcomes = [evaluate_row(component, row) for row in sell_rows]
            best_sell_outcome = choose_best(component, sell_outcomes)
            if best_sell_outcome['status'] in {cls.STATUS_COVERED_EXACT, cls.STATUS_COVERED_FALLBACK}:
                return current_outcome
            return best_sell_outcome

        def evaluate_row(component: str, row) -> dict:
            if isinstance(row, DomesticCOGS):
                return cls._run_selector(
                    component=component,
                    selector=lambda: select_domestic_cogs_rate(
                        RateSelectionContext(
                            product_code_id=row.product_code_id,
                            quote_date=today,
                            origin_zone=origin_airport,
                            destination_zone=destination_airport,
                            currency=buy_currency or 'PGK',
                            agent_id=agent_id,
                            carrier_id=carrier_id,
                        )
                    ),
                    success_outcome=success_outcome,
                    error_outcome=selection_outcome,
                )
            if isinstance(row, DomesticSellRate):
                return cls._run_selector(
                    component=component,
                    selector=lambda: select_domestic_sell_rate(
                        RateSelectionContext(
                            product_code_id=row.product_code_id,
                            quote_date=today,
                            origin_zone=origin_airport,
                            destination_zone=destination_airport,
                            currency='PGK',
                        )
                    ),
                    success_outcome=success_outcome,
                    error_outcome=selection_outcome,
                )
            if isinstance(row, ExportCOGS):
                return cls._run_selector(
                    component=component,
                    selector=lambda: select_export_cogs_rate(
                        RateSelectionContext(
                            product_code_id=row.product_code_id,
                            quote_date=today,
                            origin_airport=origin_airport,
                            destination_airport=destination_airport,
                            currency=buy_currency,
                            agent_id=agent_id,
                            carrier_id=carrier_id,
                        )
                    ),
                    success_outcome=success_outcome,
                    error_outcome=selection_outcome,
                )
            if isinstance(row, ExportSellRate):
                return cls._run_selector(
                    component=component,
                    selector=lambda: select_export_sell_rate(
                        RateSelectionContext(
                            product_code_id=row.product_code_id,
                            quote_date=today,
                            origin_airport=origin_airport,
                            destination_airport=destination_airport,
                            currency=quote_currency,
                        ),
                        allow_pgk_fallback=payment_term_normalized == 'PREPAID' and quote_currency not in {None, 'PGK'},
                    ),
                    success_outcome=success_outcome,
                    error_outcome=selection_outcome,
                )
            if isinstance(row, ImportCOGS):
                return cls._run_selector(
                    component=component,
                    selector=lambda: select_import_cogs_rate(
                        RateSelectionContext(
                            product_code_id=row.product_code_id,
                            quote_date=today,
                            origin_airport=origin_airport,
                            destination_airport=destination_airport,
                            currency=buy_currency,
                            agent_id=agent_id,
                            carrier_id=carrier_id,
                        )
                    ),
                    success_outcome=success_outcome,
                    error_outcome=selection_outcome,
                )
            if isinstance(row, ImportSellRate):
                return cls._run_selector(
                    component=component,
                    selector=lambda: select_import_sell_rate(
                        RateSelectionContext(
                            product_code_id=row.product_code_id,
                            quote_date=today,
                            origin_airport=origin_airport,
                            destination_airport=destination_airport,
                            currency=quote_currency,
                        ),
                        allow_pgk_fallback=payment_term_normalized == 'PREPAID' and quote_currency not in {None, 'PGK'},
                    ),
                    success_outcome=success_outcome,
                    error_outcome=selection_outcome,
                )
            if isinstance(row, LocalCOGSRate):
                return cls._run_selector(
                    component=component,
                    selector=lambda: select_local_cogs_rate(
                        RateSelectionContext(
                            product_code_id=row.product_code_id,
                            quote_date=today,
                            location=row.location,
                            direction=row.direction,
                            currency=buy_currency,
                            agent_id=agent_id,
                            carrier_id=carrier_id,
                        )
                    ),
                    success_outcome=success_outcome,
                    error_outcome=selection_outcome,
                )
            if isinstance(row, LocalSellRate):
                return cls._run_selector(
                    component=component,
                    selector=lambda: select_local_sell_rate(
                        RateSelectionContext(
                            product_code_id=row.product_code_id,
                            quote_date=today,
                            location=row.location,
                            direction=row.direction,
                            payment_term=(payment_term_normalized or row.payment_term),
                            currency=quote_currency,
                        ),
                        allow_pgk_fallback=payment_term_normalized == 'PREPAID' and quote_currency not in {None, 'PGK'},
                    ),
                    success_outcome=success_outcome,
                    error_outcome=selection_outcome,
                )
            return cls._missing_rate_outcome(component)

        if direction == 'DOMESTIC':
            domestic_rows = list(
                DomesticCOGS.objects.filter(
                    origin_zone=origin_airport,
                    destination_zone=destination_airport,
                    valid_from__lte=today,
                    valid_until__gte=today,
                ).select_related('product_code')
            ) + list(
                DomesticSellRate.objects.filter(
                    origin_zone=origin_airport,
                    destination_zone=destination_airport,
                    valid_from__lte=today,
                    valid_until__gte=today,
                ).select_related('product_code')
            )
            freight_outcomes = [
                evaluate_row(COMPONENT_FREIGHT, row)
                for row in domestic_rows
                if row.product_code.category == ProductCode.CATEGORY_FREIGHT
            ]
            outcomes[COMPONENT_FREIGHT] = choose_best(COMPONENT_FREIGHT, freight_outcomes)
            return outcomes

        if direction == 'EXPORT':
            export_lane_rows = list(
                ExportCOGS.objects.filter(
                    origin_airport=origin_airport,
                    destination_airport=destination_airport,
                    valid_from__lte=today,
                    valid_until__gte=today,
                ).select_related('product_code')
            ) + list(
                ExportSellRate.objects.filter(
                    origin_airport=origin_airport,
                    destination_airport=destination_airport,
                    valid_from__lte=today,
                    valid_until__gte=today,
                ).select_related('product_code')
            )
            export_local_rows = list(
                LocalCOGSRate.objects.filter(
                    location__in=[loc for loc in [origin_airport, destination_airport] if loc],
                    direction='EXPORT',
                    valid_from__lte=today,
                    valid_until__gte=today,
                ).select_related('product_code')
            ) + list(
                LocalSellRate.objects.filter(
                    location__in=[loc for loc in [origin_airport, destination_airport] if loc],
                    direction='EXPORT',
                    valid_from__lte=today,
                    valid_until__gte=today,
                ).select_related('product_code')
            )

            freight_candidates = [
                evaluate_row(COMPONENT_FREIGHT, row)
                for row in export_lane_rows
                if classify_export_component(row.product_code.code, row.product_code.category) == COMPONENT_FREIGHT
            ]
            origin_candidates = [
                evaluate_row(COMPONENT_ORIGIN_LOCAL, row)
                for row in export_lane_rows + export_local_rows
                if classify_export_component(row.product_code.code, row.product_code.category) == COMPONENT_ORIGIN_LOCAL
            ]
            destination_candidates = [
                evaluate_row(COMPONENT_DESTINATION_LOCAL, row)
                for row in export_lane_rows + export_local_rows
                if classify_export_component(row.product_code.code, row.product_code.category) == COMPONENT_DESTINATION_LOCAL
            ]

            if surcharge := matching_surcharge(COMPONENT_ORIGIN_LOCAL, 'EXPORT_ORIGIN', origin=origin_airport):
                origin_candidates.append(surcharge)
            if surcharge := matching_surcharge(COMPONENT_DESTINATION_LOCAL, 'EXPORT_DEST', destination=destination_airport):
                destination_candidates.append(surcharge)

            outcomes[COMPONENT_FREIGHT] = choose_best(COMPONENT_FREIGHT, freight_candidates)
            outcomes[COMPONENT_ORIGIN_LOCAL] = choose_best(COMPONENT_ORIGIN_LOCAL, origin_candidates)
            outcomes[COMPONENT_DESTINATION_LOCAL] = choose_best(COMPONENT_DESTINATION_LOCAL, destination_candidates)
            outcomes[COMPONENT_ORIGIN_LOCAL] = apply_payment_term_gate(
                outcomes[COMPONENT_ORIGIN_LOCAL],
                COMPONENT_ORIGIN_LOCAL,
                [
                    row for row in export_local_rows
                    if isinstance(row, LocalSellRate)
                    and classify_export_component(row.product_code.code, row.product_code.category) == COMPONENT_ORIGIN_LOCAL
                ],
            )
            outcomes[COMPONENT_DESTINATION_LOCAL] = apply_payment_term_gate(
                outcomes[COMPONENT_DESTINATION_LOCAL],
                COMPONENT_DESTINATION_LOCAL,
                [
                    row for row in export_local_rows
                    if isinstance(row, LocalSellRate)
                    and classify_export_component(row.product_code.code, row.product_code.category) == COMPONENT_DESTINATION_LOCAL
                ],
            )
            return outcomes

        import_lane_rows = list(
            ImportCOGS.objects.filter(
                origin_airport=origin_airport,
                destination_airport=destination_airport,
                valid_from__lte=today,
                valid_until__gte=today,
            ).select_related('product_code')
        ) + list(
            ImportSellRate.objects.filter(
                origin_airport=origin_airport,
                destination_airport=destination_airport,
                valid_from__lte=today,
                valid_until__gte=today,
            ).select_related('product_code')
        )
        import_destination_rows = list(
            LocalCOGSRate.objects.filter(
                location=destination_airport,
                direction='IMPORT',
                valid_from__lte=today,
                valid_until__gte=today,
            ).select_related('product_code')
        ) + list(
            LocalSellRate.objects.filter(
                location=destination_airport,
                direction='IMPORT',
                valid_from__lte=today,
                valid_until__gte=today,
            ).select_related('product_code')
        )

        freight_candidates = [
            evaluate_row(COMPONENT_FREIGHT, row)
            for row in import_lane_rows
            if classify_import_component(row.product_code.code, row.product_code.category) == COMPONENT_FREIGHT
        ]
        origin_candidates = [
            evaluate_row(COMPONENT_ORIGIN_LOCAL, row)
            for row in import_lane_rows
            if classify_import_component(row.product_code.code, row.product_code.category) == COMPONENT_ORIGIN_LOCAL
        ]
        destination_candidates = [
            evaluate_row(COMPONENT_DESTINATION_LOCAL, row)
            for row in import_lane_rows + import_destination_rows
            if classify_import_component(row.product_code.code, row.product_code.category) == COMPONENT_DESTINATION_LOCAL
        ]

        if surcharge := matching_surcharge(COMPONENT_DESTINATION_LOCAL, 'IMPORT_DEST', destination=destination_airport):
            destination_candidates.append(surcharge)

        outcomes[COMPONENT_FREIGHT] = choose_best(COMPONENT_FREIGHT, freight_candidates)
        outcomes[COMPONENT_ORIGIN_LOCAL] = choose_best(COMPONENT_ORIGIN_LOCAL, origin_candidates)
        outcomes[COMPONENT_DESTINATION_LOCAL] = choose_best(COMPONENT_DESTINATION_LOCAL, destination_candidates)
        outcomes[COMPONENT_DESTINATION_LOCAL] = apply_payment_term_gate(
            outcomes[COMPONENT_DESTINATION_LOCAL],
            COMPONENT_DESTINATION_LOCAL,
            [
                row for row in import_destination_rows
                if isinstance(row, LocalSellRate)
                and classify_import_component(row.product_code.code, row.product_code.category) == COMPONENT_DESTINATION_LOCAL
            ],
        )
        return outcomes

    @classmethod
    def get_availability(
        cls,
        origin_airport: str,
        destination_airport: str,
        direction: str,
        service_scope: str,
        payment_term: Optional[str] = None,
        *,
        agent_id: Optional[int] = None,
        carrier_id: Optional[int] = None,
        buy_currency: Optional[str] = None,
        quote_currency: Optional[str] = None,
        quote_date: Optional[date] = None,
    ) -> dict[str, bool]:
        outcomes = cls.get_component_outcomes(
            origin_airport=origin_airport,
            destination_airport=destination_airport,
            direction=direction,
            service_scope=service_scope,
            payment_term=payment_term,
            agent_id=agent_id,
            carrier_id=carrier_id,
            buy_currency=buy_currency,
            quote_currency=quote_currency,
            quote_date=quote_date,
        )
        return {
            component: outcome['status'] in {cls.STATUS_COVERED_EXACT, cls.STATUS_COVERED_FALLBACK}
            for component, outcome in outcomes.items()
        }

    @staticmethod
    def _run_selector(*, component: str, selector, success_outcome, error_outcome) -> dict:
        from pricing_v4.services.rate_selector import RateAmbiguityError, RateNotFoundError

        try:
            return success_outcome(component, selector())
        except (RateNotFoundError, RateAmbiguityError) as exc:
            return error_outcome(component, exc)

    @classmethod
    def _missing_rate_outcome(cls, component: str) -> dict:
        return {
            'component': component,
            'status': cls.STATUS_MISSING_RATE,
            'detail': 'No deterministic rate matched this component.',
            'match_type': None,
            'selector_model': None,
            'selector_context': {},
            'missing_dimensions': [],
            'conflicting_rows': [],
            'fallback_applied': False,
        }


class CommodityRateRuleService:
    """Evaluate commodity-specific ProductCode coverage for a lane/scope."""

    @classmethod
    def evaluate_coverage(
        cls,
        origin_airport: str,
        destination_airport: str,
        direction: str,
        service_scope: str,
        commodity_code: str,
        payment_term: Optional[str] = None,
    ) -> CommodityCoverageResult:
        commodity_code = str(commodity_code or DEFAULT_COMMODITY_CODE).strip().upper() or DEFAULT_COMMODITY_CODE
        if commodity_code == DEFAULT_COMMODITY_CODE:
            return CommodityCoverageResult()

        from pricing_v4.models import CommodityChargeRule

        origin_airport = (origin_airport or "").strip().upper()
        destination_airport = (destination_airport or "").strip().upper()
        direction = (direction or "").strip().upper()
        scope = (service_scope or "A2A").strip().upper()
        if scope == "P2P":
            scope = "A2A"

        payment_term_normalized = (payment_term or "").strip().upper()
        if payment_term_normalized not in {"PREPAID", "COLLECT"}:
            payment_term_normalized = None

        today = date.today()
        rules = (
            CommodityChargeRule.objects
            .filter(
                shipment_type=direction,
                service_scope=scope,
                commodity_code=commodity_code,
                is_active=True,
                effective_from__lte=today,
            )
            .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=today))
            .filter(Q(origin_code__isnull=True) | Q(origin_code='') | Q(origin_code=origin_airport))
            .filter(Q(destination_code__isnull=True) | Q(destination_code='') | Q(destination_code=destination_airport))
            .select_related("product_code")
        )

        if payment_term_normalized:
            rules = rules.filter(
                Q(payment_term__isnull=True) | Q(payment_term='') | Q(payment_term=payment_term_normalized)
            )

        result = CommodityCoverageResult()
        for rule in rules:
            code = str(rule.product_code.code or "").upper()
            if rule.trigger_mode == rule.TRIGGER_MODE_OPTIONAL:
                continue
            if rule.trigger_mode == rule.TRIGGER_MODE_REQUIRES_SPOT:
                result.spot_required_product_codes.append(code)
                continue
            if rule.trigger_mode == rule.TRIGGER_MODE_REQUIRES_MANUAL:
                result.manual_required_product_codes.append(code)
                continue
            if not cls._rule_has_coverage(
                rule=rule,
                origin_airport=origin_airport,
                destination_airport=destination_airport,
                payment_term=payment_term_normalized,
                today=today,
            ):
                result.missing_product_codes.append(code)

        return result

    @classmethod
    def _rule_has_coverage(
        cls,
        *,
        rule,
        origin_airport: str,
        destination_airport: str,
        payment_term: Optional[str],
        today: date,
    ) -> bool:
        from pricing_v4.category_rules import is_local_rate_category
        from pricing_v4.models import (
            DomesticCOGS,
            DomesticSellRate,
            ExportCOGS,
            ExportSellRate,
            ImportCOGS,
            ImportSellRate,
            LocalCOGSRate,
            LocalSellRate,
            Surcharge,
        )
        from pricing_v4.services.rate_selector import (
            RateSelectionContext,
            RateSelectionError,
            select_domestic_cogs_rate,
            select_export_cogs_rate,
            select_export_sell_rate,
            select_import_cogs_rate,
            select_import_sell_rate,
            select_local_cogs_rate,
            select_local_sell_rate,
        )

        product_code = rule.product_code

        if cls._has_matching_surcharge(
            rule=rule,
            origin_airport=origin_airport,
            destination_airport=destination_airport,
            today=today,
        ):
            return True

        if rule.shipment_type == rule.SHIPMENT_TYPE_DOMESTIC:
            try:
                select_domestic_cogs_rate(
                    RateSelectionContext(
                        product_code_id=product_code.id,
                        quote_date=today,
                        origin_zone=origin_airport,
                        destination_zone=destination_airport,
                        currency='PGK',
                    )
                )
                return True
            except RateSelectionError:
                return False

        if is_local_rate_category(product_code.category):
            location_candidates = cls._local_location_candidates(
                shipment_type=rule.shipment_type,
                leg=rule.leg,
                origin_airport=origin_airport,
                destination_airport=destination_airport,
            )
            local_sell_qs = LocalSellRate.objects.filter(
                product_code=product_code,
                direction=rule.shipment_type,
                location__in=location_candidates,
                valid_from__lte=today,
                valid_until__gte=today,
            )

            if payment_term and rule.shipment_type in {rule.SHIPMENT_TYPE_EXPORT, rule.SHIPMENT_TYPE_IMPORT}:
                has_local_sell = False
                for location in location_candidates:
                    try:
                        select_local_sell_rate(
                            RateSelectionContext(
                                product_code_id=product_code.id,
                                quote_date=today,
                                location=location,
                                direction=rule.shipment_type,
                                payment_term=payment_term,
                            ),
                            queryset_override=local_sell_qs.filter(location=location),
                            allow_pgk_fallback=payment_term == "PREPAID",
                        )
                        has_local_sell = True
                        break
                    except RateSelectionError:
                        continue
            else:
                has_local_sell = local_sell_qs.exists()

            # Destination-local commodity lines can price from explicit local sell
            # tariffs even when there is no dedicated LocalCOGSRate row.
            if (
                rule.shipment_type in {rule.SHIPMENT_TYPE_IMPORT, rule.SHIPMENT_TYPE_EXPORT}
                and (rule.leg or "").upper() == "DESTINATION"
            ):
                return has_local_sell

            has_local_cogs = False
            for location in location_candidates:
                try:
                    select_local_cogs_rate(
                        RateSelectionContext(
                            product_code_id=product_code.id,
                            quote_date=today,
                            location=location,
                            direction=rule.shipment_type,
                        )
                    )
                    has_local_cogs = True
                    break
                except RateSelectionError:
                    continue
            if not has_local_cogs:
                return False
            if payment_term and rule.shipment_type in {rule.SHIPMENT_TYPE_EXPORT, rule.SHIPMENT_TYPE_IMPORT}:
                return has_local_sell
            return True

        if rule.shipment_type == rule.SHIPMENT_TYPE_EXPORT:
            try:
                select_export_cogs_rate(
                    RateSelectionContext(
                        product_code_id=product_code.id,
                        quote_date=today,
                        origin_airport=origin_airport,
                        destination_airport=destination_airport,
                    )
                )
                return True
            except RateSelectionError:
                pass
            try:
                select_export_sell_rate(
                    RateSelectionContext(
                        product_code_id=product_code.id,
                        quote_date=today,
                        origin_airport=origin_airport,
                        destination_airport=destination_airport,
                    )
                )
                return True
            except RateSelectionError:
                return False

        if rule.shipment_type == rule.SHIPMENT_TYPE_IMPORT:
            try:
                select_import_cogs_rate(
                    RateSelectionContext(
                        product_code_id=product_code.id,
                        quote_date=today,
                        origin_airport=origin_airport,
                        destination_airport=destination_airport,
                    )
                )
                return True
            except RateSelectionError:
                pass
            try:
                select_import_sell_rate(
                    RateSelectionContext(
                        product_code_id=product_code.id,
                        quote_date=today,
                        origin_airport=origin_airport,
                        destination_airport=destination_airport,
                    )
                )
                return True
            except RateSelectionError:
                return False

        return (
            DomesticCOGS.objects.filter(
                product_code=product_code,
                origin_zone=origin_airport,
                destination_zone=destination_airport,
                valid_from__lte=today,
                valid_until__gte=today,
            ).exists()
            or DomesticSellRate.objects.filter(
                product_code=product_code,
                origin_zone=origin_airport,
                destination_zone=destination_airport,
                valid_from__lte=today,
                valid_until__gte=today,
            ).exists()
        )

    @staticmethod
    def _local_location_candidates(
        *,
        shipment_type: str,
        leg: str,
        origin_airport: str,
        destination_airport: str,
    ) -> list[str]:
        shipment_type = (shipment_type or "").upper()
        leg = (leg or "").upper()
        if shipment_type == "EXPORT":
            return [origin_airport] if leg != "DESTINATION" else [destination_airport]
        if shipment_type == "IMPORT":
            return [origin_airport] if leg == "ORIGIN" else [destination_airport]
        return [origin_airport, destination_airport]

    @staticmethod
    def _has_matching_surcharge(
        *,
        rule,
        origin_airport: str,
        destination_airport: str,
        today: date,
    ) -> bool:
        from pricing_v4.models import Surcharge

        service_types = {
            ("EXPORT", "ORIGIN"): ["EXPORT_ORIGIN", "ALL"],
            ("EXPORT", "MAIN"): ["EXPORT_AIR", "ALL"],
            ("EXPORT", "DESTINATION"): ["EXPORT_DEST", "ALL"],
            ("IMPORT", "ORIGIN"): ["IMPORT_ORIGIN", "ALL"],
            ("IMPORT", "MAIN"): ["IMPORT_AIR", "ALL"],
            ("IMPORT", "DESTINATION"): ["IMPORT_DEST", "ALL"],
            ("DOMESTIC", "ORIGIN"): ["DOMESTIC_AIR", "ALL"],
            ("DOMESTIC", "MAIN"): ["DOMESTIC_AIR", "ALL"],
            ("DOMESTIC", "DESTINATION"): ["DOMESTIC_AIR", "ALL"],
        }.get(((rule.shipment_type or "").upper(), (rule.leg or "").upper()), ["ALL"])

        return Surcharge.objects.filter(
            product_code=rule.product_code,
            rate_side="COGS",
            service_type__in=service_types,
            is_active=True,
            valid_from__lte=today,
            valid_until__gte=today,
        ).filter(
            Q(origin_filter=origin_airport) | Q(origin_filter__isnull=True) | Q(origin_filter='')
        ).filter(
            Q(destination_filter=destination_airport) | Q(destination_filter__isnull=True) | Q(destination_filter='')
        ).exists()


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
        payment_term: str = "PREPAID",
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
        from decimal import Decimal, ROUND_HALF_UP
        from uuid import uuid4
        
        from core.dataclasses import (
            QuoteInput, ShipmentDetails, LocationRef, Piece
        )
        from pricing_v4.adapter import PricingServiceV4Adapter
        from pricing_v4.models import ExportCOGS, ImportCOGS
        
        # Check availability first
        availability = RateAvailabilityService.get_availability(
            origin_airport=origin_code,
            destination_airport=destination_code,
            direction=direction,
            service_scope=service_scope,
            payment_term=payment_term,
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
                currency_code=(
                    origin_loc.country.currency.code
                    if origin_loc.country and getattr(origin_loc.country, "currency", None)
                    else "PGK"
                ),
            )
            dest_ref = LocationRef(
                id=dest_loc.id,
                code=destination_code,
                name=dest_loc.name,
                country_code=dest_loc.country.code if dest_loc.country else "XX",
                currency_code=(
                    dest_loc.country.currency.code
                    if dest_loc.country and getattr(dest_loc.country, "currency", None)
                    else "USD"
                ),
            )
            
            # Determine shipment type
            shipment_type = "EXPORT" if direction == "EXPORT" else "IMPORT"
            if direction == "DOMESTIC":
                shipment_type = "DOMESTIC"
            
            shipment = ShipmentDetails(
                mode="AIR",
                shipment_type=shipment_type,
                incoterm="EXW" if direction == "EXPORT" else "DDU",
                payment_term=str(payment_term or "PREPAID").upper(),
                commodity_code=commodity or "GCR",
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

            # Enrich with raw COGS rows where available so we can preserve rule metadata
            # such as min_charge for MIN_OR_PER_KG rows.
            cogs_by_code = {}
            if direction in {"EXPORT", "IMPORT"}:
                cogs_model = ExportCOGS if direction == "EXPORT" else ImportCOGS
                active_cogs = (
                    cogs_model.objects.filter(
                        origin_airport=origin_code,
                        destination_airport=destination_code,
                        valid_from__lte=date.today(),
                        valid_until__gte=date.today(),
                        product_code__code__in=[l.service_component_code for l in standard_lines],
                    )
                    .select_related("product_code", "carrier", "agent")
                    .order_by("product_code__code", "-valid_from", "id")
                )
                for row in active_cogs:
                    code = getattr(row.product_code, "code", None)
                    if code:
                        cogs_by_code.setdefault(code, []).append(row)

            def _normalize_text(value):
                return str(value or "").strip().lower()

            def _counterparty_tokens(row):
                tokens = set()
                for cp in (getattr(row, "carrier", None), getattr(row, "agent", None)):
                    if not cp:
                        continue
                    for raw in (str(cp), getattr(cp, "name", None), getattr(cp, "code", None)):
                        token = _normalize_text(raw)
                        if token:
                            tokens.add(token)
                return tokens

            def _as_decimal(value):
                if value is None:
                    return None
                try:
                    return Decimal(str(value))
                except Exception:
                    return None

            def _to_amount_str(value):
                dec = _as_decimal(value)
                if dec is None:
                    return "0.00"
                return str(dec.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

            def _choose_matching_cogs_row(line):
                candidates = cogs_by_code.get(line.service_component_code) or []
                if not candidates:
                    return None
                if len(candidates) == 1:
                    return candidates[0]

                target_source = _normalize_text(getattr(line, "cost_source", None))
                target_currency = _normalize_text(getattr(line, "cost_fcy_currency", None))
                target_cost = _as_decimal(getattr(line, "cost_fcy", None)) or _as_decimal(getattr(line, "cost_pgk", None))
                target_bucket = _normalize_text(getattr(line, "bucket", None))

                def score(row):
                    row_score = 0
                    row_tokens = _counterparty_tokens(row)
                    row_currency = _normalize_text(getattr(row, "currency", None))
                    row_rate_per_kg = _as_decimal(getattr(row, "rate_per_kg", None))
                    row_rate_per_shipment = _as_decimal(getattr(row, "rate_per_shipment", None))
                    row_min_charge = _as_decimal(getattr(row, "min_charge", None))

                    if target_bucket == "airfreight" and getattr(row, "carrier_id", None):
                        row_score += 40
                    if target_bucket in {"origin_charges", "destination_charges"} and getattr(row, "agent_id", None):
                        row_score += 40

                    if target_source and target_source != "v4 engine":
                        if target_source in row_tokens:
                            row_score += 200
                        elif any(target_source in token or token in target_source for token in row_tokens):
                            row_score += 120

                    if target_currency and row_currency and target_currency == row_currency:
                        row_score += 40

                    if target_cost is not None:
                        if row_rate_per_kg is not None and row_rate_per_kg == target_cost:
                            row_score += 80
                        if row_rate_per_shipment is not None and row_rate_per_shipment == target_cost:
                            row_score += 80
                        if row_min_charge is not None and row_min_charge == target_cost:
                            row_score += 80

                    return row_score

                return max(candidates, key=score)
            
            # Convert to SPEChargeLine format
            result = []
            for line in standard_lines:
                # Skip lines with missing rates
                if line.is_rate_missing:
                    continue
                # DB-backed prefill only: exclude hardcoded default/fallback rates.
                if str(getattr(line, "cost_source", "")).strip().lower() == "default":
                    continue
                
                # Map bucket
                bucket_map = {
                    "airfreight": "airfreight",
                    "origin_charges": "origin_charges",
                    "destination_charges": "destination_charges",
                }
                bucket = bucket_map.get(line.bucket, "origin_charges")
                
                cogs_row = _choose_matching_cogs_row(line)

                # SPOT prefill must only carry raw costs. SELL-only lines are skipped.
                cost_fcy = _as_decimal(getattr(line, "cost_fcy", None))
                cost_pgk = _as_decimal(getattr(line, "cost_pgk", None))
                if cost_fcy is not None and cost_fcy > 0:
                    raw_amount = cost_fcy
                    currency = str(getattr(line, "cost_fcy_currency", None) or "PGK").upper()
                elif cost_pgk is not None and cost_pgk > 0:
                    raw_amount = cost_pgk
                    currency = "PGK"
                else:
                    continue

                unit = "per_shipment"
                amount = _to_amount_str(raw_amount)
                min_charge = None
                calculation_type = None
                unit_type = None
                rate = None
                min_amount = None

                # Prefer raw COGS row metadata only for unit/min-charge shape inference.
                # Do not use COGS numeric values for amount/rate.
                if cogs_row is not None:
                    row_rate_per_kg = getattr(cogs_row, "rate_per_kg", None)
                    row_rate_per_shipment = getattr(cogs_row, "rate_per_shipment", None)
                    row_min_charge = getattr(cogs_row, "min_charge", None)

                    if row_rate_per_kg is not None:
                        if row_min_charge is not None:
                            unit = "min_or_per_kg"
                            min_charge = str(row_min_charge)
                            min_amount = str(row_min_charge)
                            calculation_type = "min_or_per_unit"
                        else:
                            unit = "per_kg"
                            calculation_type = "per_unit"
                        unit_type = "kg"
                        rate = amount
                    elif row_rate_per_shipment is not None:
                        unit = "per_shipment"
                        calculation_type = "flat"
                        unit_type = "shipment"
                        rate = amount
                else:
                    line_cost_source = str(getattr(line, "cost_source", "")).lower()
                    if "per_kg" in line_cost_source or line.service_component_code in ["FREIGHT", "AIRFREIGHT"]:
                        unit = "per_kg"
                        calculation_type = "per_unit"
                        unit_type = "kg"
                        rate = amount
                    else:
                        calculation_type = "flat"
                        unit_type = "shipment"
                        rate = amount

                result.append({
                    "code": line.service_component_code,
                    "description": line.service_component_desc,
                    "amount": amount,
                    "currency": currency,
                    "unit": unit,
                    "bucket": bucket,
                    "is_primary_cost": line.service_component_code in ["FREIGHT", "AIRFREIGHT", "DOMESTIC_FREIGHT", "EXP-FRT-AIR", "IMP-FRT-AIR"],
                    "conditional": False,
                    "min_charge": min_charge,
                    "calculation_type": calculation_type,
                    "unit_type": unit_type,
                    "rate": rate,
                    "min_amount": min_amount,
                    "rule_meta": {},
                    "source_reference": f"Standard Rate ({line.cost_source})",
                })
            logger.info(
                "StandardChargeService prefill for %s %s->%s scope=%s returned %s charges",
                direction, origin_code, destination_code, service_scope, len(result)
            )
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
        
        return True, None
    
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
        
        The envelope must be acknowledged before transitioning to READY status.
        """
        now = datetime.now()
        
        return SpotPricingEnvelope(
            id=str(uuid4()),
            status=SPEStatus.DRAFT,
            shipment=shipment,
            charges=charges,
            conditions=conditions,
            acknowledgement=None,
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
    def mark_ready(cls, spe: SpotPricingEnvelope) -> SpotPricingEnvelope:
        """
        Transition SPE to READY status.
        
        Only valid if:
        - Currently in DRAFT
        - Acknowledgement present
        """
        if spe.status != SPEStatus.DRAFT:
            raise ValueError(f"Cannot mark SPE as ready from status '{spe.status.value}'")
        
        if spe.acknowledgement is None:
            raise ValueError("Cannot mark SPE as ready without acknowledgement")

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
        branding: Optional[QuoteBrandingContext] = None,
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
        company_name = (branding.display_name if branding else "") or "RateEngine"
        sender = user_name or company_name
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
        signature_parts = [sender]
        signature_text = (branding.email_signature_text if branding else "").strip()
        if signature_text:
            signature_parts = [signature_text]
        else:
            if branding and branding.support_email:
                signature_parts.append(f"Email: {branding.support_email}")
            if branding and branding.support_phone:
                signature_parts.append(f"Phone: {branding.support_phone}")
        signature_block = "\n".join(signature_parts)

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
{signature_block}"""
        
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
            AnalysisSafetySignals,
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
            safety_signals=AnalysisSafetySignals(),
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
            AnalysisSafetySignals,
            ReplyAnalysisResult,
        )

        genai = get_gemini_client()
        ai_unavailable = genai is None
        ai_assertions = []
        ai_result = None
        safety_signals = AnalysisSafetySignals()
        
        if genai:
            # Call existing AI service with context to help it categorize
            ai_result = parse_rate_quote_text(raw_text, context=shipment_context)
            audit_result = getattr(ai_result, "extraction_audit", None)
            quote_input = getattr(ai_result, "quote_input", None)
            lines = getattr(quote_input, "charge_lines", []) if quote_input else []
            unmapped_line_count = sum(
                1
                for line in lines
                if getattr(line, "v4_product_code", None) == "UNMAPPED"
            )
            low_confidence_line_count = sum(
                1
                for line in lines
                if getattr(line, "normalization_confidence", None) == "LOW"
            )
            conditional_charge_count = sum(1 for line in lines if getattr(line, "conditional", False))
            safety_signals = AnalysisSafetySignals(
                raw_charge_count=len(getattr(ai_result, "raw_extracted_charges", []) or []),
                normalized_charge_count=len(getattr(ai_result, "normalized_charges", []) or []),
                imported_charge_count=len(lines),
                unmapped_line_count=unmapped_line_count,
                low_confidence_line_count=low_confidence_line_count,
                conditional_charge_count=conditional_charge_count,
                critic_safe_to_proceed=getattr(audit_result, "is_safe_to_proceed", None),
                critic_missed_charges=list(getattr(audit_result, "missed_charges", []) or []),
                critic_hallucinations=list(getattr(audit_result, "hallucinations_detected", []) or []),
                pdf_fallback_used=any(
                    "pdf extraction fallback" in str(w).lower()
                    for w in (getattr(ai_result, "warnings", []) or [])
                ),
            )
            logger.info(
                "AI analysis result: success=%s lines=%s warnings=%s raw=%s normalized=%s audit_safe=%s unmapped=%s",
                getattr(ai_result, "success", None),
                len(lines),
                len(getattr(ai_result, "warnings", []) or []),
                len(getattr(ai_result, "raw_extracted_charges", []) or []),
                len(getattr(ai_result, "normalized_charges", []) or []),
                getattr(audit_result, "is_safe_to_proceed", None),
                unmapped_line_count,
            )
            if getattr(ai_result, "success", False) or lines:
                # Add global currency assertion if present
                if getattr(ai_result, "quote_currency", None):
                    ai_assertions.append(ExtractedAssertion(
                        text=f"Quote Currency: {ai_result.quote_currency}",
                        category=AssertionCategory.CURRENCY,
                        status=AssertionStatus.CONFIRMED,
                        confidence=0.95,
                        rate_currency=ai_result.quote_currency
                    ))

                for line in lines:
                    # Map SpotChargeLine to ExtractedAssertion
                    category = AssertionCategory.RATE
                    if line.bucket == "ORIGIN":
                        category = AssertionCategory.ORIGIN_CHARGES
                    elif line.bucket == "DESTINATION":
                        category = AssertionCategory.DEST_CHARGES

                    is_unmapped = getattr(line, "v4_product_code", None) == "UNMAPPED"
                    has_low_norm_conf = getattr(line, "normalization_confidence", None) == "LOW"
                     
                    # Fallback to quote currency if line currency is missing
                    final_currency = line.currency or ai_result.quote_currency
                    
                    # For MIN_OR_PER_KG, use minimum as the display amount
                    display_amount = getattr(line, "min_amount", None) if getattr(line, "min_amount", None) is not None else line.amount
                    # For PERCENTAGE, use percentage value as the display amount
                    if line.unit_basis == "PERCENTAGE" and getattr(line, "percentage", None) is not None:
                        display_amount = line.percentage
                        
                    basis = getattr(line, 'percent_basis', None) or getattr(line, 'percent_applies_to', None)

                    assertion_status = (
                        AssertionStatus.CONDITIONAL if line.conditional
                        else AssertionStatus.CONFIRMED
                    )
                    assertion_confidence = line.confidence or 0.9
                    if is_unmapped:
                        assertion_confidence = min(assertion_confidence, 0.35)
                    elif has_low_norm_conf:
                        assertion_confidence = min(assertion_confidence, 0.5)

                    ai_assertions.append(ExtractedAssertion(
                        text=line.description,
                        category=category,
                        status=assertion_status,
                        confidence=assertion_confidence,
                        source_line=getattr(line, "source_line_number", None),
                        source_excerpt=getattr(line, "source_excerpt", None),
                        source_line_identity=getattr(line, "source_line_identity", None),
                        rate_amount=display_amount,
                        rate_per_unit=line.rate_per_unit,
                        rate_currency=final_currency,
                        rate_unit=line.unit_basis.lower() if line.unit_basis else "per_kg",
                        percentage_basis=basis,
                    ))
        
        all_assertions = ai_assertions
        
        # Build summary
        summary = cls._build_summary(all_assertions)
        
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
                "Install google-genai and set GEMINI_API_KEY."
            )
        
        # Add AI warnings to our warnings list
        if genai and ai_result:
            audit_result = getattr(ai_result, "extraction_audit", None)
            if audit_result:
                if audit_result.missed_charges:
                    warnings.append(
                        "⚠️ Possible missed charges: "
                        + ", ".join(audit_result.missed_charges)
                    )
                if audit_result.hallucinations_detected:
                    warnings.append(
                        "⚠️ Please verify these charges: "
                        + ", ".join(audit_result.hallucinations_detected)
                    )

            unmapped_labels = [
                line.description
                for line in (getattr(ai_result.quote_input, "charge_lines", []) if ai_result.quote_input else [])
                if getattr(line, "v4_product_code", None) == "UNMAPPED"
            ]
            if unmapped_labels:
                warnings.append(
                    "⚠️ Some imported charges need manual review: "
                    + ", ".join(unmapped_labels)
                )

            if not getattr(ai_result, "success", False):
                warnings.append(f"⚠️ Import analysis failed: {getattr(ai_result, 'error', 'Unknown error')}. Falling back to standard rates.")
            elif getattr(ai_result, "warnings", None):
                for w in ai_result.warnings:
                    warnings.append(f"⚠️ {w}")

        return ReplyAnalysisResult(
            raw_text=raw_text,
            assertions=all_assertions,
            summary=summary,
            warnings=warnings,
            safety_signals=safety_signals,
        )



    @classmethod
    def _build_summary(cls, assertions: List['ExtractedAssertion']) -> 'AnalysisSummary':
        """Build summary from assertions."""
        from quotes.reply_schemas import (
            AssertionStatus,
            AssertionCategory,
            AnalysisSummary,
        )
        
        summary = AnalysisSummary()
        
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
        
        # Only surface warnings that require a pricing decision or follow-up.
        # Routine AI assumptions should not be promoted into review warnings.
        # Mandatory field warnings
        if not summary.has_rate:
            warnings.append("⛔ MISSING: Airfreight rate is required")
        if not summary.has_currency:
            warnings.append("⛔ MISSING: Rate currency is required")
        
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

        missing_component_codes: set[str] | None = None
        shipment_type = None
        missing_components_set: set[str] = set()
        if shipment_context:
            shipment_type = _shipment_type_from_context(shipment_context)
            raw_missing = shipment_context.get("missing_components") or []
            if isinstance(raw_missing, (list, tuple, set)):
                missing_components_set = {str(item).upper() for item in raw_missing if item}
            missing_component_codes = missing_components_set if missing_components_set else None

        for a in analysis.assertions:
            # Skip missing and implicit assertions — only confirmed/conditional AI charges.
            if a.status == AssertionStatus.MISSING:
                continue
            if a.status == AssertionStatus.IMPLICIT:
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

            # Only populate components that are missing DB rates.
            if missing_component_codes is not None and component_code not in missing_component_codes:
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

            final_source_ref = source_reference

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
                "source_reference": final_source_ref,
                "source_excerpt": a.source_excerpt or a.text,
                "source_line_number": a.source_line,
                "source_line_identity": (
                    a.source_line_identity
                    or (f"assertion-line:{a.source_line}" if a.source_line is not None else None)
                ),
            })

        return charges

