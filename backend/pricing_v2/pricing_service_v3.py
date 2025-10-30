# In: backend/pricing_v2/pricing_service_v3.py
# (Replace the entire file with this)

import json
import logging
from dataclasses import asdict
from decimal import Decimal, ROUND_UP, ROUND_HALF_UP
from typing import List, Dict, Optional, Tuple
from django.db import transaction

from django.utils import timezone # Add this

# Models
from core.models import FxSnapshot, Airport, Currency
from parties.models import CustomerCommercialProfile, Company, Contact # Add Contact
from quotes.models import Quote, QuoteVersion, QuoteLine, QuoteTotal # QuoteLine & QuoteTotal
from services.models import ServiceComponent, IncotermRule # Add IncotermRule
# Import new PartnerRate models
from ratecards.models import PartnerRate
# V2 rate card service
from ratecards.services import RateCardService

# Dataclasses
from .dataclasses_v3 import (
    V3QuoteRequest,
    CalculationContext,
    ServiceCostLine,
    ManualCostOverride,
    DimensionLine, # <-- ADD THIS IMPORT
)

# Utils
from .utils_v2 import calculate_chargeable_weight # Re-use V2 util

_logger = logging.getLogger(__name__)


class PricingServiceV3:
    """
    Main service for V3 quoting logic.
    Refactored to support multiple cost sources via the "Rate Resolver" pattern.
    """
    _CURRENCY_QUANTUM = Decimal("0.01")
    _ROUNDING_THRESHOLD = Decimal("0.002")
    
    def compute_v3(self, request: V3QuoteRequest) -> Quote: # <-- Changed return type
        """
        Main entry point for calculating a V3 quote.
        """
        _logger.info(f"Starting V3 quote computation for {request.customer_id}")

        # 1. Prepare context...
        context = self._prepare_calculation_context(request)

        # 2. Get required services...
        required_services = self._get_required_services(context)
        if not required_services:
            _logger.warning(f"No IncotermRule found for {context.incoterm_rule_key}")
            # TODO: Handle this error case gracefully
            raise Exception(f"No service rule found for {request.incoterm}.")

        # 3. Calculate all PGK costs...
        cost_lines_pgk = self._calculate_costs_pgk(context, required_services)

        # 4. Apply margin...
        sell_lines_pgk = self._apply_margin_pgk(context, cost_lines_pgk)

        # 5. Convert to output currency...
        final_lines = self._convert_to_output_currency(context, sell_lines_pgk)
        
        # 6. Save the quote to the database
        quote = self._save_quote_v3(context, final_lines) # <-- This is now implemented

        return quote # <-- Return the new quote object

    # ==========================================================================
    # STEP 1: PREPARE CONTEXT
    # ==========================================================================

    def _prepare_calculation_context(self, request: V3QuoteRequest) -> CalculationContext:
        """
        Loads all necessary data into a context object for the calculation.
        """
        origin_code = (request.origin_airport_code or "").upper()
        destination_code = (request.destination_airport_code or "").upper()

        try:
            customer = Company.objects.get(pk=request.customer_id)
            customer_profile = customer.commercial_profile
            fx_snapshot = FxSnapshot.objects.latest('as_of_timestamp')
            origin_airport = Airport.objects.get(pk=origin_code)
            destination_airport = Airport.objects.get(pk=destination_code)
        except Company.DoesNotExist:
            _logger.error(f"Customer {request.customer_id} not found.")
            raise Exception("Customer not found.") # TODO: Use specific exceptions
        except CustomerCommercialProfile.DoesNotExist:
            _logger.warning(f"Customer {request.customer_id} has no commercial profile. Using defaults.")
            customer_profile = CustomerCommercialProfile(customer=customer)
        except FxSnapshot.DoesNotExist:
            _logger.error("No FxSnapshot found in database.")
            raise Exception("FX data not available.")
        except Airport.DoesNotExist:
            _logger.error(f"Airport not found. Code: {origin_code} or {destination_code}")
            raise Exception("Invalid airport code.")

        # Determine output currency (store ISO currency code string)
        preferred_currency = getattr(customer_profile, "preferred_quote_currency", None)
        if isinstance(preferred_currency, Currency):
            preferred_currency_code = preferred_currency.code
        else:
            preferred_currency_code = preferred_currency or "PGK"

        output_currency = (request.output_currency or preferred_currency_code or "PGK").upper()

        # Calculate total gross weight and total volume from the dimension lines
        pieces_payload: List[Dict[str, Decimal]] = []
        for line in request.dimensions:
            for _ in range(line.pieces):
                pieces_payload.append(
                    {
                        "weight_kg": line.gross_weight_kg,
                        "length_cm": line.length_cm,
                        "width_cm": line.width_cm,
                        "height_cm": line.height_cm,
                    }
                )

        chargeable_weight_kg = calculate_chargeable_weight(pieces_payload)

        incoterm_rule_key = (
            request.mode,
            request.shipment_type,
            request.incoterm,
        )

        return CalculationContext(
            request=request,
            customer=customer,
            customer_profile=customer_profile,
            fx_snapshot=fx_snapshot,
            output_currency=output_currency,
            chargeable_weight_kg=chargeable_weight_kg,
            origin_airport=origin_airport,
            destination_airport=destination_airport,
            incoterm_rule_key=incoterm_rule_key,
            # Create a map of overrides for fast lookup
            overrides={ov.service_component_id: ov for ov in request.overrides}
        )

    def _service_label(self, service: ServiceComponent) -> str:
        """
        Returns a human-friendly identifier for logging.
        """
        return getattr(service, "description", None) or getattr(service, "code", str(service))

    def _quantize_currency(self, value: Decimal) -> Decimal:
        """
        Quantize currency values while avoiding rounding up when the adjustment
        would exceed the original amount by less than a cent.
        """
        quantized = value.quantize(self._CURRENCY_QUANTUM, rounding=ROUND_HALF_UP)
        if quantized > value and (quantized - value) < self._ROUNDING_THRESHOLD:
            quantized -= self._CURRENCY_QUANTUM
        return quantized

    # ==========================================================================
    # STEP 2: GET REQUIRED SERVICES
    # ==========================================================================

    def _get_required_services(self, context: CalculationContext) -> List[ServiceComponent]:
        """
        Finds the list of services required based on the IncotermRule.
        """
        # This logic is sound and remains from our skeleton
        try:
            rule = IncotermRule.objects.get(
                mode=context.incoterm_rule_key[0],
                shipment_type=context.incoterm_rule_key[1],
                incoterm=context.incoterm_rule_key[2],
            )
            # Order services correctly, especially for percentage-based ones
            return list(rule.service_components.all().order_by('pk'))
        except IncotermRule.DoesNotExist:
            return []

    # ==========================================================================
    # STEP 3: CALCULATE COSTS (THE "RATE RESOLVER")
    # ==========================================================================

    def _calculate_costs_pgk(
        self, context: CalculationContext, services: List[ServiceComponent]
    ) -> List[ServiceCostLine]:
        """
        THE "RATE RESOLVER".
        Iterates through required services, finds the cost from the correct source,
        and returns a list of costs in PGK.
        """
        cost_lines: List[ServiceCostLine] = []
        pending_percentage: List[Tuple[ServiceComponent, ServiceCostLine]] = []
        
        # This holds the calculated cost of services, like "Origin Pickup"
        # so that "Fuel Surcharge (Origin Pickup)" can reference it.
        calculated_service_costs_pgk: Dict[int, Decimal] = {}
        calculated_lines: Dict[int, ServiceCostLine] = {}

        # Process services in order
        for service in services:
            cost_line: Optional[ServiceCostLine] = None
            
            # 1. Check for manual override first
            override = context.overrides.get(service.id)
            if override:
                cost_line = self._resolve_manual_override(context, service, override)
            else:
                # 2. If no override, use the "cost_source" router
                source = service.cost_source
                if source == 'PARTNER_RATECARD':
                    cost_line = self._resolve_partner_ratecard(context, service)
                elif source == 'BASE_COST':
                    cost_line = self._resolve_base_cost(context, service)
                elif source == 'EXPORT_RATECARD':
                    cost_line = self._resolve_export_ratecard(context, service)
                elif source == 'LOCAL_TARIFF':
                    _logger.warning(f"No resolver implemented for LOCAL_TARIFF: {self._service_label(service)}")
                    # cost_line = self._resolve_local_tariff(context, service)
                elif source == 'SURCHARGE':
                    _logger.warning(f"No resolver implemented for SURCHARGE: {self._service_label(service)}")
                    # cost_line = self._resolve_surcharge(context, service)
                else:
                    _logger.error(f"Unknown cost_source '{source}' for service {self._service_label(service)}")

            # 3. Handle missing rates
            if not cost_line:
                if service.cost_type == 'COGS':
                    # This is a cost we MUST find.
                    _logger.error(f"RecoverableMissingRate: No rate found for {self._service_label(service)}")
                    cost_line = ServiceCostLine(
                        service_component=service,
                        cost_pgk=Decimal(0),
                        sell_pgk=Decimal(0),
                        cost_source=service.cost_source,
                        is_rate_missing=True # Flag for the UI
                    )
                else:
                    # This is a RATE_OFFER (sell price). If not found, it's not applicable.
                    _logger.info(f"Rate offer service {self._service_label(service)} not found, skipping.")
                    continue # Skip adding this line

            if service.unit == 'PERCENT_OF_SERVICE' and not cost_line.is_rate_missing:
                pending_percentage.append((service, cost_line))
                continue

            # 4. Add to list and store its value for percentage calcs
            cost_lines.append(cost_line)
            if not cost_line.is_rate_missing:
                # Store the cost for later reference (e.g., for fuel)
                calculated_service_costs_pgk[service.id] = cost_line.cost_pgk
                calculated_lines[service.id] = cost_line

        # Process percentage-based services after base services are available
        for service, cost_line in pending_percentage:
            self._apply_percentage_cost(cost_line, service, calculated_lines)
            cost_lines.append(cost_line)
            if not cost_line.is_rate_missing:
                calculated_service_costs_pgk[service.id] = cost_line.cost_pgk
                calculated_lines[service.id] = cost_line

        return cost_lines

    # --- RESOLVER HELPER METHODS ---

    def _resolve_manual_override(
        self, context: CalculationContext, service: ServiceComponent, override: ManualCostOverride
    ) -> ServiceCostLine:
        """
        Calculates PGK cost from a user-provided spot rate override.
        An override bypasses margin, so cost_pgk and sell_pgk are set to the same value.
        """
        _logger.info(f"Using MANUAL_OVERRIDE for {self._service_label(service)}")
        cost_fcy = Decimal(0)

        # 1. Calculate FCY cost based on unit
        if override.unit == 'PER_KG':
            cost_fcy = context.chargeable_weight_kg * override.cost_fcy
            if override.min_charge_fcy and cost_fcy < override.min_charge_fcy:
                cost_fcy = override.min_charge_fcy
        
        elif override.unit == 'PER_SHIPMENT':
            cost_fcy = override.cost_fcy
        
        # TODO: Add other unit calculations (PER_CBM, etc.)
        
        # 2. Convert FCY cost to PGK (COGS = TT Buy + CAF)
        cost_pgk = self._convert_fcy_to_pgk_cost(
            context.fx_snapshot,
            cost_fcy,
            override.currency
        )
        
        # --- START FIX ---
        # An override should set the sell price directly, bypassing margin.
        # Therefore, we set sell_pgk equal to the calculated cost_pgk.
        
        return ServiceCostLine(
            service_component=service,
            cost_pgk=cost_pgk,
            sell_pgk=cost_pgk,  # <-- SET SELL_PGK = COST_PGK
            cost_fcy=cost_fcy,
            cost_fcy_currency=override.currency,
            cost_source='MANUAL_OVERRIDE',
        )
        # --- END FIX ---
        
    def _resolve_partner_ratecard(
        self, context: CalculationContext, service: ServiceComponent
    ) -> Optional[ServiceCostLine]:
        """
        Finds the PGK cost by querying PartnerRateCard models.
        (e.g., EFM AUD Rate Card)
        """
        _logger.info(f"Resolving PARTNER_RATECARD for {self._service_label(service)}")
        try:
            # 1. Find the rate in the database
            rate = PartnerRate.objects.get(
                lane__rate_card__mode=context.request.mode,
                lane__origin_airport=context.origin_airport,
                lane__destination_airport=context.destination_airport,
                service_component=service,
                # TODO: Add validity checks for the rate_card
                # lane__rate_card__valid_from__lte=datetime.date.today(),
                # lane__rate_card__valid_until__gte=datetime.date.today(),
            )
            
            rate_card = rate.lane.rate_card
            cost_fcy = Decimal(0)
            unit = rate.unit
            
            # 2. Calculate FCY cost based on unit
            if unit == 'PER_KG':
                weight = context.chargeable_weight_kg
                tiers_json = rate.tiering_json or '[]'
                tiers = json.loads(tiers_json)
                
                # Sort tiers by 'break' descending to find the highest applicable break
                tiers.sort(key=lambda x: x['break'], reverse=True)
                
                selected_rate = Decimal(0)
                if not tiers:
                    _logger.warning(f"No tiers defined for {self._service_label(service)} on {rate.lane}")
                
                for tier in tiers:
                    if weight >= tier['break']:
                        selected_rate = Decimal(tier['rate'])
                        break
                
                cost_fcy = weight * selected_rate
                
                # Check minimum
                min_charge = rate.min_charge_fcy
                if cost_fcy < min_charge:
                    cost_fcy = min_charge

            elif unit == 'PER_SHIPMENT':
                cost_fcy = rate.flat_fee_fcy or Decimal(0)
            
            elif unit == 'PERCENT_OF_SERVICE':
                # This is handled by the main _calculate_costs_pgk loop.
                # We just return the percentage value (e.g., 20.00 for 20%)
                # The _apply_percentage_cost function will use this value.
                return ServiceCostLine(
                    service_component=service,
                    cost_pgk=rate.flat_fee_fcy or Decimal(0), # Store percentage here
                    sell_pgk=Decimal(0),
                    cost_source='PARTNER_RATECARD',
                )
            
            # ... add other unit handlers (PER_CBM, etc)

            # 3. Convert FCY cost to PGK (TT Buy + CAF)
            cost_pgk = self._convert_fcy_to_pgk_cost(
                context.fx_snapshot,
                cost_fcy,
                rate_card.currency_code
            )

            return ServiceCostLine(
                service_component=service,
                cost_pgk=cost_pgk,
                sell_pgk=Decimal(0),
                cost_fcy=cost_fcy,
                cost_fcy_currency=rate_card.currency_code,
                cost_source='PARTNER_RATECARD',
            )

        except PartnerRate.DoesNotExist:
            _logger.warning(f"No PartnerRate found for {self._service_label(service)} on lane {context.origin_airport.iata_code}-{context.destination_airport.iata_code}")
            return None
        except Exception as e:
            _logger.error(f"Error resolving PartnerRateCard for {self._service_label(service)}: {e}")
            return None

    def _resolve_base_cost(
        self, context: CalculationContext, service: ServiceComponent
    ) -> Optional[ServiceCostLine]:
        """
        Finds the PGK cost from the ServiceComponent.base_pgk_cost field.
        (e.g., Our own standard handling fee)
        """
        _logger.info(f"Resolving BASE_COST for {self._service_label(service)}")
        if service.base_pgk_cost is None:
            _logger.warning(f"Service {self._service_label(service)} has BASE_COST source but no base_pgk_cost.")
            return None
        
        cost_pgk = Decimal(0)
        
        # 1. Calculate PGK cost based on unit
        if service.unit == 'PER_KG':
            cost_pgk = context.chargeable_weight_kg * service.base_pgk_cost
            if service.min_charge_pgk and cost_pgk < service.min_charge_pgk:
                cost_pgk = service.min_charge_pgk
        
        elif service.unit == 'PER_SHIPMENT':
            cost_pgk = service.base_pgk_cost
        
        # TODO: Add other unit handlers

        return ServiceCostLine(
            service_component=service,
            cost_pgk=cost_pgk,
            sell_pgk=Decimal(0),
            cost_source='BASE_COST',
        )
    
    def _resolve_export_ratecard(
        self, context: CalculationContext, service: ServiceComponent
    ) -> Optional[ServiceCostLine]:
        """
        Finds the PGK cost by querying our own (V2) RateCard models.
        (e.g., Our sell-side Export Airfreight rates)
        """
        _logger.info(f"Resolving EXPORT_RATECARD for {self._service_label(service)}")
        
        # This service is what we used for V2
        rate_card_service = RateCardService()
        try:
            rate_result = rate_card_service.get_air_freight_rate(
                chargeable_kg=context.chargeable_weight_kg,
                origin_code=context.origin_airport.iata_code,
                dest_code=context.destination_airport.iata_code,
            )
            if not rate_result:
                raise ValueError("Empty rate result")

            rate_per_kg = Decimal(str(rate_result.get("rate_per_kg", "0")))
            minimum_charge = Decimal(str(rate_result.get("minimum_charge", "0")))

            cost_pgk = rate_per_kg * context.chargeable_weight_kg
            if minimum_charge and cost_pgk < minimum_charge:
                cost_pgk = minimum_charge

            return ServiceCostLine(
                service_component=service,
                cost_pgk=cost_pgk,
                sell_pgk=Decimal(0),
                cost_source='EXPORT_RATECARD',
            )
        except AttributeError:
            # Legacy RateCardService without get_air_freight_rate support
            _logger.info("RateCardService lacks get_air_freight_rate; falling back to PartnerRate logic.")
        except ValueError as exc:
            _logger.warning(
                f"No ExportRateCard (V2) found for {self._service_label(service)} on lane "
                f"{context.origin_airport.iata_code}-{context.destination_airport.iata_code}: {exc}"
            )
        except Exception as e:
            _logger.error(f"Error resolving ExportRateCard for {self._service_label(service)}: {e}")
        # Fallback to partner ratecard logic if export ratecard is unavailable
        return self._resolve_partner_ratecard(context, service)

    # --- CALCULATION HELPER METHODS ---

    def _apply_percentage_cost(
        self,
        cost_line: ServiceCostLine,
        service: ServiceComponent,
        calculated_lines: Dict[int, ServiceCostLine]
    ):
        """
        Calculates the cost for a percentage-based service.
        This MODIFIES the cost_line object in place.
        """
        base_line = self._find_percentage_base_line(service, calculated_lines)
        if not base_line:
            _logger.error(
                f"Cannot calculate {self._service_label(service)} because the base service "
                "has not been processed yet."
            )
            cost_line.is_rate_missing = True
            return

        percentage_value = cost_line.cost_pgk or Decimal(0)
        if percentage_value <= Decimal("1"):
            percentage_fraction = percentage_value
            percentage_display = (percentage_fraction * Decimal(100)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        else:
            percentage_fraction = percentage_value / Decimal(100)
            percentage_display = percentage_value

        base_cost_pgk = base_line.cost_pgk
        if base_cost_pgk is None:
            _logger.error(
                f"Cannot calculate {self._service_label(service)} because base service "
                f"{self._service_label(base_line.service_component)} cost is missing."
            )
            cost_line.is_rate_missing = True
            return

        cost_line.cost_pgk = (base_cost_pgk * percentage_fraction).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        cost_line.cost_source_description = f"{percentage_display}% of {self._service_label(base_line.service_component)}"
        _logger.info(f"Calculated {self._service_label(service)} as {cost_line.cost_pgk} PGK")

    def _find_percentage_base_line(
        self,
        service: ServiceComponent,
        calculated_lines: Dict[int, ServiceCostLine]
    ) -> Optional[ServiceCostLine]:
        """
        Attempts to identify the base service for percentage-based charges.
        Falls back to parsing the service description if no explicit link exists.
        """
        base_service = getattr(service, "applies_to_service", None)
        if base_service and base_service.id in calculated_lines:
            return calculated_lines[base_service.id]

        # Heuristic: parse the description for a reference like "Foo (Bar)"
        description = getattr(service, "description", "") or ""
        candidates: List[str] = []
        if "(" in description and ")" in description:
            inside = description[description.rfind("(") + 1:description.rfind(")")]
            candidate = inside.strip()
            if candidate:
                candidates.append(candidate)

        for candidate in candidates:
            for line in calculated_lines.values():
                component = line.service_component
                if component.description.lower() == candidate.lower() or component.code.lower() == candidate.lower():
                    return line

        return None

    def _get_rate_info(self, fx: FxSnapshot, currency: str) -> Optional[Dict[str, Decimal]]:
        """
        Safely parses the snapshot's rate payload and returns normalized Decimal values.
        """
        cache = getattr(fx, "_normalized_rates", None)
        if cache is None:
            cache = {}
            setattr(fx, "_normalized_rates", cache)

        if currency in cache:
            return cache[currency]

        raw_rates = fx.rates

        if isinstance(raw_rates, str):
            try:
                parsed_rates = json.loads(raw_rates)
            except json.JSONDecodeError:
                _logger.error(f"FX snapshot rates JSON is invalid: {raw_rates}")
                return None
        elif isinstance(raw_rates, dict):
            parsed_rates = raw_rates
        else:
            _logger.error(f"Unsupported FX rates payload type: {type(raw_rates)}")
            return None

        rate_info = parsed_rates.get(currency)
        if not rate_info:
            return None

        if isinstance(rate_info, (str, int, float, Decimal)):
            try:
                decimal_value = Decimal(str(rate_info))
            except Exception:
                _logger.error(f"Unable to parse FX rate value for {currency}: {rate_info}")
                return None
            normalized = {"tt_buy": decimal_value, "tt_sell": decimal_value}
        elif isinstance(rate_info, dict):
            normalized: Dict[str, Decimal] = {}
            for key in ("tt_buy", "tt_sell"):
                value = rate_info.get(key)
                if value is None:
                    continue
                try:
                    normalized[key] = Decimal(str(value))
                except Exception:
                    _logger.error(f"Unable to parse FX '{key}' value for {currency}: {value}")
                    return None
        else:
            _logger.error(f"Unsupported FX rate entry type for {currency}: {type(rate_info)}")
            return None

        cache[currency] = normalized
        return normalized

    def _convert_fcy_to_pgk_cost(
        self, fx: FxSnapshot, fcy_amount: Decimal, fcy_currency: str
    ) -> Decimal:
        """
        Converts a Foreign Currency (FCY) cost amount to PGK
        using the TT Buy rate and adding CAF.
        """
        if fcy_currency == "PGK":
            return fcy_amount

        rate_info = self._get_rate_info(fx, fcy_currency)
        if not rate_info:
            _logger.error(f"No FX rate found for {fcy_currency} to PGK.")
            raise Exception(f"FX rate not found for {fcy_currency}")

        tt_buy_rate = rate_info.get("tt_buy")
        if not tt_buy_rate:
            _logger.error(f"No 'tt_buy' rate found for {fcy_currency}.")
            raise Exception(f"FX 'tt_buy' rate not found for {fcy_currency}")

        # Add CAF (Currency Adjustment Factor)
        # We use Decimal(1) and Decimal(100) for precision
        caf_rate = tt_buy_rate * (Decimal(1) + (fx.caf_percent / Decimal(100)))
        
        if caf_rate == 0:
            _logger.error(f"CAF-adjusted rate for {fcy_currency} is zero. Cannot divide.")
            raise Exception(f"Invalid FX rate for {fcy_currency}")

        return fcy_amount / caf_rate

    # ==========================================================================
    # STEP 4: APPLY MARGIN
    # ==========================================================================

    def _apply_margin_pgk(
        self, context: CalculationContext, cost_lines: List[ServiceCostLine]
    ) -> List[ServiceCostLine]:
        """
        Applies customer-specific or default margins to COGS lines.
        Skips RATE_OFFER lines (which are already sell prices).
        Skips MANUAL_OVERRIDE lines (which are also already sell prices).
        """
        _logger.info("Applying margins...")
        sell_lines: List[ServiceCostLine] = []

        for line in cost_lines:
            if line.is_rate_missing:
                # If rate is missing, sell price is also "missing"
                sell_lines.append(line)
                continue
            component_label = self._service_label(line.service_component)
            
            # --- START FIX ---
            # Add a check for MANUAL_OVERRIDE to skip margin application
            if line.cost_source == 'MANUAL_OVERRIDE':
                _logger.info(f"Service {component_label} is MANUAL_OVERRIDE. Skipping margin. Sell={line.sell_pgk}")
                sell_lines.append(line)
                continue
            # --- END FIX ---

            # NEW LOGIC: Check cost_type
            if line.service_component.cost_type == 'RATE_OFFER':
                # This is a pre-defined SELL price. No margin applied.
                # We assume the 'cost_pgk' field was populated with the sell price.
                line.sell_pgk = line.cost_pgk
                _logger.info(f"Service {component_label} is RATE_OFFER. Sell=Cost={line.sell_pgk}")
            
            elif line.service_component.cost_type == 'COGS':
                # This is a true cost. Apply margin.
                
                # ... (rest of the margin logic remains the same)
                margin_percent = context.customer_profile.default_margin_percent
                
                line.cost_pgk = line.cost_pgk.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                # Formula: Sell = Cost / (1 - Margin %)
                line.sell_pgk = line.cost_pgk / (Decimal(1) - (margin_percent / Decimal(100)))
                line.sell_pgk = line.sell_pgk.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                _logger.info(f"Applied {margin_percent}% margin to {component_label} (Cost: {line.cost_pgk}, Sell: {line.sell_pgk})")
            
            sell_lines.append(line)

        return sell_lines

    # ==========================================================================
    # STEP 5: CONVERT TO OUTPUT CURRENCY
    # ==========================================================================

    def _convert_to_output_currency(
        self, context: CalculationContext, sell_lines_pgk: List[ServiceCostLine]
    ) -> List[ServiceCostLine]:
        """
        Applies GST (if applicable) and converts all PGK sell lines
        to the final output currency.
        """
        _logger.info(f"Converting to output currency: {context.output_currency}")
        fx = context.fx_snapshot
        output_currency = context.output_currency
        final_lines: List[ServiceCostLine] = []

        # Get the conversion rate (PGK -> Output Currency)
        # This is a SELL price, so we use TT Sell + FX Buffer
        sell_rate = Decimal(1.0)
        if output_currency != "PGK":
            rate_info = self._get_rate_info(fx, output_currency)
            if not rate_info:
                _logger.error(f"No FX rate found for PGK to {output_currency}.")
                raise Exception(f"FX rate not found for {output_currency}")
            
            tt_sell_rate = rate_info.get("tt_sell")
            if not tt_sell_rate:
                _logger.error(f"No 'tt_sell' rate found for {output_currency}.")
                raise Exception(f"FX 'tt_sell' rate not found for {output_currency}")
            
            # Apply FX Buffer
            sell_rate = tt_sell_rate * (Decimal(1) - (fx.fx_buffer_percent / Decimal(100)))
        
        if sell_rate == 0:
            _logger.error(f"Sell rate for {output_currency} is zero. Cannot divide.")
            raise Exception(f"Invalid FX sell rate for {output_currency}")

        # Process each line
        for line in sell_lines_pgk:
            if line.is_rate_missing:
                final_lines.append(line)
                continue

            # 1. Apply GST (if any)
            # We apply GST to the PGK sell price
            tax_rate = line.service_component.tax_rate or Decimal("0")
            tax_fraction = tax_rate if tax_rate <= Decimal("1") else (tax_rate / Decimal(100))
            gst_amount_pgk = (line.sell_pgk * tax_fraction).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            line.sell_pgk_incl_gst = (line.sell_pgk + gst_amount_pgk).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            
            # 2. Convert to Output Currency
            line.sell_fcy = self._quantize_currency(line.sell_pgk * sell_rate)
            line.sell_fcy_incl_gst = self._quantize_currency(line.sell_pgk_incl_gst * sell_rate)
            line.sell_fcy_currency = output_currency
            line.exchange_rate = sell_rate

            final_lines.append(line)

        return final_lines
        
    # ==========================================================================
    # STEP 6: SAVE QUOTE
    # ==========================================================================
    
    @transaction.atomic
    def _save_quote_v3(self, context: CalculationContext, final_lines: List[ServiceCostLine]) -> Quote:
        """
        Saves the completed V3 quote, lines, and totals to the database.
        Returns the newly created Quote object.
        """
        _logger.info("Saving V3 Quote...")
        
        req = context.request
        
        # 1. Find the Contact
        try:
            contact = Contact.objects.get(pk=req.contact_id)
        except Contact.DoesNotExist:
            _logger.error(f"Cannot save quote: Contact {req.contact_id} not found.")
            raise Exception("Contact not found.")

        # Resolve output currency code, ensuring it exists in Currency table
        output_currency_code = context.output_currency
        try:
            Currency.objects.get(code=output_currency_code)
        except Currency.DoesNotExist:
            _logger.error(f"Cannot save quote: Currency {context.output_currency} not found.")
            raise Exception("Output currency not found.")

        # 2. Create the main Quote object
        quote = Quote.objects.create(
            # V3 Fields
            customer=context.customer,
            contact=contact,
            mode=req.mode,
            shipment_type=req.shipment_type,
            incoterm=req.incoterm,
            payment_term=req.payment_term,
            output_currency=output_currency_code,
            origin_code=req.origin_airport_code,
            destination_code=req.destination_airport_code,
            is_dangerous_goods=req.is_dangerous_goods,
            
            # TODO: Set a sensible valid_until date, e.g., 14 days from now
            valid_until=timezone.now().date() + timezone.timedelta(days=14),
            
            # Link to the FX rates used for this calculation
            fx_snapshot=context.fx_snapshot,
            
            # TODO: We need a 'created_by' user
            # created_by=context.user 
        )

        # 3. Create the first QuoteVersion
        request_payload = json.loads(json.dumps(asdict(req), default=str))

        version = QuoteVersion.objects.create(
            quote=quote,
            version_number=1,
            payload_json=request_payload,
            fx_snapshot=context.fx_snapshot,
            status=Quote.Status.DRAFT,
            # TODO: We need a 'created_by' user
            # created_by=context.user
        )

        # 4. Initialize totals
        total_cost_pgk = Decimal(0)
        total_sell_pgk = Decimal(0)
        total_sell_pgk_incl_gst = Decimal(0)
        total_sell_fcy = Decimal(0)
        total_sell_fcy_incl_gst = Decimal(0)
        has_missing_rates = False

        # 5. Create QuoteLine objects for each line
        for line in final_lines:
            QuoteLine.objects.create(
                quote_version=version,
                service_component=line.service_component,
                
                # Store all calculated values for auditing
                cost_pgk=line.cost_pgk,
                cost_fcy=line.cost_fcy,
                cost_fcy_currency=line.cost_fcy_currency,
                
                sell_pgk=line.sell_pgk,
                sell_pgk_incl_gst=line.sell_pgk_incl_gst,
                
                sell_fcy=line.sell_fcy,
                sell_fcy_incl_gst=line.sell_fcy_incl_gst,
                sell_fcy_currency=line.sell_fcy_currency,
                
                exchange_rate=line.exchange_rate,
                cost_source=line.cost_source,
                cost_source_description=line.cost_source_description,
                is_rate_missing=line.is_rate_missing
            )
            
            # 6. Sum up totals (only if rate isn't missing)
            if line.is_rate_missing:
                has_missing_rates = True
            else:
                total_cost_pgk += line.cost_pgk
                total_sell_pgk += line.sell_pgk
                total_sell_pgk_incl_gst += line.sell_pgk_incl_gst
                total_sell_fcy += line.sell_fcy
                total_sell_fcy_incl_gst += line.sell_fcy_incl_gst

        # 7. Create the QuoteTotal object
        # We save a total record even if rates are missing,
        # it will just have 0s. The 'has_missing_rates' flag is key.
        QuoteTotal.objects.create(
            quote_version=version,
            
            total_cost_pgk=total_cost_pgk,
            total_sell_pgk=total_sell_pgk,
            total_sell_pgk_incl_gst=total_sell_pgk_incl_gst,
            
            total_sell_fcy=total_sell_fcy,
            total_sell_fcy_incl_gst=total_sell_fcy_incl_gst,
            total_sell_fcy_currency=output_currency_code,
            
            has_missing_rates=has_missing_rates
        )
        
        _logger.info(f"Successfully created Quote {quote.pk} / Version {version.pk}")

        return quote
