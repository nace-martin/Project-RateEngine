# backend/pricing_v2/pricing_service_v2.py

import math
import json
from datetime import datetime, date
from decimal import Decimal
import uuid

from django.utils import timezone
from django.db import transaction

from core.models import FxSnapshot, Policy, Surcharge, LocalTariff
from parties.models import Company
from quotes.models import Quote, QuoteLine, QuoteTotal
# NOTE: We will create this dataclass in the next step.
from .dataclasses_v2 import QuoteRequest

# A comprehensive helper for JSON serialization
def json_serializer_default(obj):
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, uuid.UUID):
        return str(obj)
    raise TypeError

class PricingServiceV2:
    """
    A stateless service that calculates quotes based on a request object
    and the rules stored in the database.
    """

    @transaction.atomic
    def create_quote(self, request_data: dict) -> Quote:
        """
        Main entry point for creating a quote. It orchestrates the entire process
        from validation to calculation and database persistence.
        """
        # 1. Prepare the Quote Request and find the correct rules
        quote_request = self._prepare_quote_request(request_data)
        
        # 2. Create the main Quote object with audit links
        quote = Quote.objects.create(
            scenario=quote_request.scenario,
            bill_to=quote_request.bill_to,
            shipper=quote_request.shipper,
            consignee=quote_request.consignee,
            policy=quote_request.policy,
            fx_snapshot=quote_request.fx_snapshot,
            request_details=json.dumps(request_data, default=json_serializer_default)
        )

        # 3. Route to the correct calculation method based on scenario
        if quote_request.scenario == Quote.Scenario.IMP_D2D_COLLECT:
            self._calculate_import_d2d_collect(quote, quote_request)
        elif quote_request.scenario == Quote.Scenario.EXP_D2D_PREPAID:
            self._calculate_export_d2d_prepaid(quote, quote_request)
        elif quote_request.scenario == Quote.Scenario.IMP_A2D_AGENT:
            self._calculate_import_a2d_agent(quote, quote_request)
        else:
            raise NotImplementedError(f"Scenario {quote_request.scenario} is not yet implemented.")
            
        return quote

    def _prepare_quote_request(self, request_data: dict) -> QuoteRequest:
        """
        Validates the raw request and enriches it with the necessary database
        objects (Policy, FxSnapshot, Parties) for calculation.
        """
        # Resolve Policy
        policy_id = request_data.get("policy_id", "current")
        if policy_id == "current":
            policy = Policy.objects.filter(is_active=True, effective_from__lte=timezone.now()).latest('effective_from')
        else:
            policy = Policy.objects.get(id=policy_id)

        # Resolve FX Snapshot
        fx_asof = request_data.get("fx_asof", str(timezone.now().date()))
        fx_date = datetime.fromisoformat(fx_asof).date()
        fx_snapshot = FxSnapshot.objects.filter(as_of_timestamp__date=fx_date).latest('as_of_timestamp')

        # Resolve Parties
        bill_to = Company.objects.get(id=request_data["bill_to_id"])
        shipper = Company.objects.get(id=request_data["shipper_id"])
        consignee = Company.objects.get(id=request_data["consignee_id"])
        
        # Create a structured dataclass for easier use
        return QuoteRequest(
            scenario=request_data["scenario"],
            policy=policy,
            fx_snapshot=fx_snapshot,
            bill_to=bill_to,
            shipper=shipper,
            consignee=consignee,
            chargeable_kg=Decimal(request_data["chargeable_kg"]),
            buy_lines=request_data.get("buy_lines", []),
            origin_code=request_data.get("origin_code"),
            destination_code=request_data.get("destination_code"),
            agent_dest_lines_aud=request_data.get("agent_dest_lines_aud", [])
        )

    def _calculate_import_d2d_collect(self, quote: Quote, request: QuoteRequest):
        """
        Calculates a standard Import D2D Collect quote.
        - Converts foreign buy charges using TT BUY + CAF.
        - Applies a margin.
        - Adds local PNG destination charges without margin.
        """
        policy = request.policy
        fx_rates = request.fx_snapshot.rates
        
        buy_total_pgk = Decimal("0.0")

        # --- 1. Process Foreign Currency Buy Lines ---
        foreign_buy_lines = [line for line in request.buy_lines if line['currency'] != 'PGK']
        
        for line in foreign_buy_lines:
            currency = line['currency']
            amount_fcy = Decimal(line['amount'])
            
            # Get TT_BUY rate from our snapshot
            rate_info = fx_rates.get(currency, {})
            tt_buy_rate = Decimal(rate_info.get('tt_buy'))
            
            # Apply CAF (Currency Adjustment Factor) from the Policy
            fx_caf_rate = tt_buy_rate * (Decimal("1.0") + policy.caf_import_pct)
            
            # Convert to PGK
            # Assuming is_pgk_per_fcy = True based on our spec
            amount_pgk = amount_fcy * fx_caf_rate
            buy_total_pgk += amount_pgk

            # Create an auditable QuoteLine for this charge
            QuoteLine.objects.create(
                quote=quote,
                section=QuoteLine.Section.ORIGIN,
                charge_code=line.get('charge_code', 'FRT'),
                description=line['description'],
                currency=currency,
                basis='FLAT', # Placeholder
                quantity=Decimal('1.00'), # Placeholder
                rate=amount_fcy, # Placeholder
                buy_amount_native=amount_fcy,
                sell_amount_pgk=amount_pgk, # Pre-margin
                caf_applied_pct=policy.caf_import_pct,
                source_references={'buy_line_input': line, 'fx_rate_used': str(tt_buy_rate)}
            )

        # --- 2. Apply Margin to the Converted Total ---
        sell_component_pgk = buy_total_pgk * (Decimal("1.0") + policy.margin_pct)
        
        # Now, update the sell_amount_pgk on the lines to include margin
        margin_multiplier = (Decimal("1.0") + policy.margin_pct)
        for q_line in quote.lines.filter(section=QuoteLine.Section.ORIGIN):
            q_line.sell_amount_pgk *= margin_multiplier
            q_line.margin_applied_pct = policy.margin_pct
            q_line.save()

        # --- 3. Add PNG Destination Charges (No CAF, No Margin) ---
        dest_total_pgk = Decimal("0.0")
        gst_total_pgk = Decimal("0.0")

        # Example: Fetching a cartage charge from the new LocalTariff model
        try:
            cartage_tariff = LocalTariff.objects.get(country_id='PG', charge_code='CARTAGE')
            # Here you would implement the specific cartage formula
            # For now, a placeholder value
            cartage_base = min(max(Decimal(95), Decimal(1.50) * request.chargeable_kg), Decimal(500))
            cartage_gst = cartage_base * cartage_tariff.gst_rate
            dest_total_pgk += (cartage_base + cartage_gst)
            gst_total_pgk += cartage_gst

            QuoteLine.objects.create(
                quote=quote,
                section=QuoteLine.Section.DESTINATION,
                charge_code='CARTAGE',
                description='PNG Destination Cartage',
                currency='PGK',
                basis=cartage_tariff.basis,
                quantity=request.chargeable_kg,
                rate=cartage_tariff.rate or Decimal('0.0'),
                buy_amount_native=cartage_base,
                sell_amount_pgk=cartage_base, # No margin
                gst_amount_pgk=cartage_gst,
                source_references={'tariff_id': str(cartage_tariff.id)}
            )
        except LocalTariff.DoesNotExist:
            # Handle case where tariff is not found
            pass 
            
        # ... Add other local tariffs (clearance, agency fee) in the same way ...

        # --- 4. Finalize and Save Totals ---
        grand_total_pgk = sell_component_pgk + dest_total_pgk
        
        QuoteTotal.objects.create(
            quote=quote,
            subtotal_pgk=sell_component_pgk + (dest_total_pgk - gst_total_pgk),
            gst_total_pgk=gst_total_pgk,
            grand_total_pgk=grand_total_pgk
        )

    def _calculate_export_d2d_prepaid(self, quote: Quote, request: QuoteRequest):
        """
        Calculates a standard Export D2D Prepaid quote.
        """
        from ratecards.services import RateCardService

        policy = request.policy
        fx_rates = request.fx_snapshot.rates
        chargeable_kg = request.chargeable_kg

        total_buy_pgk = Decimal("0.0")

        # 1. Calculate Origin Freight Charges from Rate Card
        rate_card_service = RateCardService()
        freight_rate_info = rate_card_service.get_air_freight_rate(chargeable_kg, request.origin_code, request.destination_code)
        
        rate_per_kg = freight_rate_info['rate_per_kg']
        min_charge = freight_rate_info['minimum_charge']
        
        freight_buy_pgk = max(rate_per_kg * chargeable_kg, min_charge)
        total_buy_pgk += freight_buy_pgk

        QuoteLine.objects.create(
            quote=quote,
            section=QuoteLine.Section.FREIGHT,
            charge_code='AIR_FREIGHT',
            description=f"Air Freight from {request.origin_code} to {request.destination_code}",
            currency='PGK',
            basis=f"{chargeable_kg}kg @ {rate_per_kg}/kg",
            quantity=chargeable_kg,
            rate=rate_per_kg,
            buy_amount_native=freight_buy_pgk,
            sell_amount_pgk=freight_buy_pgk, # Pre-margin
            source_references={'rate_break_id': str(freight_rate_info['rate_break_id'])}
        )

        # 2. Calculate Origin Surcharges
        surcharges = Surcharge.objects.filter(is_active=True, effective_from__lte=timezone.now().date())
        for surcharge in surcharges:
            surcharge_buy_pgk = Decimal('0.0')
            if surcharge.basis == Surcharge.Basis.FLAT:
                surcharge_buy_pgk = surcharge.rate
            elif surcharge.basis == Surcharge.Basis.PER_KG:
                surcharge_buy_pgk = surcharge.rate * chargeable_kg
            
            if surcharge.minimum_charge and surcharge_buy_pgk < surcharge.minimum_charge:
                surcharge_buy_pgk = surcharge.minimum_charge
            
            total_buy_pgk += surcharge_buy_pgk

            QuoteLine.objects.create(
                quote=quote,
                section=QuoteLine.Section.ORIGIN,
                charge_code=surcharge.code,
                description=surcharge.description,
                currency=surcharge.currency.code,
                basis=surcharge.basis,
                quantity=chargeable_kg if surcharge.basis == Surcharge.Basis.PER_KG else Decimal('1.0'),
                rate=surcharge.rate,
                buy_amount_native=surcharge_buy_pgk,
                sell_amount_pgk=surcharge_buy_pgk, # Pre-margin
                source_references={'surcharge_id': str(surcharge.id)}
            )

        # 3. Calculate Destination Charges (AUD -> PGK)
        rate_info = fx_rates.get('AUD', {})
        tt_buy_rate = Decimal(rate_info.get('tt_buy'))
        fx_caf_rate = tt_buy_rate * (Decimal("1.0") + policy.caf_import_pct)

        for line in request.agent_dest_lines_aud:
            amount_aud = Decimal(line['amount'])
            dest_buy_pgk = amount_aud * fx_caf_rate
            total_buy_pgk += dest_buy_pgk

            QuoteLine.objects.create(
                quote=quote,
                section=QuoteLine.Section.DESTINATION,
                charge_code=line.get('charge_code', 'DEST_AGENT'),
                description=line['description'],
                currency='AUD',
                basis='FLAT',
                quantity=Decimal('1.0'),
                rate=amount_aud,
                buy_amount_native=amount_aud,
                sell_amount_pgk=dest_buy_pgk, # Pre-margin
                caf_applied_pct=policy.caf_import_pct,
                source_references={'buy_line_input': line, 'fx_rate_used': str(tt_buy_rate)}
            )

        # 4. Apply Margin to all lines
        margin_multiplier = (Decimal("1.0") + policy.margin_pct)
        for q_line in quote.lines.all():
            q_line.sell_amount_pgk *= margin_multiplier
            q_line.margin_applied_pct = policy.margin_pct
            q_line.save()

        # 5. Finalize and Save Totals
        total_sell_pgk = total_buy_pgk * margin_multiplier
        
        QuoteTotal.objects.create(
            quote=quote,
            subtotal_pgk=total_sell_pgk,
            gst_total_pgk=Decimal("0.00"), # No GST in this scenario
            grand_total_pgk=total_sell_pgk
        )

    def _calculate_import_a2d_agent(self, quote: Quote, request: QuoteRequest):
        """
        Calculates a Prepaid Import A2D quote for an overseas agent in AUD.
        - Converts PGK destination charges using TT SELL - CAF.
        - No margin is applied.
        - Rounds the final AUD amount up to the nearest whole dollar.
        """
        policy = request.policy
        fx_rates = request.fx_snapshot.rates
        
        # --- 1. Get FX Rate and Apply Negative CAF ---
        rate_info = fx_rates.get("AUD", {})
        tt_sell_rate = Decimal(rate_info.get('tt_sell'))
        # Note the subtraction for the export CAF rule
        effective_fx = tt_sell_rate * (Decimal("1.0") - policy.caf_export_pct)

        # --- 2. Calculate PGK Destination Charges ---
        # In a real scenario, these would come from the request or LocalTariffs.
        # For now, we'll use the example from the spec.
        # A more robust implementation would fetch these from the DB.
        pgk_lines = [
            {'desc': 'Customs Clearance', 'amount': Decimal('330.00')},
            {'desc': 'Agency Fee', 'amount': Decimal('275.00')},
            {'desc': 'Handling', 'amount': Decimal('181.50')},
        ]

        # --- 3. Convert to AUD and Round ---
        total_aud = Decimal("0.0")
        for line in pgk_lines:
            pgk_val = line['amount']
            # Convert to AUD
            aud_raw = pgk_val / effective_fx
            # Round up to the nearest whole number (per-line rounding)
            aud_final = Decimal(math.ceil(aud_raw))
            total_aud += aud_final

            QuoteLine.objects.create(
                quote=quote,
                section=QuoteLine.Section.DESTINATION,
                charge_code=line['desc'].upper().replace(' ', '_'),
                description=line['desc'],
                currency='AUD', # Output currency is AUD
                basis='FLAT', # Placeholder
                quantity=Decimal('1.00'), # Placeholder
                rate=pgk_val, # Placeholder
                buy_amount_native=pgk_val, # Store the original PGK value
                sell_amount_pgk=aud_final, # Store the final rounded AUD value
                caf_applied_pct=-policy.caf_export_pct, # Note the negative CAF
                rounding_applied=True,
                source_references={'original_pgk_amount': str(pgk_val)}
            )
        
        # --- 4. Finalize Totals ---
        QuoteTotal.objects.create(
            quote=quote,
            subtotal_pgk=sum(l['amount'] for l in pgk_lines), # Subtotal is the sum of PGK buys
            gst_total_pgk=Decimal("0.0"), # Assuming GST is included in the lines
            grand_total_pgk=sum(l['amount'] for l in pgk_lines),
            output_currency="AUD",
            grand_total_output_currency=total_aud,
            notes=f"Converted from PGK using TT SELL x (1 - {policy.caf_export_pct*100}% CAF). No margin. Rounded up to whole AUD."
        )
