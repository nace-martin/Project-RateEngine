# backend/pricing_v2/pricing_service_v3.py

"""
V3 Pricing Service.

This service is responsible for orchestrating the entire quote calculation
process.
"""

import json
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
    CalculatedTotals
)
# --- END UPDATED IMPORTS ---

from core.models import FxSnapshot, Policy, Surcharge, LocalTariff
from ratecards.models import PartnerRateLane, PartnerRate
from services.models import ServiceComponent, IncotermRule

# A constant for our home currency
HOME_CURRENCY = "PGK"
DEFAULT_POLICY_NAME = "Default Policy"

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

    def calculate_charges(self) -> QuoteCharges:
        """
        Main entry point for the calculation.
        """
        # 1. Get all applicable service components
        service_components = self._get_service_components()
        service_components = sorted(
            service_components,
            key=lambda comp: 1 if self._is_percentage_based_component(comp) else 0
        )

        # 2. Calculate each line
        for component in service_components:
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
        # TODO: Implement chargeable weight calculation
        chargeable_weight_kg = self.shipment.pieces[0].gross_weight_kg
        
        # Get the latest active policy and FX snapshot
        # In a real app, this would be more robust
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
        Gets the list of services to be quoted based on a cascading rules engine.
        """
        rules_to_try = [
            # Most specific rule
            {'incoterm': self.shipment.incoterm, 'service_level': self.shipment.service_level, 'payment_term': self.shipment.payment_term},
            # Fallback to service level
            {'incoterm': self.shipment.incoterm, 'service_level': self.shipment.service_level},
            # Fallback to any service level
            {'incoterm': self.shipment.incoterm},
        ]

        for rule_kwargs in rules_to_try:
            try:
                rule = IncotermRule.objects.get(
                    mode=self.shipment.mode,
                    shipment_type=self.shipment.shipment_type,
                    **rule_kwargs
                )
                return list(rule.service_components.filter(is_active=True))
            except IncotermRule.DoesNotExist:
                continue
            except IncotermRule.MultipleObjectsReturned:
                # If multiple rules match, we need to decide which one to use.
                # For now, we'll just use the first one.
                rule = IncotermRule.objects.filter(
                    mode=self.shipment.mode,
                    shipment_type=self.shipment.shipment_type,
                    **rule_kwargs
                ).first()
                return list(rule.service_components.filter(is_active=True))

        # If no rule is found, return an empty list of services
        return []

    # --- REFACTORED: This method now returns a PartnerRate object ---
    def _get_buy_rate(self, component: ServiceComponent) -> Optional[PartnerRate]:
        """
        Finds the buy-side (cost) rate for a given service component.
        """
        # This is the core of the V3 "Buy Source Adapter" logic
        
        # 1. Check for a manual override first
        for override in self.quote_input.overrides:
            if override.service_component_id == component.id:
                # TODO: Handle overrides
                print(f"Handle override for {component.code}")
                return None # Placeholder

        # 2. Find a matching PartnerRate
        # We find the lane based on the new (corrected) FKs
        try:
            rate = PartnerRate.objects.get(
                lane__mode=self.shipment.mode,
                lane__shipment_type=self.shipment.shipment_type,
                # TODO: Add supplier/audience logic
                lane__origin_airport__iata_code=self.shipment.origin_code,
                lane__destination_airport__iata_code=self.shipment.destination_code,
                service_component=component
            )
            return rate
        except PartnerRate.DoesNotExist:
            print(f"No PartnerRate found for {component.code}")
            return None
        except Exception as e:
            print(f"Error finding PartnerRate: {e}")
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

    # --- REFACTORED: This method now builds the new CalculatedChargeLine ---
    def _create_charge_line(
        self,
        component: ServiceComponent,
        buy_rate: Optional[PartnerRate],
        cost_info: dict,
        sell_rate_pgk: Decimal
    ) -> CalculatedChargeLine:
        """
        Creates the final, auditable charge line.
        """
        cost_pgk = cost_info['cost_pgk']
        cost_fcy = cost_info['cost_fcy']
        cost_fcy_currency = cost_info['cost_fcy_currency']
        exchange_rate = cost_info['exchange_rate']
        cost_source = cost_info['cost_source']
        cost_source_desc = cost_info['cost_source_description']
        is_rate_missing = cost_info['is_rate_missing']

        tax_rate = component.tax_rate or Decimal("0.0")
        if (self.shipment.shipment_type or "").upper() == "IMPORT" and component.leg != "DESTINATION":
            tax_rate = Decimal("0.0")
        tax_multiplier = Decimal("1.0") + tax_rate
        sell_pgk_incl_gst = (sell_rate_pgk * tax_multiplier).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        sell_fcy_currency = self.quote_input.output_currency
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

    def _convert_pgk_to_currency(self, amount_pgk: Decimal, currency: str) -> Decimal:
        if currency == "PGK":
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
            total_sell_fcy_currency=self.quote_input.output_currency,
            has_missing_rates=has_missing_rates,
            notes=notes
        )
