import uuid
import json
import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Dict, List, Optional
from uuid import UUID

from core.models import FxSnapshot, Policy
from django.db import models
from core.dataclasses import (
    QuoteInput, QuoteCharges, CalculatedChargeLine, CalculatedTotals
)
from pricing_v4.engine.export_engine import ExportPricingEngine
from pricing_v4.engine.import_engine import ImportPricingEngine, PaymentTerm, ServiceScope
from pricing_v4.engine.domestic_engine import DomesticPricingEngine
from pricing_v4.models import ProductCode, CustomerDiscount
from services.models import ServiceComponent

logger = logging.getLogger(__name__)


class PricingMode:
    """Pricing mode constants."""
    NORMAL = "NORMAL"
    SPOT = "SPOT"


class PricingServiceV4Adapter:
    """
    Adapts V4 Pricing Engines (Export, Import, Domestic) to the V3 Service interface.
    This allows swapping the implementation in views.py without changing the entire view logic.
    
    SPOT Mode Integration:
    - If spot_envelope_id is provided, validates SPE and uses its charges as BUY lines
    - Applies FX/CAF/margin as normal, marks output as pricing_mode=SPOT
    """

    def __init__(self, quote_input: QuoteInput, spot_envelope_id: Optional[UUID] = None):
        self.quote_input = quote_input
        self.spot_envelope_id = spot_envelope_id
        self.pricing_mode = PricingMode.NORMAL
        
        # Fetch Policy and FX just like V3 did, so views can save them to Quote
        try:
            self.policy = Policy.objects.filter(is_active=True).latest('effective_from')
        except Policy.DoesNotExist:
            self.policy = None
            
        try:
            self.fx_snapshot = FxSnapshot.objects.latest('as_of_timestamp')
        except FxSnapshot.DoesNotExist:
            self.fx_snapshot = None

    def get_fx_snapshot(self):
        return self.fx_snapshot

    def get_policy(self):
        return self.policy
    
    def get_pricing_mode(self) -> str:
        """Return the pricing mode used (NORMAL or SPOT)."""
        return self.pricing_mode
    
    # =========================================================================
    # CUSTOMER DISCOUNT METHODS
    # =========================================================================
    
    def _get_customer_discounts(self) -> Dict[int, 'CustomerDiscount']:
        """
        Load active customer discounts for all ProductCodes.
        
        Returns:
            Dict mapping ProductCode ID to CustomerDiscount instance
        """
        customer_id = getattr(self.quote_input, 'customer_id', None)
        if not customer_id:
            return {}
        quote_date = self.quote_input.quote_date or date.today()
        
        try:
            discounts = CustomerDiscount.objects.filter(
                customer_id=customer_id,
                valid_until__gte=quote_date
            ).filter(
                # valid_from is null OR valid_from <= quote_date
                models.Q(valid_from__isnull=True) | models.Q(valid_from__lte=quote_date)
            ).select_related('product_code')
            
            return {d.product_code_id: d for d in discounts}
        except Exception as e:
            logger.warning(f"Failed to load customer discounts: {e}")
            return {}
    
    def _apply_customer_discounts(self, lines: List[CalculatedChargeLine]) -> List[CalculatedChargeLine]:
        """
        Apply customer-specific discounts to sell prices.
        
        Supports multiple discount types:
        - PERCENTAGE: Reduce by X%
        - FLAT_AMOUNT: Reduce by fixed amount
        - RATE_REDUCTION: Not applied here (needs weight context at engine level)
        - FIXED_CHARGE: Replace sell price entirely
        
        Discounts are applied before GST is recalculated.
        """
        discounts = self._get_customer_discounts()
        if not discounts:
            return lines
        
        # Build a mapping from ServiceComponent code to ProductCode ID
        sc_codes = [l.service_component_code for l in lines]
        pc_map = {}
        try:
            for pc in ProductCode.objects.filter(code__in=sc_codes):
                pc_map[pc.code] = pc.id
        except Exception as e:
            logger.warning(f"Failed to map ServiceComponent to ProductCode: {e}")
            return lines
        
        for line in lines:
            pc_id = pc_map.get(line.service_component_code)
            if pc_id and pc_id in discounts:
                discount = discounts[pc_id]
                original_sell = line.sell_pgk
                discounted_sell = original_sell
                
                # Apply discount based on type
                if discount.discount_type == CustomerDiscount.TYPE_PERCENTAGE:
                    discount_pct = discount.discount_value / Decimal('100')
                    discounted_sell = original_sell * (Decimal('1') - discount_pct)
                    
                elif discount.discount_type == CustomerDiscount.TYPE_FLAT_AMOUNT:
                    # TODO: Handle currency conversion if discount.currency != 'PGK'
                    discounted_sell = max(Decimal('0'), original_sell - discount.discount_value)
                    
                elif discount.discount_type == CustomerDiscount.TYPE_FIXED_CHARGE:
                    # Replace the entire sell price with fixed charge
                    discounted_sell = discount.discount_value
                    
                elif discount.discount_type == CustomerDiscount.TYPE_RATE_REDUCTION:
                    # Rate reduction requires weight context - log warning and skip
                    logger.warning(
                        f"RATE_REDUCTION discount for {line.service_component_code} "
                        "cannot be applied at this stage (requires weight context)"
                    )
                    continue
                    
                elif discount.discount_type == CustomerDiscount.TYPE_MARGIN_OVERRIDE:
                    # Recalculate sell from cost using custom margin rate
                    # discount_value is the margin % (e.g., 15.00 for 15%)
                    custom_margin = discount.discount_value / Decimal('100')
                    cost = line.cost_pgk
                    if cost > 0:
                        discounted_sell = cost * (Decimal('1') + custom_margin)
                    else:
                        # No cost info - can't apply margin override
                        logger.warning(
                            f"MARGIN_OVERRIDE for {line.service_component_code} "
                            "cannot be applied (no cost data)"
                        )
                        continue
                
                if discounted_sell == original_sell:
                    continue  # No change
                
                # Recalculate GST on discounted amount
                gst_amount = line.sell_pgk_incl_gst - line.sell_pgk
                gst_rate = gst_amount / original_sell if original_sell > 0 else Decimal('0')
                new_gst = discounted_sell * gst_rate
                
                try:
                    line.sell_pgk = discounted_sell
                    line.sell_pgk_incl_gst = discounted_sell + new_gst
                    
                    # Update FCY if applicable
                    if line.sell_fcy_currency != 'PGK' and original_sell > 0:
                        ratio = discounted_sell / original_sell
                        line.sell_fcy = line.sell_fcy * ratio
                        line.sell_fcy_incl_gst = line.sell_fcy_incl_gst * ratio
                    else:
                        line.sell_fcy = discounted_sell
                        line.sell_fcy_incl_gst = discounted_sell + new_gst
                        
                    logger.debug(
                        f"Applied {discount.discount_type} discount to {line.service_component_code}: "
                        f"{original_sell} -> {discounted_sell}"
                    )
                except AttributeError:
                    logger.warning(f"Cannot apply discount to frozen line: {line.service_component_code}")
        
        return lines

    def calculate_charges(self) -> QuoteCharges:
        shipment = self.quote_input.shipment
        
        # 1. Calculate Standard Charges (Base)
        standard_lines = []
        try:
            standard_lines = self._calculate_standard_lines()
        except Exception as e:
            # If standard engine fails (e.g. Unsupported Route), and we have no SPOT info, re-raise.
            # If we have SPOT info, proceed with SPOT only overlay.
            if self.spot_envelope_id:
                logger.warning(f"Standard pricing engine failed, relying on SPOT overlay: {e}")
            else:
                raise e

        # 2. Calculate Spot Charges (Overlay)
        spot_lines = []
        if self.spot_envelope_id:
            spot_lines = self._calculate_spot_lines()
            self.pricing_mode = PricingMode.SPOT

        # 3. Merge Strategies (Standard + Spot Overlay)
        # Using bucket-level override logic
        final_lines = self._merge_charge_lines(standard_lines, spot_lines)
        
        # 4. Apply Customer Discounts (before GST recalculation)
        final_lines = self._apply_customer_discounts(final_lines)
        
        # 5. Calculate Final Totals (Unified Pass)
        return self._calculate_totals(final_lines)

    def _calculate_standard_lines(self) -> List[CalculatedChargeLine]:
        """Run standard V4 pricing engine and return raw charge lines."""
        shipment = self.quote_input.shipment
        engine = None
        result = None
        
        # Calculate weight
        gross_weight = sum(p.gross_weight_kg * p.pieces for p in shipment.pieces)
        # Simple volume weight? The engines take 'weight_kg'. Let's assume charge weight logic is inside or handled here.
        # For now, pass gross weight as verified in scripts.
        chargeable_weight = gross_weight # Simplify for now
        
        origin_code = shipment.origin_location.code
        dest_code = shipment.destination_location.code

        if shipment.shipment_type == 'EXPORT':
            # Export Engine
            engine = ExportPricingEngine(
                quote_date=self.quote_input.quote_date, # Add quote_date
                origin=origin_code,
                destination=dest_code,
                chargeable_weight_kg=chargeable_weight # Rename param
            )
        elif shipment.shipment_type == 'IMPORT':
            # Import Engine
            # Convert strings to enum values
            payment_term_enum = PaymentTerm(shipment.payment_term)
            service_scope_enum = ServiceScope(shipment.service_scope)
            
            engine = ImportPricingEngine(
                quote_date=self.quote_input.quote_date,
                origin=origin_code,
                destination=dest_code,
                chargeable_weight_kg=chargeable_weight,
                payment_term=payment_term_enum,
                service_scope=service_scope_enum
            )
        elif shipment.shipment_type == 'DOMESTIC':
            # Domestic Engine
            engine = DomesticPricingEngine(
                cogs_origin=origin_code,
                destination=dest_code,
                weight_kg=chargeable_weight,
                service_scope=shipment.service_scope,
                quote_date=self.quote_input.quote_date
            )
        else:
            raise NotImplementedError(f"Unsupported shipment type: {shipment.shipment_type}")
            
        # 2. Run Calculation
        # Export Engine requires product_code_ids; others may not
        if shipment.shipment_type == 'EXPORT':
            product_code_ids = ExportPricingEngine.get_product_codes(
                is_dg=shipment.is_dangerous_goods,
                service_scope=shipment.service_scope
            )
            result = engine.calculate_quote(product_code_ids)
        else:
            # Import and Domestic engines use calculate_quote() without args
            result = engine.calculate_quote()
        
        # 3. Convert Result to V3 QuoteCharges (now returns List[CalculatedChargeLine])
        return self._convert_result_to_lines(result)

    def _convert_result_to_lines(self, result) -> List[CalculatedChargeLine]:
        lines: List[CalculatedChargeLine] = []
        
        # We need to consolidate Cost and Sell lines into single ChargeLines for V3.
        # V3 expects ONE line per ServiceComponent (usually).
        # We map V4 ProductCodes to V3 ServiceComponents using the code.
        
        # 1. Gather all line data into a map by Product Code
        # Structure: { code: { 'cost': ..., 'sell': ..., 'description': ... } }
        
        consolidated = {}
        
        # Helper to process V4 lines (they come in different shapes from different engines)
        # Export: QuoteResult.lines -> ChargeLineResult (has product_code, cost, sell)
        # Import: QuoteResult.xxx_lines -> ChargeLine (has product_code, cost, sell)
        # Domestic: QuoteResult.cogs_breakdown / sell_breakdown -> BillableCharge (separated)
        
        import_or_export_lines = []
        if hasattr(result, 'lines'): # Export
            import_or_export_lines = result.lines
        elif hasattr(result, 'origin_lines'): # Import
            import_or_export_lines = result.origin_lines + result.freight_lines + result.destination_lines
            
        # Process Import/Export Style (Unified lines)
        for line in import_or_export_lines:
            code = line.product_code
            # Map V4 category to V3 bucket
            # Use the leg from the V4 engine if available
            leg = getattr(line, 'leg', 'MAIN')
            
            # Map V4 category/leg to V3 bucket
            v4_category = getattr(line, 'category', 'HANDLING')
            bucket = 'origin_charges'
            if v4_category == 'FREIGHT' or leg == 'FREIGHT':
                bucket = 'airfreight'
                leg = 'MAIN'
            elif leg == 'DESTINATION' or 'DEST' in code.upper() or 'DEST' in getattr(line, 'description', '').upper():
                bucket = 'destination_charges'
                leg = 'DESTINATION'
            elif leg == 'ORIGIN' or v4_category in ['HANDLING', 'DOCUMENTATION', 'SCREENING', 'AGENCY', 'CARTAGE', 'SURCHARGE', 'CLEARANCE']:
                bucket = 'origin_charges'
                leg = 'ORIGIN'

            sell_currency = getattr(line, 'sell_currency', 'PGK')
            cost_currency = getattr(line, 'cost_currency', sell_currency)
            if code not in consolidated:
                consolidated[code] = {
                    'description': line.description,
                    'cost_amount': Decimal('0'),
                    'sell_amount': Decimal('0'),
                    'sell_incl_gst': Decimal('0'),
                    'gst_amount': Decimal('0'),
                    'is_rate_missing': getattr(line, 'is_rate_missing', False),
                    'bucket': bucket,
                    'leg': leg,
                    'sell_currency': sell_currency,
                    'cost_currency': cost_currency,
                    'agent_name': getattr(line, 'agent_name', None),  # NEW
                }
            
            # Sum up (though typically one per code)
            consolidated[code]['cost_amount'] += line.cost_amount
            consolidated[code]['sell_amount'] += line.sell_amount
            
            # Handle Tax
            gst = getattr(line, 'gst_amount', Decimal('0'))
            if hasattr(line, 'sell_incl_gst'):
                consolidated[code]['sell_incl_gst'] += line.sell_incl_gst
            else:
                 # Default logic if missing
                consolidated[code]['sell_incl_gst'] += line.sell_amount # Assume no GST if not specified
                
        # Process Domestic Style (Separated Lists)
        if hasattr(result, 'cogs_breakdown'):
            for item in result.cogs_breakdown:
                code = item.product_code
                if code not in consolidated:
                    consolidated[code] = {'description': item.description.replace(' (Cost)', ''), 'cost_amount': Decimal('0'), 'sell_amount': Decimal('0'), 'sell_incl_gst': Decimal('0'), 'bucket': 'origin_charges', 'agent_name': getattr(item, 'agent_name', None)} # Domestic simplified
                consolidated[code]['cost_amount'] += item.amount

            for item in result.sell_breakdown:
                code = item.product_code
                if code not in consolidated:
                    consolidated[code] = {'description': item.description, 'cost_amount': Decimal('0'), 'sell_amount': Decimal('0'), 'sell_incl_gst': Decimal('0'), 'bucket': 'origin_charges', 'agent_name': None}
                consolidated[code]['sell_amount'] += item.amount
                
                # Domestic GST Logic (10%)
                gst = item.amount * Decimal('0.10')
                consolidated[code]['sell_incl_gst'] += (item.amount + gst)

        # Prefetch ServiceComponents to avoid N+1 and handle missing gracefully
        component_map = {
            sc.code: sc for sc in ServiceComponent.objects.filter(code__in=list(consolidated.keys()))
        }
        
        # 2. Convert to CalculatedChargeLine objects
        for code, data in consolidated.items():
            sc = component_map.get(code)
            if not sc:
                logger.warning("ServiceComponent missing for code %s; skipping line creation", code)
                continue
            
            sc_id = sc.id
            sc_desc = sc.description

            # [FIX P1] Handle non-PGK currency from Standard Engine (e.g. Import Prepaid)
            currency = data.get('sell_currency', 'PGK')
            cost_currency = data.get('cost_currency', currency)
            agent_name = data.get('agent_name')
            if isinstance(agent_name, str) and agent_name:
                cost_source = agent_name
            elif agent_name:
                cost_source = str(agent_name)
            else:
                cost_source = 'V4 Engine'
            
            if currency != 'PGK':
                sell_fcy = Decimal(str(data['sell_amount']))
                sell_fcy_incl_gst = Decimal(str(data.get('sell_incl_gst', sell_fcy)))
                cost_fcy = Decimal(str(data['cost_amount']))
                
                fx_sell_rate = self._get_fx_sell_rate(currency, self._get_fx_rates_dict())
                fx_buy_rate = self._get_fx_buy_rate(cost_currency, self._get_fx_rates_dict())
                
                if fx_sell_rate > 0:
                    sell_pgk = sell_fcy * fx_sell_rate
                    sell_pgk_incl_gst = sell_fcy_incl_gst * fx_sell_rate
                else:
                    sell_pgk = sell_fcy
                    sell_pgk_incl_gst = sell_fcy_incl_gst

                if fx_buy_rate > 0:
                    cost_pgk = cost_fcy * fx_buy_rate
                else:
                    cost_pgk = cost_fcy

                lines.append(CalculatedChargeLine(
                    service_component_id=sc_id,
                    service_component_code=code,
                    service_component_desc=data['description'] or sc_desc,
                    leg=data.get('leg', 'MAIN'),
                    cost_pgk=cost_pgk,
                    sell_pgk=sell_pgk,
                    sell_pgk_incl_gst=sell_pgk_incl_gst,
                    sell_fcy=sell_fcy,
                    sell_fcy_incl_gst=sell_fcy_incl_gst,
                    sell_fcy_currency=currency,
                    cost_fcy=cost_fcy,
                    cost_fcy_currency=cost_currency,
                    bucket=data.get('bucket', 'origin_charges'),

                    cost_source=cost_source,  # NEW: Use agent name if available
                    is_rate_missing=data.get('is_rate_missing', False),
                ))
            else:
                if cost_currency != 'PGK':
                    fx_buy_rate = self._get_fx_buy_rate(cost_currency, self._get_fx_rates_dict())
                    cost_pgk = data['cost_amount'] * fx_buy_rate if fx_buy_rate > 0 else data['cost_amount']
                else:
                    cost_pgk = data['cost_amount']
                lines.append(CalculatedChargeLine(
                    service_component_id=sc_id,
                    service_component_code=code,
                    service_component_desc=data['description'] or sc_desc,
                    leg=data.get('leg', 'MAIN'),
                    cost_pgk=cost_pgk,
                    sell_pgk=data['sell_amount'],
                    sell_pgk_incl_gst=data.get('sell_incl_gst', data['sell_amount']),
                    sell_fcy=data['sell_amount'],
                    sell_fcy_incl_gst=data.get('sell_incl_gst', data['sell_amount']),
                    sell_fcy_currency='PGK',
                    bucket=data.get('bucket', 'origin_charges'),
                    cost_source=cost_source,  # NEW: Use agent name if available
                    is_rate_missing=data.get('is_rate_missing', False),
                ))

        return lines

    def get_output_currency(self):
        """
        Determine the output currency for the quote based on payment terms.
        
        Rules:
        - Import Prepaid: Quote in origin currency (FCY - customer pays overseas)
        - Import Collect: Quote in PGK (customer pays in PNG)
        - Export Prepaid: Quote in PGK (customer pays in PNG)
        - Export Collect: Quote in destination currency (FCY - customer pays overseas)
        - Domestic: Always PGK
        """
        shipment = self.quote_input.shipment
        
        if shipment.shipment_type == 'IMPORT':
            if shipment.payment_term == 'PREPAID':
                # Import Prepaid: Customer pays shipper overseas -> quote in origin FCY
                origin_ccy = None
                if shipment.origin_location:
                    origin_ccy = getattr(shipment.origin_location, 'currency_code', None)
                return origin_ccy or self.quote_input.output_currency or 'AUD'
            # Import Collect: Customer pays in PNG -> PGK
            return 'PGK'
        
        elif shipment.shipment_type == 'EXPORT':
            if shipment.payment_term == 'COLLECT':
                # Export Collect: Customer (consignee) pays overseas -> quote in dest FCY
                dest_ccy = None
                if shipment.destination_location:
                    dest_ccy = getattr(shipment.destination_location, 'currency_code', None)
                return dest_ccy or self.quote_input.output_currency or 'AUD'
            # Export Prepaid: Customer pays in PNG -> PGK
            return 'PGK'
        
        # Domestic: Always PGK
        return self.quote_input.output_currency or 'PGK'

    def _get_fx_rates_dict(self) -> dict:
        if not self.fx_snapshot:
            return {}
        rates = self.fx_snapshot.rates
        if isinstance(rates, str):
            try:
                return json.loads(rates)
            except json.JSONDecodeError:
                logger.warning("Invalid FX rates JSON; falling back to empty rates.")
                return {}
        return rates or {}

    def _get_fx_buy_rate(self, currency: str, rates: dict) -> Decimal:
        if currency == 'PGK':
            return Decimal('1')
        info = rates.get(currency, {})
        if info and info.get('tt_buy'):
            return Decimal(str(info['tt_buy']))
        logger.warning("No FX BUY rate found for %s; using 1.0", currency)
        return Decimal('1')

    def _get_fx_sell_rate(self, currency: str, rates: dict) -> Decimal:
        if currency == 'PGK':
            return Decimal('1')
        info = rates.get(currency, {})
        if info and info.get('tt_sell'):
            return Decimal(str(info['tt_sell']))
        logger.warning("No FX SELL rate found for %s; using 1.0", currency)
        return Decimal('1')

    def _calculate_chargeable_weight(self) -> Decimal:
        total_actual = Decimal('0')
        total_volumetric = Decimal('0')
        pieces = getattr(self.quote_input.shipment, 'pieces', []) or []
        for piece in pieces:
            piece_count = Decimal(str(piece.pieces))
            gross_weight = Decimal(str(piece.gross_weight_kg))
            total_actual += piece_count * gross_weight
            if piece.length_cm and piece.width_cm and piece.height_cm:
                vol = (Decimal(str(piece.length_cm)) * Decimal(str(piece.width_cm)) * Decimal(str(piece.height_cm))) / Decimal('6000')
                total_volumetric += piece_count * vol
        return max(total_actual, total_volumetric)

    def _calculate_totals(self, lines: List[CalculatedChargeLine]) -> QuoteCharges:
        total_cost = sum(l.cost_pgk for l in lines)
        total_sell = sum(l.sell_pgk for l in lines)
        total_gst = sum(l.sell_pgk_incl_gst - l.sell_pgk for l in lines)
        total_sell_pgk_incl_gst = total_sell + total_gst

        fx_rates = self._get_fx_rates_dict()
        output_currency = self.quote_input.output_currency or 'PGK'
        output_fx_sell = self._get_fx_sell_rate(output_currency, fx_rates)

        if output_currency == 'PGK' or output_fx_sell <= 0:
            total_sell_fcy = total_sell
            total_sell_fcy_incl_gst = total_sell_pgk_incl_gst
        else:
            total_sell_fcy = total_sell / output_fx_sell
            total_sell_fcy_incl_gst = total_sell_pgk_incl_gst / output_fx_sell
        
        totals = CalculatedTotals(
            total_cost_pgk=total_cost,
            total_sell_pgk=total_sell,
            total_sell_pgk_incl_gst=total_sell_pgk_incl_gst,
            total_sell_fcy=total_sell_fcy,
            total_sell_fcy_incl_gst=total_sell_fcy_incl_gst,
            total_sell_fcy_currency=output_currency,
            has_missing_rates=any(l.is_rate_missing for l in lines)
        )
        return QuoteCharges(lines=lines, totals=totals)

    def _merge_charge_lines(
        self, 
        standard_lines: List[CalculatedChargeLine], 
        spot_lines: List[CalculatedChargeLine]
    ) -> List[CalculatedChargeLine]:
        """
        [FIX P2] Domestic Logic: Append strategy for Domestic to preserve origin/freight.
        """
        is_domestic = (self.quote_input.shipment.shipment_type == 'DOMESTIC')
        if not spot_lines:
            return standard_lines
            
        if is_domestic:
            final_lines = list(standard_lines)
            final_lines.extend(spot_lines)
            return final_lines

        spot_buckets = {l.bucket for l in spot_lines}
        final_lines = [l for l in standard_lines if l.bucket not in spot_buckets]
        final_lines.extend(spot_lines)
        return final_lines

    def _calculate_spot_lines(self) -> List[CalculatedChargeLine]:
        """
        Calculate charges using SPOT Pricing Envelope.
        Returns list of CalculatedChargeLine (no totals).
        """
        # from quotes.models import SpotPricingEnvelopeDB
        from quotes.spot_models import SpotPricingEnvelopeDB
        from quotes.spot_services import SpotEnvelopeService
        from quotes.spot_schemas import (
            SpotPricingEnvelope,
            SPEShipmentContext,
            SPEChargeLine,
            SPEConditions,
            SPEAcknowledgement,
            SPEManagerApproval,
            SPEStatus,
        )
        
        # 1. Load SPE from database
        try:
            spe_db = SpotPricingEnvelopeDB.objects.prefetch_related(
                'charge_lines', 'acknowledgement', 'manager_approval'
            ).get(id=self.spot_envelope_id)
        except SpotPricingEnvelopeDB.DoesNotExist:
            raise ValueError(f"SPOT Pricing Envelope not found: {self.spot_envelope_id}")
        
        # Verify context integrity
        if not spe_db.verify_context_integrity():
            raise ValueError(
                "SPOT Pricing Envelope integrity check failed. "
                "Shipment context has been modified."
            )
        
        # 2. Reconstruct Pydantic SPE for validation
        ack = None
        if hasattr(spe_db, 'acknowledgement') and spe_db.acknowledgement:
            ack_db = spe_db.acknowledgement
            ack = SPEAcknowledgement(
                acknowledged_by_user_id=str(ack_db.acknowledged_by_id) if ack_db.acknowledged_by_id else "",
                acknowledged_at=ack_db.acknowledged_at,
                statement=ack_db.statement,
            )
        
        mgr = None
        if hasattr(spe_db, 'manager_approval') and spe_db.manager_approval:
            mgr_db = spe_db.manager_approval
            mgr = SPEManagerApproval(
                approved=mgr_db.approved,
                manager_user_id=str(mgr_db.manager_id) if mgr_db.manager_id else "",
                decision_at=mgr_db.decision_at,
                comment=mgr_db.comment,
            )
        
        charges = []
        for cl in spe_db.charge_lines.all():
            charges.append(SPEChargeLine(
                code=cl.code,
                description=cl.description,
                amount=float(cl.amount),
                currency=cl.currency,
                unit=cl.unit,
                bucket=cl.bucket,
                is_primary_cost=cl.is_primary_cost,
                conditional=cl.conditional,
                source_reference=cl.source_reference,
                entered_by_user_id=str(cl.entered_by_id) if cl.entered_by_id else "",
                entered_at=cl.entered_at,
                min_charge=float(cl.min_charge) if cl.min_charge is not None else None,
            ))
        
        ctx_json = spe_db.shipment_context_json
        ctx = SPEShipmentContext(
            origin_country=ctx_json.get('origin_country', 'OTHER'),
            destination_country=ctx_json.get('destination_country', 'OTHER'),
            origin_code=ctx_json.get('origin_code', 'XXX'),
            destination_code=ctx_json.get('destination_code', 'XXX'),
            commodity=ctx_json.get('commodity', 'GCR'),
            total_weight_kg=ctx_json.get('total_weight_kg', 0),
            pieces=ctx_json.get('pieces', 1),
            service_scope=str(ctx_json.get('service_scope', 'p2p')).lower(),
        )
        
        cond_json = spe_db.conditions_json or {}
        conditions = SPEConditions(
            space_not_confirmed=cond_json.get('space_not_confirmed', True),
            airline_acceptance_not_confirmed=cond_json.get('airline_acceptance_not_confirmed', True),
            rate_validity_hours=cond_json.get('rate_validity_hours', 72),
            conditional_charges_present=cond_json.get('conditional_charges_present', False),
            notes=cond_json.get('notes'),
        )

        validation_charges = list(charges)
        if validation_charges:
            has_airfreight = any(c.bucket == 'airfreight' for c in validation_charges)
            if not has_airfreight:
                primary_count = sum(
                    1 for c in validation_charges
                    if c.is_primary_cost or c.code == "AIRFREIGHT_SPOT"
                )
                placeholder_code = "AIRFREIGHT_SPOT" if primary_count == 0 else "AIRFREIGHT_PLACEHOLDER"
                validation_charges.append(SPEChargeLine(
                    code=placeholder_code,
                    description="Airfreight placeholder",
                    amount=1.0,
                    currency="PGK",
                    unit="flat",
                    bucket="airfreight",
                    is_primary_cost=(primary_count == 0),
                    conditional=True,
                    source_reference="system",
                    entered_by_user_id="system",
                    entered_at=datetime.now(),
                ))

        spe = SpotPricingEnvelope(
            id=str(spe_db.id),
            status=SPEStatus(spe_db.status),
            shipment=ctx,
            charges=validation_charges,
            conditions=conditions,
            acknowledgement=ack,
            manager_approval=mgr,
            spot_trigger_reason_code=spe_db.spot_trigger_reason_code,
            spot_trigger_reason_text=spe_db.spot_trigger_reason_text,
            created_by_user_id=str(spe_db.created_by_id) if spe_db.created_by_id else "",
            created_at=spe_db.created_at,
            expires_at=spe_db.expires_at,
        )
        
        # 3. Validate SPE is ready for pricing
        is_valid, error = SpotEnvelopeService.validate_for_pricing(spe)
        if not is_valid:
            raise ValueError(f"SPOT Pricing Envelope not valid for pricing: {error}")
        
        # 4. Convert SPE charges to V3 CalculatedChargeLines
        lines: List[CalculatedChargeLine] = []
        
        fx_rates = self._get_fx_rates_dict()
        output_currency = self.quote_input.output_currency or 'PGK'
        output_fx_sell = self._get_fx_sell_rate(output_currency, fx_rates)
        chargeable_weight = self._calculate_chargeable_weight()

        # Get margin from policy
        margin_pct = Decimal('0.15')  # Default 15%
        if self.policy and self.policy.margin_pct is not None:
            margin_pct = Decimal(str(self.policy.margin_pct))
        
        codes = [c.code for c in charges]
        component_map = {
            sc.code: sc for sc in ServiceComponent.objects.filter(code__in=codes)
        }
        
        for charge in charges:
            # [FIX] Handle conditional/informational charges
            # If conditional, we strip the value to prevent it affecting totals, 
            # and mark it as informational.
            is_info = charge.conditional
            
            # Determine CAF pct
            caf_pct = Decimal("0")
            if self.policy:
                shipment_type = self.quote_input.shipment.shipment_type
                if shipment_type == 'IMPORT':
                    caf_pct = Decimal(str(self.policy.caf_import_pct))
                elif shipment_type == 'EXPORT':
                    caf_pct = Decimal(str(self.policy.caf_export_pct))

            # Apply CAF to FX Rate (User Request)
            fx_buy = self._get_fx_buy_rate(charge.currency, fx_rates)
            fx_buy_adjusted = fx_buy * (Decimal('1') + caf_pct)
            
            # Calculate Base Cost in FCY
            # Handle 'per_kg' OR 'min_or_per_kg' using min_charge if present
            cost_fcy_base = Decimal("0")
            
            # Clean cost_fcy from amount
            unit_rate = Decimal(str(charge.amount))
            if is_info:
                unit_rate = Decimal("0")
                
            if charge.unit == 'per_kg' or charge.unit == 'min_or_per_kg':
                base_calc = unit_rate * chargeable_weight
                min_val = Decimal(str(charge.min_charge)) if charge.min_charge is not None else Decimal("0")
                if is_info: 
                    min_val = Decimal("0")
                cost_fcy = max(base_calc, min_val)
            elif charge.unit == 'percentage':
                # Existing logic
                logger.warning(f"Percentage charge '{charge.code}' skipped. Setting cost to 0.")
                cost_fcy = Decimal("0")
            else:
                # Flat or other
                cost_fcy = unit_rate
                
            # Convert to PGK using Adjusted FX
            cost_pgk = cost_fcy * fx_buy_adjusted
            
            # Apply margin for sell price
            sell_pgk = cost_pgk * (Decimal('1') + margin_pct)
            
            # [FIX] Apply Tax Policy (GST)
            # We map the SPOT bucket/info to the attributes expected by apply_gst_policy
            from quotes.tax_policy import apply_gst_policy
            
            # Define minimal mocks to satisfy the policy interface
            class TaxLocation:
                def __init__(self, cc): self.country_code = cc
            
            class TaxQuotation:
                def __init__(self, st): self.service_type = st
                
            class TaxVersion:
                def __init__(self, origin_cc, dest_cc, svc_type, snap):
                    self.origin = TaxLocation(origin_cc)
                    self.destination = TaxLocation(dest_cc)
                    self.quotation = TaxQuotation(svc_type)
                    self.policy_snapshot = snap
            
            class TaxCharge:
                def __init__(self, code, stage):
                    self.code = code
                    self.stage = stage
                    self.is_taxable = False
                    self.gst_percentage = 0
            
            # Prepare context
            s = self.quote_input.shipment
            origin_cc = s.origin_location.country_code if s.origin_location else 'PG'
            dest_cc = s.destination_location.country_code if s.destination_location else 'PG'
            # Map shipment_type to service_type (IMPORT/EXPORT/DOMESTIC)
            svc_type = s.shipment_type
            
            policy_snap = {} # Could populate export_evidence if available
            
            version_mock = TaxVersion(origin_cc, dest_cc, svc_type, policy_snap)
            
            # Map charge to stage
            stage = "ORIGIN"
            if charge.bucket == 'destination_charges':
                stage = "DESTINATION"
            elif charge.bucket == 'airfreight':
                stage = "AIR"
            
            charge_mock = TaxCharge(charge.code, stage)
            
            # Apply Policy
            apply_gst_policy(version_mock, charge_mock)
            
            # Calculate GST
            gst_rate = Decimal(str(charge_mock.gst_percentage)) / Decimal('100')
            gst = sell_pgk * gst_rate
            sell_incl_gst = sell_pgk + gst

            if output_currency == 'PGK' or output_fx_sell <= 0:
                sell_fcy = sell_pgk
                sell_fcy_incl_gst = sell_incl_gst
            else:
                sell_fcy = sell_pgk / output_fx_sell
                sell_fcy_incl_gst = sell_incl_gst / output_fx_sell
            
            # Get ServiceComponent if exists
            sc = component_map.get(charge.code)
            
            # [FIX] Fallback for dynamic SPOT charges not in DB (e.g. agent ad-hoc charges)
            if not sc:
                if charge.bucket == 'origin_charges':
                    sc = ServiceComponent.objects.filter(code='SPOT_ORIGIN').first()
                elif charge.bucket == 'destination_charges':
                    sc = ServiceComponent.objects.filter(code='SPOT_DEST').first()
                elif charge.bucket == 'airfreight':
                     sc = ServiceComponent.objects.filter(code='SPOT_FREIGHT').first()

            if not sc:
                sc = ServiceComponent.objects.filter(code='SPOT_CHARGE').first()
            if not sc:
                sc = ServiceComponent.objects.filter(code__in=['MISC', 'OTHER', 'GENERIC']).first()
            if not sc:
                # Last resort Fallback 
                pass
            
            # If still no SC, we have a problem because CalculatedChargeLine needs ID.
            # We assume database seeding has 'SPOT_CHARGE' or similar.
            sc_id = sc.id if sc else uuid.uuid4() # Danger but ensures UUID
            sc_desc = sc.description if sc else charge.description
            
            lines.append(CalculatedChargeLine(
                service_component_id=sc_id,
                service_component_code=charge.code,
                service_component_desc=charge.description or sc_desc, # Use charge desc from SPE preferentially
                leg=sc.leg if sc else 'MAIN',
                cost_pgk=cost_pgk,
                sell_pgk=sell_pgk,
                sell_pgk_incl_gst=sell_incl_gst,
                sell_fcy=sell_fcy,
                sell_fcy_incl_gst=sell_fcy_incl_gst,
                cost_source=charge.source_reference or 'SPOT Envelope',  # NEW: Map Source Ref
                cost_source_description=charge.description, # Ensure desc is passed
                cost_fcy=cost_fcy,
                cost_fcy_currency=charge.currency,
                sell_fcy_currency=output_currency,
                bucket=charge.bucket, # Ensure bucket is passed
                is_informational=is_info,
                is_rate_missing=False,
            ))
            
        return lines
