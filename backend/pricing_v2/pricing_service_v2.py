# backend/pricing_v2/pricing_service_v3.py # Conceptually V3
# (Rename the file later if desired, update imports elsewhere accordingly)

import json
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from django.utils import timezone
from django.db import transaction
from django.core.exceptions import ObjectDoesNotExist

# V3 Models
from core.models import FxSnapshot, Policy, Surcharge, LocalTariff, Currency, Airport, Port
from parties.models import Company, Contact, CustomerCommercialProfile
from quotes.models import Quote, QuoteLine, QuoteTotal, QuoteVersion, OverrideNote
from services.models import ServiceComponent, IncotermRule

# V3 Dataclasses (We'll define these)
from .dataclasses_v3 import V3QuoteRequest, CalculationContext, ServiceCostLine

# V2 RateCard service (reusable for FRT_AIR)
from ratecards.services import RateCardService

# --- Helper Functions ---
def decimal_default(obj):
    if isinstance(obj, Decimal):
        return float(obj) # Or str(obj) if exact precision needed in JSON
    raise TypeError

def get_exchange_rate(fx_snapshot: FxSnapshot, from_currency: str, to_currency: str) -> Decimal | None:
    """Helper to get a specific rate from the snapshot JSON."""
    if from_currency == to_currency:
        return Decimal("1.0")
    
    rates_data = fx_snapshot.rates
    
    # Try direct PGK -> FCY (using TT Sell as per V2 logic for output)
    if from_currency == 'PGK' and to_currency != 'PGK':
        rate_info = rates_data.get(to_currency)
        if rate_info and rate_info.get('tt_sell'):
            # Assuming rate is stored as PGK per 1 FCY (e.g., AUD: 2.60)
            # To get FCY per 1 PGK, we need 1 / rate
            return Decimal("1.0") / Decimal(rate_info['tt_sell'])
            
    # Try FCY -> PGK (using TT Buy as per V2 logic for input)
    elif from_currency != 'PGK' and to_currency == 'PGK':
         rate_info = rates_data.get(from_currency)
         if rate_info and rate_info.get('tt_buy'):
             # Assuming rate is stored as PGK per 1 FCY (e.g., AUD: 2.50)
             return Decimal(rate_info['tt_buy']) # PGK per 1 FCY

    # Add logic for FCY -> FCY if needed (e.g., via PGK)
    
    print(f"Warning: Exchange rate not found for {from_currency} -> {to_currency}")
    return None

