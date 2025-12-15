# backend/pricing_v2/pricing_service_v3.py

"""
V3 Pricing Service.

This service is responsible for orchestrating the entire quote calculation
process.
"""

import json
import logging
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Optional, Dict, Any
from django.utils import timezone
import uuid

# --- UPDATED IMPORTS ---
# We now import the *correct* V3 dataclasses and remove the old ones.
from .dataclasses_v3 import (
    QuoteInput,
    QuoteCharges,
    ShipmentDetails,
    Piece,
    ManualOverride,
    CalculatedChargeLine,
    CalculatedTotals,
    LocationRef,
)
# --- END UPDATED IMPORTS ---
from quotes.tax_policy import apply_gst_policy

from core.models import FxSnapshot, Policy, Location
from core.routing import RoutingValidator, CargoConstraintViolation
from ratecards.models import PartnerRateLane, PartnerRate
from services.models import ServiceComponent, ServiceRule

# A constant for our home currency
HOME_CURRENCY = "PGK"
DEFAULT_POLICY_NAME = "Default Policy"
logger = logging.getLogger(__name__)

# Import A2D DAP passthrough pricing
from .a2d_dap_pricing import (
    is_a2d_dap_quote,
    calculate_a2d_dap_charges,
    get_a2d_dap_currency,
)

# --------------------

