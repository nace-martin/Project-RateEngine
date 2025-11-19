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

from core.models import FxSnapshot, Policy, Surcharge, LocalTariff, Location
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

    def calculate_charges(self) -> QuoteCharges:
        """
        Main entry point for the calculation.
        """
        self._resolve_service_rule()
        # 1. Get all applicable service components
        service_components = self._get_service_components()
        self._apply_output_currency_policy()
        service_components = sorted(
            service_components,
            key=lambda comp: 1 if self._is_percentage_based_component(comp) else 0
        )

        # 2. Calculate each line
        for component in service_components:
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

    def _resolve_iata_code(self, location_ref: Optional[LocationRef]) -> Optional[str]:
        """
        Resolves the correct IATA Airport Code for a given location.
        If the location is a City or Address, it looks up the linked Airport from the DB.
        """
        if not location_ref:
            return None

        # Fast Path: If it's already an airport, use the code directly.
        if location_ref.kind == "AIRPORT" and location_ref.code:
            return location_ref.code

        # Slow Path: It's a City/Address. We must find the 'gateway' airport.
        try:
            loc_obj = Location.objects.get(id=location_ref.id)
            if getattr(loc_obj, 'airport', None):
                return loc_obj.airport.iata_code
        except Exception as e:
            logger.warning(f"Could not resolve airport for location {location_ref.name}: {e}")

        # Fallback: Try using the location's own code (might be same as airport)
        return location_ref.code

    # --- REFACTORED: This method now returns a PartnerRate object ---
    def _get_buy_rate(self, component: ServiceComponent) -> Optional[PartnerRate]:
        """
        Finds the buy-side (cost) rate for a given service component.
        """
        # --- UPDATED LOGIC ---
        # Resolve the actual AIRPORT codes, even if the location is a City
        origin_code = self._resolve_iata_code(self.shipment.origin_location)
        destination_code = self._resolve_iata_code(self.shipment.destination_location)
        # ---------------------
        if not origin_code or not destination_code:
            return None

        # Find a matching PartnerRate based on the shipment context
        try:
            rate = PartnerRate.objects.get(
                lane__mode=self.shipment.mode,
                lane__shipment_type=self.shipment.shipment_type,
                # TODO: Add supplier/audience logic
                lane__origin_airport__iata_code=origin_code,
                lane__destination_airport__iata_code=destination_code,
                service_component=component
            )
            return rate
        except PartnerRate.DoesNotExist:
            # Debug log only
            # print(f"No PartnerRate found for {component.code} on {origin_code}->{destination_code}")
            return None
        except Exception as e:
            logger.error(f"Error finding PartnerRate: {e}")
            return None

    # --- REFACTORED: This method now returns a simple Decimal ---
    def _calculate_sell_rate(self, component: ServiceComponent, cost_pgk: Decimal) -> Decimal:
        """
        Applies the policy margin to convert cost to sell rate.
        """
        margin = self.context['policy'].margin_pct
        base_cost = cost_pgk if cost_pgk and cost_pgk > 0 else component.base_pgk_cost
        if base_cost is None:
            base_cost = Decimal("0.00")
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
        
        return CalculatedChargeLine(
            service_component_id=component.id,
            service_component_code=component.code,
            service_component_desc=component.description,
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

    def _calculate_buy_cost(self, component: ServiceComponent, buy_rate: Optional[PartnerRate]) -> dict:
        """
        Normalises buy-side costs into PGK while keeping FCY audit info.
        """
        zero = Decimal("0.00")
        chargeable_weight = Decimal(self.context['chargeable_weight_kg'])

        percent_cost = self._percentage_based_cost(component)
        if percent_cost:
            return percent_cost

        if buy_rate:
            currency = buy_rate.lane.rate_card.currency_code or "PGK"
            if buy_rate.unit == 'KG' and buy_rate.rate_per_kg_fcy:
                cost_fcy = buy_rate.rate_per_kg_fcy * chargeable_weight
            elif buy_rate.unit == 'SHIPMENT' and buy_rate.rate_per_shipment_fcy:
                cost_fcy = buy_rate.rate_per_shipment_fcy
            else:
                cost_fcy = zero

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
        rate = self._get_exchange_rate("PGK", currency)
        converted = amount_pgk * rate
        return converted.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def _get_exchange_rate(self, from_currency: str, to_currency: str, apply_caf: bool = False) -> Decimal:
        if from_currency == to_currency:
            return Decimal("1.0")

        rates = self._get_rates_dict()
        if from_currency != "PGK" and to_currency == "PGK":
            info = rates.get(from_currency)
            if info and info.get("tt_buy"):
                rate = Decimal(str(info["tt_buy"]))
                if apply_caf:
                    rate *= (Decimal("1.0") + self._get_caf_percent())
                return rate

        if from_currency == "PGK" and to_currency != "PGK":
            info = rates.get(to_currency)
            if info and info.get("tt_sell"):
                rate = Decimal(str(info["tt_sell"]))
                return Decimal("1.0") / rate

        return Decimal("1.0")

    def _get_caf_percent(self) -> Decimal:
        shipment_type = (self.shipment.shipment_type or "").upper()
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
        data = component.tiering_json
        return isinstance(data, dict) and data.get("percent_of") and data.get("percent") is not None

    def _percentage_based_cost(self, component: ServiceComponent) -> Optional[dict]:
        data = component.tiering_json
        if not isinstance(data, dict):
            return None
        ref_code = data.get("percent_of")
        percent_value = data.get("percent")
        if not ref_code or percent_value is None:
            return None

        ref_cost_info = self.calculated_component_costs.get(ref_code)
        if not ref_cost_info:
            return None

        percent = Decimal(str(percent_value))
        cost_pgk = (ref_cost_info['cost_pgk'] * percent).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return {
            "cost_pgk": cost_pgk,
            "cost_fcy": None,
            "cost_fcy_currency": None,
            "exchange_rate": Decimal("1.0"),
            "cost_source": f"PERCENT_OF:{ref_code}",
            "cost_source_description": f"{percent:.2%} of {ref_code}",
            "is_rate_missing": False,
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