# --- Main Service ---
class PricingServiceV3:
    """
    V3 Pricing Engine: Customer-first, Incoterm-driven, Multi-currency.
    """

    @transaction.atomic
    def create_quote(self, request_data: dict, user) -> Quote:
        """ Main entry point - passes buy_lines to cost calculation """
        context = self._prepare_calculation_context(request_data, user)
        required_services = self._get_required_services(context)

        # --- PASS USER BUY LINES ---
        user_buy_lines = request_data.get('buy_lines', []) # Get buy lines from original request
        cost_lines_pgk = self._calculate_costs_pgk(context, required_services, user_buy_lines)
        # ---

        sell_lines_pgk = self._apply_margin_pgk(context, cost_lines_pgk)
        # Check for incompleteness *before* final conversion
        if any(line.is_incomplete for line in sell_lines_pgk):
            print("Quote calculation incomplete due to missing costs.")
            # How to handle? Save as DRAFT/INCOMPLETE? Raise specific exception?
            # For now, let's save but maybe set status differently
            # We'll refine this when adding RecoverableMissingRate exception

        sell_lines_output_currency, totals = self._convert_to_output_currency(context, sell_lines_pgk)
        quote = self._save_quote_v3(context, request_data, user, sell_lines_output_currency, totals)

        # Update status if incomplete
        if any(line.is_incomplete for line in sell_lines_pgk):
             quote.status = Quote.Status.INCOMPLETE
             quote.save(update_fields=['status'])
             # TODO: Add reason/notes about incompleteness

        return quote

    # ... (_prepare_calculation_context is fine) ...
    # ... (_get_required_services is fine) ...

    # --- MODIFY THIS METHOD ---
    def _calculate_costs_pgk(self, context: CalculationContext, services: list[ServiceComponent], user_buy_lines: list[dict]) -> list[ServiceCostLine]:
        """
        Calculates PGK costs, now handling FCY inputs based on service.cost_currency_type.
        """
        cost_lines: list[ServiceCostLine] = []
        missing_rate_found = False

        print(f"\nCalculating PGK costs for {len(services)} services...")

        for service in services:
            cost_pgk = Decimal("0.0")
            rate_source_info = f"Base ({service.base_pgk_cost} PGK / {service.unit})"
            is_incomplete = False

            # --- NEW: Check Currency Type First ---
            if service.cost_currency_type == 'FCY':
                # --- Handle FCY Cost Input ---
                print(f"  - Service {service.code} requires FCY input.")
                found_input = None
                # Try to find matching input (simple match on code or description for now)
                # More robust matching might be needed
                for line_input in user_buy_lines:
                    # Prioritize matching service code if provided in input, else description
                    input_code = line_input.get('charge_code') or line_input.get('code')
                    input_desc = line_input.get('description','').lower()
                    service_desc = service.description.lower()

                    if input_code == service.code or service.code in input_desc or service_desc in input_desc :
                         found_input = line_input
                         print(f"    - Found matching user input: {found_input}")
                         break # Take the first match

                if found_input:
                    try:
                        fcy_amount = Decimal(found_input['amount'])
                        fcy_currency = found_input['currency'].upper()

                        if fcy_currency == 'PGK':
                            # User entered PGK for an FCY expected cost - treat as direct PGK cost? Or error?
                            cost_pgk = fcy_amount
                            rate_source_info = f"User Input (PGK): {fcy_amount:.2f} PGK"
                            print(f"    - Warning: Received PGK input for expected FCY service {service.code}. Using PGK value directly.")
                        else:
                            # Get TT Buy rate and CAF from snapshot
                            tt_buy_rate = get_exchange_rate(context.fx_snapshot, fcy_currency, 'PGK') # FCY -> PGK
                            caf_pct = context.fx_snapshot.caf_percent # Use CAF from snapshot

                            if tt_buy_rate is None:
                                print(f"    - ERROR: Missing TT Buy rate for {fcy_currency} -> PGK in snapshot.")
                                is_incomplete = True
                                missing_rate_found = True
                                rate_source_info = f"ERROR: Missing TT Buy rate for {fcy_currency}"
                            else:
                                # Apply CAF (FCY -> PGK uses +CAF)
                                fx_caf_rate = tt_buy_rate * (Decimal("1.0") + caf_pct)
                                cost_pgk = fcy_amount * fx_caf_rate

                                rate_source_info = (
                                    f"User Input: {fcy_amount:.2f} {fcy_currency} "
                                    f"-> TT Buy {tt_buy_rate} * (1+{caf_pct:.2%}) = {fx_caf_rate:.4f} "
                                    f"-> {cost_pgk:.2f} PGK"
                                )
                                print(f"    - Calculated Cost: {cost_pgk:.2f} PGK")

                    except (KeyError, ValueError, TypeError) as e:
                        print(f"    - ERROR: Invalid user input format: {found_input} - {e}")
                        is_incomplete = True
                        missing_rate_found = True
                        rate_source_info = f"ERROR: Invalid input line format - {e}"
                else:
                    # Required FCY input was NOT provided
                    print(f"    - ERROR: Required FCY cost input for {service.code} not found in user_buy_lines.")
                    is_incomplete = True
                    missing_rate_found = True
                    rate_source_info = "ERROR: Required foreign cost input missing"

            elif service.cost_currency_type == 'PGK':
                # --- Handle PGK Cost Calculation (Existing Logic) ---
                print(f"  - Service {service.code} uses PGK logic.")

                # Rate Card Lookup (e.g., for FRT_AIR Export)
                if service.code == 'FRT_AIR' and service.unit == 'KG' and context.request.shipment_type == 'EXPORT':
                     try:
                         # ... (RateCardService lookup as before) ...
                         rate_card_service = RateCardService()
                         rate_info = rate_card_service.get_air_freight_rate(context.chargeable_kg, context.request.origin_code, context.request.destination_code)
                         calculated_freight = context.chargeable_kg * rate_info['rate_per_kg']
                         cost_pgk = max(rate_info['minimum_charge'], calculated_freight)
                         # ... (rate_source_info update) ...
                     except ValueError as e:
                         print(f"    - RATE MISSING (RateCard Export) for {service.code}: {e}")
                         is_incomplete = True; missing_rate_found = True
                         rate_source_info = f"ERROR: {e}"

                # Per KG charges
                elif service.unit == 'KG':
                    # ... (Per KG logic as before, including min charge) ...
                     cost_pgk = service.base_pgk_cost * context.chargeable_kg
                     rate_source_info = f"{context.chargeable_kg:.1f}kg @ {service.base_pgk_cost}/kg = {cost_pgk:.2f} PGK"
                     if service.min_charge_pgk is not None and cost_pgk < service.min_charge_pgk:
                         cost_pgk = service.min_charge_pgk
                         rate_source_info += f" -> Min Applied ({service.min_charge_pgk:.2f} PGK)"

                # Flat rate per Shipment
                elif service.unit == 'SHIPMENT':
                     # ... (Flat rate logic as before) ...
                     cost_pgk = service.base_pgk_cost
                     rate_source_info = f"Flat rate = {cost_pgk:.2f} PGK"
                     # Apply component minimum if applicable (though less common for SHIPMENT)
                     if service.min_charge_pgk is not None and cost_pgk < service.min_charge_pgk:
                         cost_pgk = service.min_charge_pgk
                         rate_source_info += f" -> Min Applied ({service.min_charge_pgk:.2f} PGK)"

                # Tiering Logic
                elif service.tiering_json and isinstance(service.tiering_json, list):
                    # ... (Tiering logic as before) ...
                    # Ensure rate_source_info is updated and is_incomplete/missing_rate_found flags set on failure
                     pass # Placeholder for brevity

                # Fallback/Default
                elif not is_incomplete:
                    # ... (Fallback logic as before, including min charge) ...
                     cost_pgk = service.base_pgk_cost
                     rate_source_info = f"Fallback to Base Cost = {cost_pgk:.2f} PGK / {service.unit}"
                     if service.min_charge_pgk is not None and cost_pgk < service.min_charge_pgk:
                          cost_pgk = service.min_charge_pgk
                          rate_source_info += f" -> Min Applied ({service.min_charge_pgk:.2f} PGK)"
            else:
                 # Unknown cost_currency_type
                 print(f"    - ERROR: Unknown cost_currency_type '{service.cost_currency_type}' for {service.code}")
                 is_incomplete = True
                 missing_rate_found = True
                 rate_source_info = f"ERROR: Invalid cost type '{service.cost_currency_type}'"


            # --- TODO: Integrate Surcharges/LocalTariffs based on context ---

            cost_lines.append(ServiceCostLine(
                service_component=service,
                cost_pgk=cost_pgk if not is_incomplete else Decimal("0.0"),
                source_info=rate_source_info,
                is_incomplete=is_incomplete,
            ))

        # TODO: Raise RecoverableMissingRate exception if missing_rate_found is True
        if missing_rate_found:
             print("WARNING: One or more rates/costs were missing during calculation.")
             # Consider raising specific exception here to inform caller

        print(f"Calculated PGK costs result: {[f'{line.service_component.code}: {line.cost_pgk if not line.is_incomplete else 'INCOMPLETE'}' for line in cost_lines]}")
        return cost_lines

    def _apply_margin_pgk(self, context: CalculationContext, cost_lines: list[ServiceCostLine]) -> list[ServiceCostLine]:
        """
        Applies margin (customer-specific or policy default) to each cost line's PGK cost.
        Populates the sell_price_pgk field. Considers minimum margin rules.
        """
        # --- Determine applicable margin percentage ---
        margin_pct = context.policy.margin_pct # Default from general Policy
        source = "Policy Default"

        # Check for customer-specific override
        if context.customer_profile and context.customer_profile.default_margin_percent is not None:
             margin_pct_override = context.customer_profile.default_margin_percent
             # Optional: Check against minimum margin if defined
             min_margin = context.customer_profile.min_margin_percent
             if min_margin is not None and margin_pct_override < min_margin:
                 print(f"Warning: Customer default margin {margin_pct_override:.2%} is below minimum {min_margin:.2%}. Applying minimum.")
                 margin_pct = min_margin
                 source = f"Customer Minimum ({min_margin:.2%})"
             else:
                 margin_pct = margin_pct_override
                 source = f"Customer Profile ({margin_pct:.2%})"
        else:
            source = f"Policy Default ({margin_pct:.2%})"

        print(f"Applying Margin: {margin_pct:.2%} ({source})")
        margin_multiplier = Decimal("1.0") + margin_pct

        # --- Apply margin to each line ---
        for line in cost_lines:
            service = line.service_component
            
            # Only apply margin if the cost was calculated successfully
            # And potentially check if the service is meant to have margin applied (e.g., audience='SELL' or 'BOTH')
            apply_margin = (
                not line.is_incomplete and 
                line.cost_pgk > 0 and 
                service.audience in ['SELL', 'BOTH']
            )

            if apply_margin:
                 line.sell_price_pgk = (line.cost_pgk * margin_multiplier).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                 line.margin_applied_pct = margin_pct
            else:
                # If no margin applied (e.g., pass-through cost or missing cost), sell = buy
                line.sell_price_pgk = line.cost_pgk if not line.is_incomplete else Decimal("0.0")
                line.margin_applied_pct = None # Explicitly set no margin applied

            print(f"  - {service.code}: Cost={line.cost_pgk:.2f}, Margin={line.margin_applied_pct if line.margin_applied_pct is not None else 'N/A'}, Sell={line.sell_price_pgk:.2f} PGK")

        return cost_lines


    def _convert_to_output_currency(self, context: CalculationContext, sell_lines_pgk: list[ServiceCostLine]) -> tuple[list[ServiceCostLine], dict]:
        """
        Applies GST based on ServiceComponent rules.
        Applies FX Buffer from the snapshot.
        Converts sell_price_pgk (including GST) to the target output currency.
        Calculates final totals in both PGK and output currency.
        """
        target_currency_code = context.output_currency.code
        fx_snapshot = context.fx_snapshot
        req = context.request

        print(f"\nConverting to output currency: {target_currency_code}")

        # --- Get base conversion rate PGK -> Target Currency ---
        # Using our helper function (which assumes TT_SELL for PGK -> FCY)
        rate_pgk_to_output = get_exchange_rate(fx_snapshot, 'PGK', target_currency_code)

        if rate_pgk_to_output is None and target_currency_code != 'PGK':
            # This should ideally be caught earlier or handled more gracefully
            raise ValueError(f"Cannot convert PGK to {target_currency_code}: Missing TT_SELL rate in snapshot ID {fx_snapshot.id}.")

        # --- Apply FX Buffer (as per suggestion: Buffer applied to the rate) ---
        buffer_pct = fx_snapshot.fx_buffer_percent
        effective_rate = rate_pgk_to_output # Will be Decimal('1.0') if target is PGK

        if target_currency_code != 'PGK':
            if buffer_pct > 0:
                # Assuming buffer makes the rate less favorable to protect margin
                # If rate_pgk_to_output is FCY per 1 PGK (e.g., 0.41 AUD per 1 PGK),
                # adding buffer means we charge *more* FCY per PGK.
                effective_rate = rate_pgk_to_output * (Decimal("1.0") + buffer_pct)
                print(f"Applied FX Buffer {buffer_pct:.2%}. Rate: {rate_pgk_to_output} -> {effective_rate}")
            else:
                print(f"No FX Buffer applied (Buffer={buffer_pct:.2%}). Rate: {rate_pgk_to_output}")
        else:
             print("Output currency is PGK. No conversion needed.")


        # --- Initialize totals ---
        subtotal_output = Decimal("0.0")
        gst_total_output = Decimal("0.0")
        subtotal_pgk = Decimal("0.0")
        gst_total_pgk = Decimal("0.0")

        # --- Process each line: Apply GST, Convert ---
        for line in sell_lines_pgk:
            if line.is_incomplete:
                # Skip lines where cost couldn't be determined
                print(f"  - Skipping incomplete line: {line.service_component.code}")
                continue

            service = line.service_component
            sell_pgk = line.sell_price_pgk # This already includes margin

            # --- Apply GST (based on component's tax rate, calculated on PGK sell price) ---
            gst_pct = service.tax_rate
            apply_gst = False # Default to false

            # Determine if GST applies based on rules (Refine this logic!)
            # Example Rule: Apply GST if shipment is Domestic OR if service leg is Destination for Imports
            if req.shipment_type == 'DOMESTIC':
                 apply_gst = True
                 # Domestic might have different GST rules based on service type/location?
            elif req.shipment_type == 'IMPORT' and service.leg == 'DESTINATION':
                 apply_gst = True
            elif req.shipment_type == 'EXPORT' and service.leg == 'ORIGIN' and gst_pct > 0:
                 # Check if origin export services get GST based on tax_code/rate in ServiceComponent
                 apply_gst = True # Example: Assume yes if tax_rate > 0

            # Apply based on flag and rate > 0
            if apply_gst and gst_pct > 0:
                line.gst_pgk = (sell_pgk * gst_pct).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                line.gst_pct = gst_pct # Store the rate applied
                print(f"  - Applied GST {gst_pct:.2%} to {service.code}: {line.gst_pgk:.2f} PGK")
            else:
                line.gst_pgk = Decimal("0.0")
                line.gst_pct = Decimal("0.0")

            # Add to PGK totals
            subtotal_pgk += sell_pgk
            gst_total_pgk += line.gst_pgk

            # --- Convert line sell price and GST to output currency ---
            line_total_pgk_incl_gst = sell_pgk + line.gst_pgk

            if target_currency_code == 'PGK':
                line.sell_price_output = sell_pgk
                line.gst_output = line.gst_pgk
            else:
                 # Apply rounding strategy (e.g., per line, commercial rounding)
                 # Note: Rounding the total including GST might be preferred financially
                 line_total_output = (line_total_pgk_incl_gst * effective_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

                 # Back-calculate approximate components in output currency if needed for display,
                 # but prioritize accuracy of the line total.
                 # A simpler approach is to store the converted total and potentially PGK components.
                 # Let's store the PGK components and the final converted line total.
                 line.sell_price_output = (sell_pgk * effective_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) # For potential display
                 line.gst_output = (line.gst_pgk * effective_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) # For potential display
                 # Ensure line total accuracy: recalculate from rounded components or round the converted total PGK incl GST
                 line_total_output_check = line.sell_price_output + line.gst_output
                 # It might be better to just store the final converted line total directly
                 # For now, let's sum the rounded components.

            line.output_currency = target_currency_code

            # Add rounded output components to totals
            subtotal_output += line.sell_price_output
            gst_total_output += line.gst_output

        # --- Calculate Final Totals ---
        grand_total_output = subtotal_output + gst_total_output
        grand_total_pgk = subtotal_pgk + gst_total_pgk

        # --- Prepare Totals Dictionary ---
        totals = {
            "subtotal_pgk": subtotal_pgk.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            "gst_total_pgk": gst_total_pgk.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            "grand_total_pgk": grand_total_pgk.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),

            "output_currency": target_currency_code,
            "subtotal_output": subtotal_output.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            "gst_total_output": gst_total_output.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            "grand_total_output": grand_total_output.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),

            "exchange_rate_used": effective_rate, # Rate used including buffer
            "base_exchange_rate": rate_pgk_to_output, # Base rate before buffer
            "fx_snapshot_id": str(fx_snapshot.id),
            "caf_percent_snapshot": fx_snapshot.caf_percent, # Keep for audit (though not used in V3 calc flow here)
            "fx_buffer_percent_snapshot": fx_snapshot.fx_buffer_percent,
        }
        print(f"\nFinal Totals Calculated:\n  PGK: {totals['grand_total_pgk']}\n  {totals['output_currency']}: {totals['grand_total_output']}")
        print(f"  FX Details: Base Rate={totals['base_exchange_rate']}, Effective Rate={totals['exchange_rate_used']}, Buffer={totals['fx_buffer_percent_snapshot']:.2%}")

        return sell_lines_pgk, totals


    def _save_quote_v3(self, context: CalculationContext, request_data: dict, user, processed_lines: list[ServiceCostLine], totals: dict) -> Quote:
        """
        Saves the V3 Quote, QuoteVersion, QuoteLines, and QuoteTotal to the DB.
        """
        req = context.request
        
        # Create the main Quote object
        quote = Quote.objects.create(
            customer=req.customer,
            contact=req.contact,
            mode=req.mode,
            shipment_type=req.shipment_type,
            incoterm=req.incoterm,
            payment_term=req.payment_term,
            output_currency=context.output_currency,
            origin_code=req.origin_code,
            destination_code=req.destination_code,
            is_dangerous_goods=req.is_dangerous_goods,
            policy=context.policy, # Store fallback policy for reference
            fx_snapshot=context.fx_snapshot,
            status=Quote.Status.DRAFT, # Initial status
            created_by=user,
            # valid_until defaults set in model save method
        )

        # Create the first QuoteVersion
        # Determine next version number
        last_version_no = QuoteVersion.objects.filter(quote=quote).order_by('-version_no').values_list('version_no', flat=True).first() or 0
        current_version_no = last_version_no + 1
        
        quote_version = QuoteVersion.objects.create(
            quote=quote,
            version_no=current_version_no,
            payload_json=json.dumps(request_data, default=decimal_default),
            policy=context.policy,
            fx_snapshot=context.fx_snapshot,
            status=quote.status,
            reason="Initial Quote Calculation",
            created_by=user
        )

        # Create QuoteLine objects from processed lines
        for line in processed_lines:
            service = line.service_component
            QuoteLine.objects.create(
                quote=quote,
                # Link version? Maybe not needed if version stores payload
                section=service.leg,
                charge_code=service.code,
                description=service.description,
                basis=line.source_info, # Store how cost was derived
                quantity=context.chargeable_kg if service.unit == 'KG' else Decimal("1.0"), # Simplification
                rate=service.base_pgk_cost, # Store base rate for reference?
                currency='PGK', # Base calculation currency
                buy_amount_native=line.cost_pgk, # Store calculated PGK cost
                sell_amount_pgk=line.sell_price_pgk,
                gst_amount_pgk=line.gst_pgk,
                margin_applied_pct=line.margin_applied_pct,
                # TODO: Add CAF/Buffer pct applied?
                source_references={"service_component_id": str(service.id)}
            )

        # Create QuoteTotal object
        QuoteTotal.objects.create(
            quote=quote,
            subtotal_pgk=totals['subtotal_pgk'],
            gst_total_pgk=totals['gst_total_pgk'],
            grand_total_pgk=totals['grand_total_pgk'],
            output_currency=totals['output_currency'],
            grand_total_output_currency=totals['grand_total_output'],
            # Add notes about FX rate used etc.?
            notes=f"FX Rate (PGK->{totals['output_currency']}) used: {totals['exchange_rate_used']:.6f} (incl. {totals['fx_buffer_percent_snapshot']:.2%} buffer). Snapshot ID: {totals['fx_snapshot_id']}"
        )

        # Optionally update quote status if calculation complete/valid
        # if not any(line.cost_pgk < 0 for line in processed_lines):
        #    quote.status = Quote.Status.FINAL
        #    quote.save()

        print(f"Saved V3 Quote: {quote.quote_number} v{current_version_no}")
        return quote