class PricingServiceV3:
    """
    Orchestrates the V3 quote calculation logic.
    
    1. Fetches relevant data (Policy, FX, Rates).
    2. Calculates all charge lines.
    3. Applies margins and taxes.
    4. Returns a structured QuoteCharges object.
    """
    
    def __init__(self, quote_input: QuoteInput):
        self.quote_input = quote_input
        self.shipment = quote_input.shipment

        self.context = self._build_calculation_context()
        self.sell_lines: List[CalculatedChargeLine] = []
        self.calculated_component_costs = {}
        self.service_rule: Optional[ServiceRule] = None
        self.output_currency_code: str = quote_input.output_currency or HOME_CURRENCY
        self.context['service_rule'] = None
        self.override_map = {override.service_component_id: override for override in quote_input.overrides}

        # Intelligent routing: determine required service level based on cargo dimensions
        self.required_service_level: str = 'STANDARD'
        self.routing_reason: Optional[str] = None
        self.routing_violations: List[CargoConstraintViolation] = []
        self._determine_routing()

    def calculate_charges(self) -> QuoteCharges:
        """
        Main entry point for the calculation.
        """
        # --- A2D DAP PASSTHROUGH CHECK ---
        # For Import + Prepaid + A2D + DAP quotes, use passthrough pricing
        # No FX, CAF, or margin applied - rates are already in FCY
        if self._is_a2d_dap_quote():
            return self._calculate_a2d_dap_passthrough()
        
        self._resolve_service_rule()
        # 1. Get all applicable service components
        service_components = self._get_service_components()
        self._apply_output_currency_policy()
        
        # 1.1 Inject DST_CHARGES if in spot_rates but not in components
        spot_rates = getattr(self.quote_input, 'spot_rates', {})
        if 'DST_CHARGES' in spot_rates:
            has_dst = any(c.code == 'DST_CHARGES' for c in service_components)
            if not has_dst:
                # Need to fetch the component definition
                try:
                    dst_comp = ServiceComponent.objects.get(code='DST_CHARGES')
                    service_components.append(dst_comp)
                except ServiceComponent.DoesNotExist:
                    logger.warning("DST_CHARGES component not found, cannot inject spot rate.")

        service_components = sorted(
            service_components,
            key=lambda comp: 1 if self._is_percentage_based_component(comp) else 0
        )

        # Check for All-In Spot Rate on Freight
        frt_spot = spot_rates.get('FRT_AIR_EXP')
        suppress_surcharges = False
        if frt_spot and isinstance(frt_spot, dict) and frt_spot.get('is_all_in'):
            suppress_surcharges = True
            logger.info("Spot Rate is All-In. Suppressing Carrier Surcharges.")

        # 2. Calculate each line
        for component in service_components:
            # If All-In, skip specific carrier surcharges
            if suppress_surcharges and component.code in ['FRT_AIR_FUEL', 'SECURITY_SELL', 'AWB_FEE_SELL']:
                continue

            override = self.override_map.get(component.id)
            buy_rate = None
            if override:
                cost_info = self._calculate_override_cost(component, override)
            else:
                buy_rate = self._get_buy_rate(component)
                cost_info = self._calculate_buy_cost(component, buy_rate)

            self.calculated_component_costs[component.code] = cost_info
            sell_rate = self._calculate_sell_rate(component, cost_info['cost_pgk'])
            line = self._create_charge_line(component, buy_rate, cost_info, sell_rate)
            self.sell_lines.append(line)

        # 3. Sum totals
        totals = self._calculate_totals()
        
        return QuoteCharges(lines=self.sell_lines, totals=totals)

    def get_fx_snapshot(self) -> FxSnapshot:
        return self.context['fx_snapshot']

    def get_policy(self) -> Policy:
        return self.context['policy']

    # --- EXPORT SCENARIO HELPERS ---
    def _is_export_prepaid_d2a(self) -> bool:
        return (
            self.shipment.shipment_type == 'EXPORT' and
            self.shipment.payment_term == 'PREPAID' and
            self.shipment.service_scope == 'D2A'
        )

    def _is_export_prepaid_d2d(self) -> bool:
        return (
            self.shipment.shipment_type == 'EXPORT' and
            self.shipment.payment_term == 'PREPAID' and
            self.shipment.service_scope == 'D2D'
        )

    def _is_export_collect_d2a(self) -> bool:
        return (
            self.shipment.shipment_type == 'EXPORT' and
            self.shipment.payment_term == 'COLLECT' and
            self.shipment.service_scope == 'D2A'
        )
    # -------------------------------

    def _is_a2d_dap_quote(self) -> bool:
        """
        Check if this quote qualifies for A2D DAP passthrough pricing.
        Criteria: IMPORT + PREPAID + A2D + DAP
        """
        return is_a2d_dap_quote(
            shipment_type=self.shipment.shipment_type,
            service_scope=self.shipment.service_scope,
            incoterm=self.shipment.incoterm,
            payment_term=self.shipment.payment_term,
        )

    def _calculate_a2d_dap_passthrough(self) -> QuoteCharges:
        """
        Calculate charges for A2D DAP quotes.
        
        For PREPAID (partner agent):
        - No FX conversion (rates already in FCY)
        - No margin applied
        - Output in AUD/USD
        
        For COLLECT (local customer):
        - Convert FCY rates to PGK with FX
        - Apply margin
        - Output in PGK
        """
        # Get origin country code
        origin_country = 'AU'  # Default
        if self.shipment.origin_location:
            origin_country = self.shipment.origin_location.country_code or 'AU'
        
        # Get payment term
        payment_term = self.shipment.payment_term or 'PREPAID'
        
        # Get margin for COLLECT
        margin_pct = self.context['policy'].margin_pct if payment_term == 'COLLECT' else Decimal('0')
        
        # Calculate using A2D DAP module (returns Pydantic model)
        result = calculate_a2d_dap_charges(
            origin_country_code=origin_country,
            payment_term=payment_term,
            chargeable_weight_kg=self.context['chargeable_weight_kg'],
            fx_snapshot=self.context.get('fx_snapshot'),
            margin_pct=margin_pct,
        )
        
        # Is this passthrough (PREPAID) or converted (COLLECT)?
        is_passthrough = result.is_passthrough
        is_collect = (payment_term == 'COLLECT')
        
        # Convert to standard charge lines
        lines = []
        for line in result.lines:
            if line.component == 'AGENCY_EXP':
                print(f"DEBUG: Processing AGENCY_EXP in A2D DAP. CostType={line.cost_type if hasattr(line, 'cost_type') else 'N/A'}")
            # Get service component ID from database
            from services.models import ServiceComponent
            try:
                svc_comp = ServiceComponent.objects.get(code=line.component)
                svc_id = svc_comp.id
                svc_desc = svc_comp.description
            except ServiceComponent.DoesNotExist:
                import uuid as uuid_mod
                svc_id = uuid_mod.uuid4()  # Fallback
                svc_desc = line.description
            
            # Currency handling:
            # - PREPAID: Amount is in FCY (AUD/USD) - goes to sell_fcy, sell_pgk = 0 (no PGK conversion)
            # - COLLECT: Amount is in PGK with 10% GST - goes to sell_pgk, sell_fcy = 0 (already in local currency)
            if is_collect:
                # COLLECT: PGK with 10% GST
                gst_rate = Decimal('0.10')  # 10% GST for PNG local
                sell_pgk = line.sell_amount
                gst_amount = (sell_pgk * gst_rate).quantize(Decimal('0.01'))
                sell_pgk_incl_gst = sell_pgk + gst_amount
                sell_fcy = Decimal('0')
                sell_fcy_incl_gst = Decimal('0')
                sell_fcy_currency = None
                cost_pgk = line.cost_amount
            else:
                # PREPAID: FCY passthrough (AUD/USD) - no GST for overseas partner agent
                sell_pgk = Decimal('0')  # No PGK value - this is FCY passthrough
                sell_pgk_incl_gst = Decimal('0')
                sell_fcy = line.sell_amount  # The FCY amount
                sell_fcy_incl_gst = line.sell_amount  # No GST for FCY
                sell_fcy_currency = line.sell_currency  # AUD or USD
                cost_pgk = Decimal('0')  # No PGK cost - FCY passthrough
            
            # Create CalculatedChargeLine from Pydantic model
            charge_line = CalculatedChargeLine(
                service_component_id=svc_id,
                service_component_code=line.component,
                service_component_desc=svc_desc,
                leg='DESTINATION',
                # Cost values
                cost_pgk=cost_pgk,
                cost_fcy=line.cost_amount,
                cost_fcy_currency=line.cost_currency,
                exchange_rate=line.exchange_rate,
                # Sell values
                sell_pgk=sell_pgk,
                sell_pgk_incl_gst=sell_pgk_incl_gst,
                sell_fcy=sell_fcy,
                sell_fcy_incl_gst=sell_fcy_incl_gst,
                sell_fcy_currency=sell_fcy_currency,
                cost_source='A2D_DAP_RATECARD',
                cost_source_description=f"A2D DAP {result.currency} Rate Card ({payment_term})",
                is_rate_missing=False,
            )
            lines.append(charge_line)
        
        # Create totals
        if is_collect:
            # COLLECT: Total is in PGK with 10% GST
            gst_rate = Decimal('0.10')
            total_sell_pgk = result.totals.total_sell
            total_gst = (total_sell_pgk * gst_rate).quantize(Decimal('0.01'))
            total_sell_pgk_incl_gst = total_sell_pgk + total_gst
            total_sell_fcy = Decimal('0')
            total_sell_fcy_incl_gst = Decimal('0')
        else:
            # PREPAID: Total is in FCY (AUD/USD) - no GST
            total_sell_pgk = Decimal('0')  # No PGK total - FCY passthrough
            total_sell_pgk_incl_gst = Decimal('0')
            total_sell_fcy = result.totals.total_sell
            total_sell_fcy_incl_gst = result.totals.total_sell
        
        totals = CalculatedTotals(
            total_cost_pgk=result.totals.total_pgk_internal,
            total_sell_pgk=total_sell_pgk,
            total_sell_pgk_incl_gst=total_sell_pgk_incl_gst,
            total_sell_fcy=total_sell_fcy,
            total_sell_fcy_incl_gst=total_sell_fcy_incl_gst,
            total_sell_fcy_currency=result.totals.total_sell_currency,
            has_missing_rates=False,
            notes=f"A2D DAP {payment_term} Quote - {result.currency}",
        )
        
        # Store metadata for UI
        self.is_a2d_dap = True
        self.a2d_dap_currency = result.currency
        self.a2d_dap_payment_term = payment_term
        self.show_pgk_to_client = result.show_pgk_to_client
        
        return QuoteCharges(lines=lines, totals=totals)

    def _build_calculation_context(self) -> dict:
        """
        Pre-fetches all common data needed for the calculation.
        """
        # --- 1. Calculate Chargeable Weight ---
        # Logic: Iterate through all pieces to find the Max(Total Gross, Total Volumetric)
        # Standard Air Freight Divisor: 6000 ccm/kg

        total_gross_weight = Decimal("0.00")
        total_volumetric_weight = Decimal("0.00")
        volumetric_divisor = Decimal("6000.0")

        for piece in self.shipment.pieces:
            # A. Sum up the physical gross weight
            # Assumption: piece.gross_weight_kg is the TOTAL weight for this line (all pieces)
            total_gross_weight += piece.gross_weight_kg
            
            # B. Calculate volumetric weight for this line
            # Formula: (L x W x H) / 6000 * Number of Pieces
            volume_per_piece_kg = (piece.length_cm * piece.width_cm * piece.height_cm) / volumetric_divisor
            total_volumetric_weight += (volume_per_piece_kg * piece.pieces)

        # The Chargeable Weight is whichever is heavier
        chargeable_weight_kg = max(total_gross_weight, total_volumetric_weight)
        
        # Round to 2 decimal places for calculation consistency
        chargeable_weight_kg = chargeable_weight_kg.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        # --------------------------------------

        # Get the latest active policy and FX snapshot
        # In a real app, you might want to handle "Policy.DoesNotExist" errors gracefully here
        policy = Policy.objects.filter(is_active=True).latest('effective_from')
        fx_snapshot = FxSnapshot.objects.latest('as_of_timestamp')

        return {
            "policy": policy,
            "fx_snapshot": fx_snapshot,
            "chargeable_weight_kg": chargeable_weight_kg,
            "home_currency": HOME_CURRENCY,
        }

    def _get_service_components(self) -> List[ServiceComponent]:
        """
        Gets the list of services to be quoted based on the incoterm.
        Updated for Export Logic:
        - Exclude DST_CHARGES for Export D2A
        - Inject DST_CHARGES for Export D2D if missing
        """
        service_rule_components = self._get_service_rule_components()
        
        # If no rule found, just return empty list (or detailed log)
        if not service_rule_components:
            logger.warning(
                "No ServiceRule resolved for %s %s %s %s",
                self.shipment.mode,
                self.shipment.shipment_type,
                self.shipment.incoterm,
                getattr(self.shipment, "service_scope", None),
            )
            return []

        # --- EXPORT LOGIC: Filter Components ---
        final_components = []
        has_dst_charges = False
        
        for comp in service_rule_components:
            # Scenario: Export D2A -> EXCLUDE destination charges
            if (self._is_export_prepaid_d2a() or self._is_export_collect_d2a()) and comp.code == 'DST_CHARGES':
                continue
            
            if comp.code == 'DST_CHARGES':
                has_dst_charges = True
                
            final_components.append(comp)
            
        # Scenario: Export Prepaid D2D -> REQUIRE destination charges
        if self._is_export_prepaid_d2d() and not has_dst_charges:
            try:
                dst_comp = ServiceComponent.objects.get(code='DST_CHARGES')
                final_components.append(dst_comp)
                logger.info("Injected DST_CHARGES for Export Prepaid D2D")
            except ServiceComponent.DoesNotExist:
                logger.error("DST_CHARGES component missing in DB")

        return final_components

    def _get_service_rule_components(self) -> Optional[List[ServiceComponent]]:
        """
        Returns resolved ServiceRule components if a rule is loaded.
        """
        if not self.service_rule:
            return None

        rule_components = (
            self.service_rule.rule_components.select_related('service_component')
            .order_by('sequence', 'service_component__code')
        )
        components: List[ServiceComponent] = []
        for rc in rule_components:
            component = rc.service_component
            if component.is_active:
                components.append(component)
        return components

    def _resolve_service_rule(self) -> None:
        """
        Resolves the ServiceRule matching the shipment context, if any.
        """
        service_scope = getattr(self.shipment, "service_scope", None)
        if not service_scope:
            self.service_rule = None
            self.context["service_rule"] = None
            return

        incoterm = self.shipment.incoterm or None
        
        # Helper to find best rule
        def find_rule(_incoterm):
            return (
                ServiceRule.objects.filter(
                    mode=self.shipment.mode,
                    direction=self.shipment.shipment_type,
                    incoterm=_incoterm,
                    payment_term=self.shipment.payment_term,
                    service_scope=service_scope,
                    is_active=True,
                )
                .order_by("-effective_from")
                .first()
            )

        rule = find_rule(incoterm)

        self.service_rule = rule
        self.context["service_rule"] = rule

    def _apply_output_currency_policy(self) -> None:
        """
        Applies ServiceRule-driven currency logic when available.
        """
        derived_currency = self._derive_currency_from_rule(self.service_rule)

        if derived_currency:
            self.output_currency_code = derived_currency

    def _derive_currency_from_rule(self, rule: Optional[ServiceRule]) -> Optional[str]:
        """
        Determines the output currency based on the business logic.
        """
        # 1. Export Prepaid D2A/D2D -> PGK
        if self._is_export_prepaid_d2a() or self._is_export_prepaid_d2d():
            return "PGK"
            
        # 2. Export Collect D2A -> AUD/USD
        if self._is_export_collect_d2a():
            dest = self.shipment.destination_location
            if dest and dest.country_code == 'AU':
                return "AUD"
            return "USD"

        # 3. Fallback to ServiceRule configuration
        if not rule:
            return None
            
        ccy_type = rule.output_currency_type or "DESTINATION"
        if ccy_type == "PGK":
            return HOME_CURRENCY
        if ccy_type == "USD":
            return "USD"
        if ccy_type == "ORIGIN":
            code = self._get_origin_currency_code()
            return code or HOME_CURRENCY
        if ccy_type == "ORIGIN_AU_USD":
            # Import Prepaid A2D: AU origin → AUD, else → USD
            origin = getattr(self.shipment, "origin_location", None)
            if origin and origin.country_code == "AU":
                return "AUD"
            return "USD"
        if ccy_type == "DESTINATION":
            code = self._get_destination_currency_code()
            return code or HOME_CURRENCY
        return None

    def _get_origin_currency_code(self) -> Optional[str]:
        location = getattr(self.shipment, "origin_location", None)
        if not location:
            return None
        return location.currency_code

    def _get_destination_currency_code(self) -> Optional[str]:
        location = getattr(self.shipment, "destination_location", None)
        if not location:
            return None
        return location.currency_code

    def get_output_currency(self) -> str:
        return self.output_currency_code

    def _determine_routing(self):
        """
        Determines the required routing/service level based on cargo dimensions.
        Uses RoutingValidator to check cargo against aircraft constraints.
        """
        # Only run validation if we have origin/destination and cargo dimensions
        if not self.shipment.origin_location or not self.shipment.destination_location:
            return
        
        if not self.shipment.pieces:
            return
        
        # Convert Piece dataclasses to dict format for RoutingValidator
        # Note: Converting Decimal to float for RoutingValidator input. This may lead to minor precision loss.
        # If RoutingValidator can support Decimal directly, it would be preferable.
        pieces_dict = []
        for piece_line in self.shipment.pieces:
            # Each piece_line could represent multiple identical pieces
            for _ in range(piece_line.pieces):
                pieces_dict.append({
                    'length_cm': float(piece_line.length_cm),
                    'width_cm': float(piece_line.width_cm),
                    'height_cm': float(piece_line.height_cm),
                    'weight_kg': float(piece_line.gross_weight_kg)
                })
        
        # Use RoutingValidator to determine required service level
        validator = RoutingValidator()
        service_level, reason, violations = validator.determine_required_service_level(
            origin_code=self.shipment.origin_location.code,
            destination_code=self.shipment.destination_location.code,
            pieces=pieces_dict
        )
        
        self.required_service_level = service_level
        self.routing_reason = reason
        self.routing_violations = violations
        
        if reason:
            logger.info(
                f"Routing determination: {self.shipment.origin_location.code}->{self.shipment.destination_location.code} "
                f"requires {service_level}. Reason: {reason}"
            )

    def _get_buy_rate(self, component: ServiceComponent) -> Optional[PartnerRate]:
        """
        Finds the buy-side (cost) rate for a given service component.
        
        Filters by:
        - mode (AIR)
        - origin/destination airports
        - direction (IMPORT/EXPORT) - from shipment_type
        - payment_term (exact match OR 'ANY')
        - rate_type (BUY_RATE only)
        - service_level (for intelligent routing)
        
        Orders by:
        1. Exact payment_term match before ANY
        2. Routing constraint priority
        3. Rate card valid_from (newest first)
        """
        from django.db.models import Q, Case, When, Value, IntegerField
        
        # Use the location code directly (it's already the airport IATA code)
        origin_code = self.shipment.origin_location.code if self.shipment.origin_location else None
        destination_code = self.shipment.destination_location.code if self.shipment.destination_location else None
        
        if not origin_code or not destination_code:
            logger.warning(f"Cannot resolve buy rate for {component.code}: missing origin or destination")
            return None
        
        # Get direction from shipment_type (IMPORT/EXPORT)
        direction = self.shipment.shipment_type  # 'IMPORT' or 'EXPORT'
        payment_term = self.shipment.payment_term  # 'PREPAID' or 'COLLECT'
        
        # Build base query filters
        filters = {
            'lane__mode': self.shipment.mode,
            'lane__origin_airport__iata_code': origin_code,
            'lane__destination_airport__iata_code': destination_code,
            'lane__direction': direction,  # NEW: Filter by direction
            'service_component': component,
            'lane__rate_card__rate_type': 'BUY_RATE',
        }
        
        # Payment term filter: match exact term OR 'ANY'
        payment_term_filter = Q(lane__payment_term=payment_term) | Q(lane__payment_term='ANY')
        
        # Service level filter for intelligent routing
        service_level_filter = Q()
        if self.required_service_level != 'STANDARD':
            service_level_filter = Q(lane__rate_card__service_level=self.required_service_level)
            logger.debug(
                f"Filtering rate card by service_level={self.required_service_level} for {component.code}"
            )
        
        # Build queryset with deterministic ordering:
        # 1. Exact payment_term match (priority 0) before ANY (priority 1)
        # 2. Routing constraint priority
        # 3. Rate card valid_from descending (newest first)
        rates = (
            PartnerRate.objects
            .filter(**filters)
            .filter(payment_term_filter)
            .filter(service_level_filter) if self.required_service_level != 'STANDARD' else
            PartnerRate.objects
            .filter(**filters)
            .filter(payment_term_filter)
        )
        
        # Add ordering annotation for payment term priority
        rates = rates.annotate(
            payment_term_priority=Case(
                When(lane__payment_term=payment_term, then=Value(0)),  # Exact match = highest priority
                default=Value(1),  # ANY = lower priority
                output_field=IntegerField(),
            )
        ).order_by(
            'payment_term_priority',  # Exact match first
            'lane__rate_card__route_lane_constraint__priority',  # Then routing priority
            '-lane__rate_card__valid_from',  # Newest rate card first
            'id',  # Tie-breaker for determinism
        )
        
        rate = rates.first()
        
        if rate:
            logger.debug(
                f"Found rate for {component.code}: {rate.lane.rate_card.name} "
                f"(direction={rate.lane.direction}, payment_term={rate.lane.payment_term})"
            )
            return rate
        
        # Try fallback to STANDARD service level if specific level not found
        if self.required_service_level != 'STANDARD':
            logger.warning(
                f"No PartnerRate found for {component.code} with service_level={self.required_service_level}. "
                f"Trying STANDARD fallback."
            )
            rates = (
                PartnerRate.objects
                .filter(**filters)
                .filter(payment_term_filter)
                .filter(lane__rate_card__service_level='STANDARD')
                .annotate(
                    payment_term_priority=Case(
                        When(lane__payment_term=payment_term, then=Value(0)),
                        default=Value(1),
                        output_field=IntegerField(),
                    )
                ).order_by(
                    'payment_term_priority',
                    'lane__rate_card__route_lane_constraint__priority',
                    '-lane__rate_card__valid_from',
                    'id',
                )
            )
            rate = rates.first()
            if rate:
                logger.debug(
                    f"Found STANDARD fallback rate for {component.code}: {rate.lane.rate_card.name}"
                )
                return rate
        
        # NO RATE FOUND - Log detailed failure info for debugging
        logger.error(
            f"NO RATE FOUND for {component.code} | "
            f"Route: {origin_code}->{destination_code} | "
            f"Direction: {direction} | "
            f"PaymentTerm: {payment_term} | "
            f"Mode: {self.shipment.mode} | "
            f"ServiceLevel: {self.required_service_level}"
        )
        
        return None


    # --- REFACTORED: This method now returns a simple Decimal ---
    def _calculate_sell_rate(self, component: ServiceComponent, cost_pgk: Decimal) -> Decimal:
        """
        Applies the policy margin to convert cost to sell rate.
        Phase 2: Uses service_code.pricing_method if available, falls back to cost_type.
        """
        base_cost = cost_pgk if cost_pgk and cost_pgk > 0 else component.base_pgk_cost
        if base_cost is None:
            base_cost = Decimal("0.00")

        # Priority 1: Check cost_type='RATE_OFFER' (Fixed Sell Rate)
        # For RATE_OFFER components, get the sell rate from the SELL_RATE card
        if component.cost_type == 'RATE_OFFER':
            # SPECIAL CASE: D2D Export Destination Charges require a 20% margin
            if component.code == 'DST_CHARGES':
                 margin = Decimal("0.20")
                 sell_pgk = base_cost * (Decimal("1.0") + margin)
                 return sell_pgk.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            
            # Look up the sell rate from the Sell Rate Card
            sell_rate = self._get_sell_rate_from_card(component)
            if sell_rate is not None:
                return sell_rate
            # Fallback to cost if no sell rate found
            return base_cost

        # Phase 2: Check service_code.pricing_method first
        if component.service_code:
            pricing_method = component.service_code.pricing_method
            
            # PASSTHROUGH: No margin applied (destination charges)
            if pricing_method == 'PASSTHROUGH':
                # SPECIAL CASE: D2D Export Destination Charges require a 20% margin
                if component.code == 'DST_CHARGES':
                     margin = Decimal("0.20")
                     sell_pgk = base_cost * (Decimal("1.0") + margin)
                     return sell_pgk.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                return base_cost
            
            # FX_CAF_MARGIN: Apply margin (origin charges)
            # STANDARD_RATE: Apply margin (freight charges)
            # RATE_OF_BASE: Will be handled by percentage component logic
            if pricing_method in ('FX_CAF_MARGIN', 'STANDARD_RATE'):
                margin = self.context['policy'].margin_pct
                sell_pgk = base_cost * (Decimal("1.0") + margin)
                return sell_pgk.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        
        # Fallback to legacy cost_type logic for backward compatibility
        if component.cost_type == 'RATE_OFFER':
            # Already handled above, should not reach here
            return base_cost

        margin = self.context['policy'].margin_pct
        sell_pgk = base_cost * (Decimal("1.0") + margin)
        return sell_pgk.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    
    def _get_sell_rate_from_card(self, component: ServiceComponent) -> Optional[Decimal]:
        """
        Looks up the sell rate for a RATE_OFFER component from the SELL_RATE card.
        Returns the calculated sell rate in PGK, or None if not found.
        
        Supports weight break tiering via tiering_json field.
        """
        origin_code = self.shipment.origin_location.code if self.shipment.origin_location else None
        destination_code = self.shipment.destination_location.code if self.shipment.destination_location else None
        
        if not origin_code or not destination_code:
            return None
        
        filters = {
            'lane__mode': self.shipment.mode,
            'lane__origin_airport__iata_code': origin_code,
            'lane__destination_airport__iata_code': destination_code,
            'service_component': component,
            'lane__rate_card__rate_type': 'SELL_RATE',  # Only get Sell rates
        }
        
        sell_rate = PartnerRate.objects.filter(**filters).first()
        
        if not sell_rate:
            return None
        
        chargeable_weight = Decimal(self.context['chargeable_weight_kg'])
        currency = sell_rate.lane.rate_card.currency_code or HOME_CURRENCY
        
        # Check for tiering_json weight break pricing
        if sell_rate.tiering_json:
            data = sell_rate.tiering_json
            if isinstance(data, dict) and data.get("type") == "weight_break":
                min_charge = Decimal(str(data.get("minimum_charge", "0.00")))
                breaks = data.get("breaks", [])
                
                if breaks:
                    selected_rate = None
                    # Sort breaks by min_kg descending to find the applicable tier
                    sorted_breaks = sorted(
                        breaks,
                        key=lambda x: Decimal(str(x.get("min_kg", "0"))),
                        reverse=True,
                    )
                    
                    for tier in sorted_breaks:
                        if chargeable_weight >= Decimal(str(tier.get("min_kg", "0"))):
                            selected_rate = Decimal(str(tier.get("rate_per_kg")))
                            break
                    
                    if selected_rate is None:
                        rate_fcy = min_charge
                    else:
                        calculated_cost = chargeable_weight * selected_rate
                        rate_fcy = max(calculated_cost, min_charge)
                    
                    # Convert to PGK if needed
                    if currency == 'PGK':
                        return rate_fcy.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                    
                    fx_rate = self._get_exchange_rate(currency, "PGK", apply_caf=False)
                    return (rate_fcy * fx_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        
        # Fallback to simple rate calculation if no tiering
        rate_fcy = Decimal("0.00")
        
        if sell_rate.rate_per_kg_fcy:
            rate_fcy += sell_rate.rate_per_kg_fcy * chargeable_weight
        
        if sell_rate.rate_per_shipment_fcy:
            rate_fcy += sell_rate.rate_per_shipment_fcy
        
        # Apply minimum charge if applicable
        if sell_rate.min_charge_fcy and rate_fcy < sell_rate.min_charge_fcy:
            rate_fcy = sell_rate.min_charge_fcy
        
        # Apply maximum charge if applicable
        if sell_rate.max_charge_fcy and rate_fcy > sell_rate.max_charge_fcy:
            rate_fcy = sell_rate.max_charge_fcy
        
        # Convert to PGK if needed
        if currency == 'PGK':
            return rate_fcy.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        
        fx_rate = self._get_exchange_rate(currency, "PGK", apply_caf=False)
        return (rate_fcy * fx_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


    def _create_charge_line(
        self,
        component: ServiceComponent,
        buy_rate: Optional[PartnerRate],
        cost_info: dict,
        sell_rate_pgk: Decimal
    ) -> CalculatedChargeLine:
        """
        Creates the final, auditable charge line with TAX POLICY applied.
        """
        cost_pgk = cost_info['cost_pgk']
        cost_fcy = cost_info['cost_fcy']
        cost_fcy_currency = cost_info['cost_fcy_currency']
        exchange_rate = cost_info['exchange_rate']
        cost_source = cost_info['cost_source']
        cost_source_desc = cost_info['cost_source_description']
        is_rate_missing = cost_info['is_rate_missing']

        # --- START TAX INTEGRATION ---
        
        # Create a VersionAdapter mockup that satisfies apply_gst_policy expectations
        # It expects: origin.country_code, destination.country_code, quotation.service_type, policy_snapshot
        class MockVersion:
            def __init__(self, service):
                self.origin = service.shipment.origin_location # Pydantic LocationRef
                self.destination = service.shipment.destination_location # Pydantic LocationRef
                self.quotation = type('Quotation', (), {
                    'service_type': service.shipment.shipment_type
                })()
                # Use policy dict
                self.policy_snapshot = {"export_evidence": False} 

        version_adapter = MockVersion(self)
        
        # Create ChargeAdapter mockup
        # It expects: code, stage (or derived logic)
        class MockCharge:
            def __init__(self, comp):
                self.code = comp.code
                self.stage = comp.leg
                if comp.service_code:
                     self.stage = comp.service_code.location_type
                if comp.mode == 'AIR' and comp.category == 'TRANSPORT':
                     self.stage = 'AIR'
                # Mutated by policy
                self.is_taxable = False
                self.gst_percentage = 0

        charge_adapter = MockCharge(component)

        # Apply GST Policy
        apply_gst_policy(version_adapter, charge_adapter)

        # Calculate Tax
        tax_pct = Decimal(str(charge_adapter.gst_percentage)) / Decimal("100.0")
        tax_multiplier = Decimal("1.0") + tax_pct

        # Apply Tax to Sell Rate
        sell_pgk_incl_gst = (sell_rate_pgk * tax_multiplier).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        # --- END TAX INTEGRATION ---

        sell_fcy_currency = self.output_currency_code
        sell_fcy = self._convert_pgk_to_currency(sell_rate_pgk, sell_fcy_currency)
        sell_fcy_incl_gst = self._convert_pgk_to_currency(sell_pgk_incl_gst, sell_fcy_currency)
        
        # Phase 2: Use service_code.location_type if available for UI grouping
        leg = component.leg
        if component.service_code:
            leg = component.service_code.location_type

        return CalculatedChargeLine(
            service_component_id=component.id,
            service_component_code=component.code,
            service_component_desc=component.description,
            leg=leg,  # Pass the resolved leg for UI grouping
            cost_pgk=cost_pgk,
            cost_fcy=cost_fcy,
            cost_fcy_currency=cost_fcy_currency,
            sell_pgk=sell_rate_pgk,
            sell_pgk_incl_gst=sell_pgk_incl_gst,
            sell_fcy=sell_fcy,
            sell_fcy_incl_gst=sell_fcy_incl_gst,
            sell_fcy_currency=sell_fcy_currency,
            exchange_rate=exchange_rate,
            cost_source=cost_source,
            cost_source_description=cost_source_desc,
            is_rate_missing=is_rate_missing
        )

    def _calculate_weight_break_cost(self, component: ServiceComponent) -> Optional[dict]:
        """
        Calculates cost for components with tiered, weight-based rating.
        This logic is driven by a 'tiering_json' field on the ServiceComponent.
        """
        data = component.tiering_json
        if not isinstance(data, dict) or data.get("type") != "weight_break":
            return None

        chargeable_weight = self.context["chargeable_weight_kg"]
        currency = data.get("currency", HOME_CURRENCY)
        min_charge = Decimal(str(data.get("minimum_charge", "0.00")))
        breaks = data.get("breaks", [])

        if not breaks:
            return None

        # Find the correct rate for the chargeable weight
        # Tiers should be sorted from highest min_kg to lowest
        selected_rate = None
        sorted_breaks = sorted(
            breaks,
            key=lambda x: Decimal(str(x.get("min_kg", "0"))),
            reverse=True,
        )
        
        for tier in sorted_breaks:
            if chargeable_weight >= Decimal(str(tier.get("min_kg", "0"))):
                selected_rate = Decimal(str(tier.get("rate_per_kg")))
                break
        
        # If weight is below the lowest break, there's no per-kg rate.
        # The charge is simply the minimum.
        if selected_rate is None:
            cost_fcy = min_charge
        else:
            # Calculate the cost and then apply the minimum
            calculated_cost = chargeable_weight * selected_rate
            cost_fcy = max(calculated_cost, min_charge)

        # Convert to home currency
        fx_rate = self._get_exchange_rate(currency, "PGK", apply_caf=True)
        cost_pgk = (cost_fcy * fx_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        return {
            "cost_pgk": cost_pgk,
            "cost_fcy": cost_fcy.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            "cost_fcy_currency": currency,
            "exchange_rate": fx_rate.quantize(Decimal("0.0001")),
            "cost_source": "TIERED_RATECARD",
            "cost_source_description": f"Tiered rate for {chargeable_weight}kg",
            "is_rate_missing": False,
        }

    def _calculate_buy_cost(self, component: ServiceComponent, buy_rate: Optional[PartnerRate]) -> dict:
        """
        Normalises buy-side costs into PGK while keeping FCY audit info.
        This is the primary cost calculation router.
        """
        # 0. Check for Spot Rate
        spot_rates = getattr(self.quote_input, 'spot_rates', {})
        if component.code in spot_rates:
            return self._calculate_spot_cost(component, spot_rates[component.code])

        # --- TIERED & COMPLEX PRICING FIRST ---
        # 1. Check for weight-break pricing
        # A. Check on the component itself (legacy/service-code driven)
        weight_break_cost = self._calculate_weight_break_cost(component)
        if weight_break_cost:
            return weight_break_cost
            
        # B. Check on the buy_rate (PartnerRate specific tiering)
        if buy_rate and buy_rate.tiering_json:
            data = buy_rate.tiering_json
            if isinstance(data, dict) and data.get("type") == "weight_break":
                chargeable_weight = self.context["chargeable_weight_kg"]
                currency = data.get("currency", buy_rate.lane.rate_card.currency_code or "PGK")
                min_charge = Decimal(str(data.get("minimum_charge", "0.00")))
                breaks = data.get("breaks", [])
                
                if breaks:
                    selected_rate = None
                    sorted_breaks = sorted(
                        breaks,
                        key=lambda x: Decimal(str(x.get("min_kg", "0"))),
                        reverse=True,
                    )
                    
                    for tier in sorted_breaks:
                        if chargeable_weight >= Decimal(str(tier.get("min_kg", "0"))):
                            selected_rate = Decimal(str(tier.get("rate_per_kg")))
                            break
                    
                    if selected_rate is None:
                        cost_fcy = min_charge
                    else:
                        calculated_cost = chargeable_weight * selected_rate
                        cost_fcy = max(calculated_cost, min_charge)
                        
                    fx_rate = self._get_exchange_rate(currency, "PGK", apply_caf=True)
                    cost_pgk = (cost_fcy * fx_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                    
                    return {
                        "cost_pgk": cost_pgk,
                        "cost_fcy": cost_fcy.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
                        "cost_fcy_currency": currency,
                        "exchange_rate": fx_rate.quantize(Decimal("0.0001")),
                        "cost_source": "PARTNER_TIERED",
                        "cost_source_description": f"{buy_rate.lane.rate_card.name} (Tiered)",
                        "is_rate_missing": False,
                    }

        # 2. Check for percentage-based pricing
        if self._is_percentage_based_component(component):
            return self._percentage_based_cost(component)
            
        # NOTE: RATE_OFFER components now calculate buy cost from Buy Rate Card
        # The sell rate is calculated separately in _calculate_sell_rate
        # This allows showing actual cost while keeping sell rate fixed
        
        # --- SIMPLE PRICING LAST ---
        zero = Decimal("0.00")
        chargeable_weight = Decimal(self.context['chargeable_weight_kg'])

        if buy_rate:
            currency = buy_rate.lane.rate_card.currency_code or "PGK"
            # Note: This logic now correctly handles 'PER_KG' vs 'KG' from older data
            unit = (buy_rate.unit or "").upper()
            
            cost_fcy = Decimal("0.00")
            
            # Support composite rates (e.g. Per KG + Flat Fee)
            # If both are present, we sum them.
            if buy_rate.rate_per_kg_fcy:
                cost_fcy += buy_rate.rate_per_kg_fcy * chargeable_weight
            
            if buy_rate.rate_per_shipment_fcy:
                cost_fcy += buy_rate.rate_per_shipment_fcy

            # Apply minimum charge if applicable
            if buy_rate.min_charge_fcy and cost_fcy < buy_rate.min_charge_fcy:
                cost_fcy = buy_rate.min_charge_fcy

            # Apply maximum charge if applicable
            if buy_rate.max_charge_fcy and cost_fcy > buy_rate.max_charge_fcy:
                cost_fcy = buy_rate.max_charge_fcy

            fx_rate = self._get_exchange_rate(currency, "PGK", apply_caf=True)
            cost_pgk = (cost_fcy * fx_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            return {
                "cost_pgk": cost_pgk,
                "cost_fcy": cost_fcy.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
                "cost_fcy_currency": currency,
                "exchange_rate": fx_rate.quantize(Decimal("0.0001")),
                "cost_source": "PARTNER_RATECARD",
                "cost_source_description": buy_rate.lane.rate_card.name,
                "is_rate_missing": cost_fcy == zero,
            }

        base_cost = component.base_pgk_cost or zero
        cost_pgk = base_cost.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return {
            "cost_pgk": cost_pgk,
            "cost_fcy": None,
            "cost_fcy_currency": None,
            "exchange_rate": Decimal("1.0"),
            "cost_source": component.cost_source or "BASE_COST",
            "cost_source_description": "Component base cost",
            "is_rate_missing": cost_pgk == zero,
        }

    def _calculate_spot_cost(self, component: ServiceComponent, spot_data: dict) -> dict:
        """
        Calculates cost based on manual spot rate input.
        """
        amount = Decimal(str(spot_data.get('amount', '0.00')))
        currency = spot_data.get('currency', 'PGK')
        
        # Convert FCY to PGK using Buy Rate + CAF buffer
        # CAF rates: Import=5%, Export=10% (confirmed)
        # Export D2D destination charges use Export CAF (10%)
        rate = self._get_exchange_rate(currency, "PGK", apply_caf=True)
        cost_pgk = (amount * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        
        return {
            "cost_pgk": cost_pgk,
            "cost_fcy": amount,
            "cost_fcy_currency": currency,
            "exchange_rate": rate,
            "cost_source": "SPOT_RATE",
            "cost_source_description": "Manual Spot Rate",
            "is_rate_missing": False,
        }

    def _calculate_override_cost(self, component: ServiceComponent, override: ManualOverride) -> dict:
        """
        Converts a manual override into the standard cost structure.
        """
        zero = Decimal("0.00")
        chargeable_weight = Decimal(self.context["chargeable_weight_kg"])
        unit = (override.unit or "").upper()

        cost_fcy = override.cost_fcy
        if unit in {"PER_KG", "KG"}:
            cost_fcy = cost_fcy * chargeable_weight
        elif unit in {"PER_SHIPMENT", "SHIPMENT"}:
            pass  # already shipment-level
        # other units default to shipment behavior

        if override.min_charge_fcy and cost_fcy < override.min_charge_fcy:
            cost_fcy = override.min_charge_fcy

        currency = override.currency or self.output_currency_code or HOME_CURRENCY
        fx_rate = self._get_exchange_rate(currency, "PGK", apply_caf=True)
        cost_pgk = (cost_fcy * fx_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        return {
            "cost_pgk": cost_pgk,
            "cost_fcy": cost_fcy.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            "cost_fcy_currency": currency,
            "exchange_rate": fx_rate.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP),
            "cost_source": "MANUAL_OVERRIDE",
            "cost_source_description": "Manual override",
            "is_rate_missing": cost_fcy == zero,
        }

    def _convert_pgk_to_currency(self, amount_pgk: Decimal, currency: Optional[str]) -> Decimal:
        if not currency or currency == "PGK":
            return amount_pgk
        rate = self._get_exchange_rate("PGK", currency, apply_caf=True)
        converted = amount_pgk * rate
        return converted.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def _get_exchange_rate(self, from_currency: str, to_currency: str, apply_caf: bool = False, force_import_caf: bool = False) -> Decimal:
        """
        Get exchange rate for currency conversion.
        """
        if from_currency == to_currency:
            return Decimal("1.0")

        rates = self._get_rates_dict()
        
        if from_currency != "PGK" and to_currency == "PGK":
            info = rates.get(from_currency)
            # FCY -> PGK (Cost): We BUY FCY to pay supplier costs.
            # Use TT BUY rate (PGK per FCY).
            if info and info.get("tt_buy"):
                rate = Decimal(str(info["tt_buy"]))
                if apply_caf:
                    # CAF increases the effective rate (more PGK per FCY = higher cost)
                    # Formula: rate * (1 + CAF)
                    caf_pct = self._get_caf_percent(force_import=force_import_caf)
                    rate *= (Decimal("1.0") + caf_pct)
                return rate  # FCY * rate = PGK

        if from_currency == "PGK" and to_currency != "PGK":
            info = rates.get(to_currency)
            # PGK -> FCY (Sell-side): Customer pays in FCY, we receive revenue.
            # tt_sell is stored as PGK per FCY (e.g. 2.85 PGK per AUD)
            # We need FCY per PGK, so we invert: 1/2.85 = 0.35 AUD per PGK
            if info and info.get("tt_sell"):
                tt_sell_pgk_per_fcy = Decimal(str(info["tt_sell"]))
                # Invert to get FCY per PGK
                rate = Decimal("1.0") / tt_sell_pgk_per_fcy  # e.g. 1/2.85 = 0.35
                if apply_caf:
                    # CAF decreases the effective rate (less FCY per PGK = customer pays more FCY)
                    # Formula: rate / (1 + CAF)
                    # Example: 0.35 / 1.10 = 0.318
                    caf_pct = self._get_caf_percent(force_import=force_import_caf)
                    rate /= (Decimal("1.0") + caf_pct)
                return rate  # PGK * rate = FCY

        return Decimal("1.0")

    def _get_caf_percent(self, force_import: bool = False) -> Decimal:
        shipment_type = (self.shipment.shipment_type or "").upper()
        if force_import:
            shipment_type = "IMPORT"
            
        policy = self.context['policy']
        if shipment_type == "IMPORT":
            return policy.caf_import_pct or Decimal("0.0")
        if shipment_type == "EXPORT":
            return policy.caf_export_pct or Decimal("0.0")
        return Decimal("0.0")

    def _get_rates_dict(self) -> dict:
        rates = self.context['fx_snapshot'].rates
        if isinstance(rates, str):
            return json.loads(rates)
        return rates or {}

    def _is_percentage_based_component(self, component: ServiceComponent) -> bool:
        return component.percent_of_component is not None

    def _percentage_based_cost(self, component: ServiceComponent) -> Optional[dict]:
        """
        Calculates cost for RATE_OF_BASE components (percentage surcharges).
        
        The percentage is sourced from agent rate cards (PartnerRate), NOT from
        the static component.percent_value. This allows different agents (EFM PNG,
        EFM AU, etc.) to have different fuel surcharge percentages.
        
        Requirements:
        1. Base component must be calculated first (execution order)
        2. Percentage must come from agent rate card for this component
        3. If base or percentage is missing → is_rate_missing=True with clear error
        """
        if not component.percent_of_component:
            return None
            
        ref_code = component.percent_of_component.code
        
        if not ref_code:
            logger.error(f"RATE_OF_BASE component {component.code} has no base component code")
            return None

        # Step 1: Check if base component cost has been calculated
        ref_cost_info = self.calculated_component_costs.get(ref_code)
        if not ref_cost_info:
            # Base component not yet calculated - need to wait for execution order
            error_msg = f"{component.description} missing base component cost ({ref_code})"
            logger.warning(f"RATE_OF_BASE: {error_msg}")
            return {
                "cost_pgk": Decimal("0.00"),
                "cost_fcy": None,
                "cost_fcy_currency": None,
                "exchange_rate": Decimal("1.0"),
                "cost_source": f"PERCENT_OF:{ref_code}",
                "cost_source_description": error_msg,
                "is_rate_missing": True,
            }
        
        # Step 2: Get percentage from AGENT RATE CARD first (not static component.percent_value)
        percent_value = self._get_percentage_from_agent_rate(component)
        
        if percent_value is None:
            # Fall back to static percent_value if no agent rate exists (backward compat)
            percent_value = component.percent_value
            
        if percent_value is None:
            # No percentage found - fail loudly
            error_msg = f"{component.description} missing agent rate percentage"
            logger.error(f"RATE_OF_BASE: {error_msg}")
            return {
                "cost_pgk": Decimal("0.00"),
                "cost_fcy": None,
                "cost_fcy_currency": None,
                "exchange_rate": Decimal("1.0"),
                "cost_source": f"PERCENT_OF:{ref_code}",
                "cost_source_description": error_msg,
                "is_rate_missing": True,
            }

        # Step 3: Calculate the percentage-based cost
        percent = percent_value / Decimal("100.0")
        cost_pgk = (ref_cost_info['cost_pgk'] * percent).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        
        # Calculate FCY if available in reference
        cost_fcy = None
        cost_fcy_currency = None
        exchange_rate = Decimal("1.0")
        
        if ref_cost_info.get('cost_fcy') is not None and ref_cost_info.get('cost_fcy_currency'):
             cost_fcy = (ref_cost_info['cost_fcy'] * percent).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
             cost_fcy_currency = ref_cost_info['cost_fcy_currency']
             exchange_rate = ref_cost_info.get('exchange_rate', Decimal("1.0"))

        return {
            "cost_pgk": cost_pgk,
            "cost_fcy": cost_fcy,
            "cost_fcy_currency": cost_fcy_currency,
            "exchange_rate": exchange_rate,
            "cost_source": f"PERCENT_OF:{ref_code}",
            "cost_source_description": f"{percent_value}% of {ref_code}",
            "is_rate_missing": False,
        }

    def _get_percentage_from_agent_rate(self, component: ServiceComponent) -> Optional[Decimal]:
        """
        Looks up the fuel surcharge percentage from the agent's rate card.
        
        The percentage is stored in PartnerRate.rate_per_shipment_fcy or
        a dedicated percentage field for RATE_OF_BASE components.
        
        Returns:
            Decimal percentage value (e.g., 10.00 for 10%) or None if not found
        """
        origin_code = self.shipment.origin_location.code if self.shipment.origin_location else None
        destination_code = self.shipment.destination_location.code if self.shipment.destination_location else None
        direction = self.shipment.shipment_type  # IMPORT/EXPORT
        payment_term = self.shipment.payment_term  # PREPAID/COLLECT
        
        if not origin_code or not destination_code:
            return None
        
        from django.db.models import Q
        
        # Query for the percentage rate from agent rate card
        filters = {
            'lane__mode': self.shipment.mode,
            'lane__origin_airport__iata_code': origin_code,
            'lane__destination_airport__iata_code': destination_code,
            'lane__direction': direction,
            'service_component': component,
            'lane__rate_card__rate_type': 'BUY_RATE',
        }
        
        # Payment term filter: match exact term OR 'ANY'
        payment_term_filter = Q(lane__payment_term=payment_term) | Q(lane__payment_term='ANY')
        
        rate = (
            PartnerRate.objects
            .filter(**filters)
            .filter(payment_term_filter)
            .first()
        )
        
        if not rate:
            logger.debug(
                f"No agent rate found for {component.code} (RATE_OF_BASE) | "
                f"Route: {origin_code}->{destination_code} | Direction: {direction}"
            )
            return None
        
        # For RATE_OF_BASE components, the percentage can be stored as:
        # 1. rate_per_shipment_fcy (interpreted as percentage when unit is 'PERCENT' or component is RATE_OF_BASE)
        # 2. A dedicated percentage field (future enhancement)
        
        # Check if this is a percentage-type rate
        if rate.rate_per_shipment_fcy is not None:
            logger.debug(
                f"Found agent rate for {component.code}: {rate.rate_per_shipment_fcy}% "
                f"from {rate.lane.rate_card.name}"
            )
            return rate.rate_per_shipment_fcy
        
        return None



    def _pass_through_sell_rate(self, component: ServiceComponent, buy_rate: Optional[PartnerRate]) -> dict:
        """
        For destination sell-rates that are already in PGK and should
        pass through without FX conversion or margin application.
        
        For Import Collect D2D to PNG, destination charges are local PGK sell rates
        and should NOT have FX applied (FX rate = 1.0).
        """
        zero = Decimal("0.00")
        
        if not buy_rate:
            return {
                'cost_pgk': zero,
                'cost_fcy': None,
                'cost_fcy_currency': None,
                'exchange_rate': Decimal('1.0'),
                'cost_source': 'MISSING_SELL_RATE',
                'cost_source_description': 'Missing Sell Rate',
                'is_rate_missing': True
            }
        
        # Get the sell-rate in its original currency
        unit = (buy_rate.unit or "").upper()
        rate_fcy = zero
        
        # Support composite rates (e.g., Per KG + Flat Fee for MXC)
        # If both rate_per_kg_fcy and rate_per_shipment_fcy are present, sum them.
        chargeable_weight = Decimal(self.context['chargeable_weight_kg'])
        
        if buy_rate.rate_per_kg_fcy:
            rate_fcy += buy_rate.rate_per_kg_fcy * chargeable_weight
        
        if buy_rate.rate_per_shipment_fcy:
            rate_fcy += buy_rate.rate_per_shipment_fcy
        
        # Apply minimum charge if applicable (to total)
        if buy_rate.min_charge_fcy and rate_fcy < buy_rate.min_charge_fcy:
            rate_fcy = buy_rate.min_charge_fcy
        
        # Apply maximum charge if applicable
        if buy_rate.max_charge_fcy and rate_fcy > buy_rate.max_charge_fcy:
            rate_fcy = buy_rate.max_charge_fcy
        
        # CRITICAL: For Import Collect D2D to PNG, destination charges are local PGK
        # sell rates. They should NOT have FX conversion applied.
        shipment = self.quote_input.shipment
        dest_country = shipment.destination_location.country_code if shipment.destination_location else None
        is_import = shipment.shipment_type == 'IMPORT'
        is_destination_leg = component.leg == 'DESTINATION' or component.code.startswith('DST')
        
        # If destination is PNG (home) and this is a destination charge, use PGK directly
        if is_import and dest_country == 'PG' and is_destination_leg:
            # These are PNG local sell rates - already in PGK, no FX needed
            cost_pgk = rate_fcy.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            return {
                'cost_pgk': cost_pgk,
                'cost_fcy': cost_pgk,  # Same as PGK (no conversion)
                'cost_fcy_currency': 'PGK',
                'exchange_rate': Decimal('1.0'),
                'cost_source': 'DIRECT_SELL_RATE',
                'cost_source_description': 'PNG Local Sell Rate (PGK)',
                'is_rate_missing': False
            }
        
        # For other cases (Export destination charges or foreign destinations), apply FX
        currency = buy_rate.lane.rate_card.currency_code or HOME_CURRENCY
        fx_rate = self._get_exchange_rate(currency, "PGK", apply_caf=False)
        
        cost_pgk = (rate_fcy * fx_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        return {
            'cost_pgk': cost_pgk,
            'cost_fcy': rate_fcy,
            'cost_fcy_currency': currency,
            'exchange_rate': fx_rate,
            'cost_source': 'DIRECT_SELL_RATE',
            'cost_source_description': f'Direct Sell Rate ({currency})',
            'is_rate_missing': False
        }

    def _calculate_totals(self) -> CalculatedTotals:
        """
        Sums all sell lines into a final totals object.
        """
        total_cost_pgk = sum(line.cost_pgk for line in self.sell_lines if line.cost_pgk)
        total_sell_pgk = sum(line.sell_pgk for line in self.sell_lines)
        total_sell_pgk_incl_gst = sum(line.sell_pgk_incl_gst for line in self.sell_lines)
        
        total_sell_fcy = sum(line.sell_fcy for line in self.sell_lines)
        total_sell_fcy_incl_gst = sum(line.sell_fcy_incl_gst for line in self.sell_lines)
        
        has_missing_rates = any(line.is_rate_missing for line in self.sell_lines)
        
        notes = "Rates are missing." if has_missing_rates else None

        return CalculatedTotals(
            total_cost_pgk=total_cost_pgk, 
            total_sell_pgk=total_sell_pgk,
            total_sell_pgk_incl_gst=total_sell_pgk_incl_gst,
            total_sell_fcy=total_sell_fcy,
            total_sell_fcy_incl_gst=total_sell_fcy_incl_gst,
            total_sell_fcy_currency=self.output_currency_code,
            has_missing_rates=has_missing_rates,
            notes=notes
        )
