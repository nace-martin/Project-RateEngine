# backend/pricing_v2/pricing_service_v3.py

"""
V3 Pricing Service.

This service is responsible for orchestrating the entire quote calculation
process.
"""

import json
import logging
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Optional
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

# --- TAX ADAPTERS ---
class TaxVersionAdapter:
    """
    Translates the V3 Shipment/Context into the 'version' object
    expected by quotes.tax_policy.apply_gst_policy.
    """
    def __init__(self, service):
        self.origin = service.shipment.origin_location
        self.destination = service.shipment.destination_location

        # Create a fake quotation object with just the service_type attribute
        self.quotation = type('Quotation', (), {
            'service_type': service.shipment.shipment_type
        })()

        # TODO: If you add an 'export_evidence' checkbox to the UI, map it here.
        self.policy_snapshot = {"export_evidence": False}


class TaxChargeAdapter:
    """
    Translates a V3 ServiceComponent into the 'charge' object
    expected by quotes.tax_policy.apply_gst_policy.
    """
    def __init__(self, component):
        self.code = component.code
        self.stage = component.leg
        
        # Phase 2: Use service_code.location_type if available
        if component.service_code:
            self.stage = component.service_code.location_type

        # CRITICAL: Map Freight to 'AIR' stage to ensure International Linehaul is 0%
        if component.mode == 'AIR' and component.category == 'TRANSPORT':
            self.stage = 'AIR'

        # Fields the policy will mutate
        self.is_taxable = False
        self.gst_percentage = 0
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
        """
        service_rule_components = self._get_service_rule_components()
        if service_rule_components:
            return service_rule_components

        logger.warning(
            "No ServiceRule resolved for %s %s %s %s",
            self.shipment.mode,
            self.shipment.shipment_type,
            self.shipment.incoterm,
            getattr(self.shipment, "service_scope", None),
        )
        return []

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
        try:
            rule = (
                ServiceRule.objects.filter(
                    mode=self.shipment.mode,
                    direction=self.shipment.shipment_type,
                    incoterm=incoterm,
                    payment_term=self.shipment.payment_term,
                    service_scope=service_scope,
                    is_active=True,
                )
                .order_by("-effective_from")
                .first()
            )
        except Exception:
            rule = None

        self.service_rule = rule
        self.context["service_rule"] = rule

    def _apply_output_currency_policy(self) -> None:
        """
        Applies ServiceRule-driven currency logic when available.
        """
        derived_currency = None
        if self.service_rule:
            derived_currency = self._derive_currency_from_rule(self.service_rule)

        if derived_currency:
            self.output_currency_code = derived_currency

    def _derive_currency_from_rule(self, rule: ServiceRule) -> Optional[str]:
        ccy_type = rule.output_currency_type or "DESTINATION"
        if ccy_type == "PGK":
            return HOME_CURRENCY
        if ccy_type == "USD":
            return "USD"
        if ccy_type == "ORIGIN":
            code = self._get_origin_currency_code()
            return code or HOME_CURRENCY
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
        Now filters by service_level for intelligent routing.
        """
        # Use the location code directly (it's already the airport IATA code)
        origin_code = self.shipment.origin_location.code if self.shipment.origin_location else None
        destination_code = self.shipment.destination_location.code if self.shipment.destination_location else None
        
        if not origin_code or not destination_code:
            return None
        # Build query filters
        # NOTE: Removed lane__shipment_type filter. The model uses SHIPMENT_TYPE_CHOICES 
        # like 'GENERAL', but quote.shipment_type is 'EXPORT'/'IMPORT'. These are different
        # concepts (cargo type vs direction). Lane is uniquely identified by origin/dest.
        filters = {
            'lane__mode': self.shipment.mode,
            'lane__origin_airport__iata_code': origin_code,
            'lane__destination_airport__iata_code': destination_code,
            'service_component': component
        }
        
        # ADD THIS: service_level filter for intelligent routing
        # Only filter if we have a specific routing requirement (not STANDARD)
        if self.required_service_level != 'STANDARD':
            filters['lane__rate_card__service_level'] = self.required_service_level
            logger.debug(
                f"Filtering rate card by service_level={self.required_service_level} for {component.code}"
            )
        # Find a matching PartnerRate based on the shipment context
        # We use filter() + order_by() to handle cases where multiple rates might match
        # (e.g. Direct vs Via BNE) and prioritize them based on the routing constraint priority.
        rates = PartnerRate.objects.filter(**filters).order_by(
            'lane__rate_card__route_lane_constraint__priority',
            'id'
        )
        
        rate = rates.first()
        
        if rate:
            return rate
            
        # ADD THIS: If no rate found with specific service level, try fallback to STANDARD
        if self.required_service_level != 'STANDARD':
            logger.warning(
                f"No PartnerRate found for {component.code} with service_level={self.required_service_level}. "
                f"Trying STANDARD fallback."
            )
            filters['lane__rate_card__service_level'] = 'STANDARD'
            rates = PartnerRate.objects.filter(**filters).order_by(
                'lane__rate_card__route_lane_constraint__priority',
                'id'
            )
            rate = rates.first()
            if rate:
                return rate
                
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
            # SPECIAL CASE: D2D Export Destination Charges require a 20% margin
            if component.code == 'DST_CHARGES':
                 margin = Decimal("0.20")
                 sell_pgk = base_cost * (Decimal("1.0") + margin)
                 return sell_pgk.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            return base_cost

        margin = self.context['policy'].margin_pct
        sell_pgk = base_cost * (Decimal("1.0") + margin)
        return sell_pgk.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

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
        # 1. Build the adapters
        version_adapter = TaxVersionAdapter(self)
        charge_adapter = TaxChargeAdapter(component)

        # 2. Apply the policy (this updates charge_adapter in place)
        apply_gst_policy(version_adapter, charge_adapter)

        # 3. Calculate Tax
        tax_pct = Decimal(str(charge_adapter.gst_percentage)) / Decimal("100.0")
        tax_multiplier = Decimal("1.0") + tax_pct

        # 4. Apply Tax to Sell Rate
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
            # Create a temporary component-like object or modify the call to support passing data directly
            # For now, let's just reuse the logic by temporarily mocking the component's tiering_json
            # Or better, refactor _calculate_weight_break_cost to accept data input.
            
            # Let's refactor inline for now to be safe and explicit
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
            
        # 3. Check for Sell-Rate Pass-Through (Destination Charges)
        if component.cost_type == 'RATE_OFFER':
            return self._pass_through_sell_rate(component, buy_rate)
        
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
        
        # If currency is FCY, convert to PGK using Buy Rate + Buffer (Import Logic)
        # Why Import Logic? Because we are "buying" the spot service.
        # However, for Export D2D, the user said: "Dest Charges FCY -> PGK (Buy Rate + 5% Buffer)"
        # This matches our standard _get_exchange_rate(..., apply_caf=True) logic IF shipment_type=IMPORT.
        # BUT here shipment_type=EXPORT.
        # So we need to force "IMPORT" context for this specific conversion if it's a destination charge?
        # Or just rely on the fact that _get_exchange_rate uses caf_export_pct (10%) for Exports?
        
        # User Requirement: "Apply 5% buffer / CAF to the FX BUY rate" for D2D Dest Charges.
        # Export CAF is 10%. Import CAF is 5%.
        # So for D2D Dest Charges, we should use Import CAF (5%).
        
        # Let's check if this is a Destination Charge
        is_dest_charge = component.code == 'DST_CHARGES' or (component.service_code and component.service_code.location_type == 'DESTINATION')
        
        force_import_caf = False
        if is_dest_charge and self.shipment.shipment_type == 'EXPORT':
            force_import_caf = True
            
        rate = self._get_exchange_rate(currency, "PGK", apply_caf=True, force_import_caf=force_import_caf)
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
        
        FCY -> PGK (Buy-side/Cost conversion):
            - Use TT BUY rate (how many PGK to pay for 1 FCY)
            - Apply CAF by MULTIPLYING: TT_BUY * (1 + CAF)
            - Example: 2.80 PGK/AUD * 1.05 = 2.94 PGK/AUD
            - Then: FCY_amount * 2.94 = PGK_cost
        
        PGK -> FCY (Sell-side/Quote conversion):
            - Use TT SELL rate (how many FCY per 1 PGK)
            - Apply CAF by DIVIDING: TT_SELL / (1 + CAF)
            - Example: 0.35 AUD/PGK / 1.10 = 0.318 AUD/PGK
            - Then: PGK_amount * 0.318 = FCY_sell
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
        if not component.percent_of_component:
            return None
            
        ref_code = component.percent_of_component.code
        percent_value = component.percent_value
        
        if not ref_code or percent_value is None:
            return None

        ref_cost_info = self.calculated_component_costs.get(ref_code)
        if not ref_cost_info:
             # If base component is missing, we can't calculate surcharge
            return {
                "cost_pgk": Decimal("0.00"),
                "cost_fcy": None,
                "cost_fcy_currency": None,
                "exchange_rate": Decimal("1.0"),
                "cost_source": f"PERCENT_OF:{ref_code}",
                "cost_source_description": f"Waiting for {ref_code}",
                "is_rate_missing": True,
            }

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

    def _pass_through_sell_rate(self, component: ServiceComponent, buy_rate: Optional[PartnerRate]) -> dict:
        """
        For destination sell-rates that are already in PGK and should
        pass through without FX conversion or margin application.
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
        
        if unit == 'SHIPMENT':
            rate_fcy = buy_rate.rate_per_shipment_fcy or zero
        elif unit in ('KG', 'PER_KG'):
            chargeable_weight = Decimal(self.context['chargeable_weight_kg'])
            rate_fcy = (buy_rate.rate_per_kg_fcy or zero) * chargeable_weight
            if buy_rate.min_charge_fcy:
                rate_fcy = max(rate_fcy, buy_rate.min_charge_fcy)
        
        currency = buy_rate.lane.rate_card.currency_code or HOME_CURRENCY
        fx_rate = self._get_exchange_rate(currency, "PGK", apply_caf=False) # No CAF on sell rates usually? Or maybe yes?
        # User said "Apply our FX BUY rate... Convert... Apply margin".
        # But for "Sell Rates" provided by user, they are already the final price?
        # If it's RATE_OFFER, we assume it's the final price in that currency.
        # So we just convert to PGK for reporting.
        
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

    # --- REFACTORED: This method now builds the new CalculatedTotals ---
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
            # --- THIS IS THE FIX ---
            total_cost_pgk=total_cost_pgk, 
            # --- END FIX ---
            total_sell_pgk=total_sell_pgk,
            total_sell_pgk_incl_gst=total_sell_pgk_incl_gst,
            total_sell_fcy=total_sell_fcy,
            total_sell_fcy_incl_gst=total_sell_fcy_incl_gst,
            total_sell_fcy_currency=self.output_currency_code,
            has_missing_rates=has_missing_rates,
            notes=notes
        )
