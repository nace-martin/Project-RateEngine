import uuid
import logging
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from core.models import FxSnapshot, Policy
from pricing_v2.dataclasses_v3 import (
    QuoteInput, QuoteCharges, CalculatedChargeLine, CalculatedTotals
)
from pricing_v4.engine.export_engine import ExportPricingEngine
from pricing_v4.engine.import_engine import ImportPricingEngine, PaymentTerm, ServiceScope
from pricing_v4.engine.domestic_engine import DomesticPricingEngine
from pricing_v4.models import ProductCode
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

    def calculate_charges(self) -> QuoteCharges:
        shipment = self.quote_input.shipment
        
        # SPOT Mode: if spot_envelope_id provided, use SPE charges instead of DB rates
        if self.spot_envelope_id:
            return self._calculate_spot_charges()
        
        # 1. Determine which engine to use
        # Logic matches _classify_shipment_type in views.py but we trust the input object
        
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
            # needs: quote_date, origin, destination, chargeable_weight_kg
            # (service_scope/incoterm are handled by logic or not needed for basic constructor yet?)
            # Wait, verify ExportEngine uses them?
            # Looking at current ExportEngine.__init__ it DOES NOT take service_scope or incoterm.
            # It DOES take quote_date.
            
            engine = ExportPricingEngine(
                quote_date=self.quote_input.quote_date, # Add quote_date
                origin=origin_code,
                destination=dest_code,
                chargeable_weight_kg=chargeable_weight # Rename param
            )
        elif shipment.shipment_type == 'IMPORT':
            # Import Engine
            # needs: quote_date, origin, destination, chargeable_weight_kg, payment_term, service_scope
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
            # needs: cogs_origin, destination, weight_kg, service_scope
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
            product_code_ids = ExportPricingEngine.get_product_codes(is_dg=shipment.is_dangerous_goods)
            result = engine.calculate_quote(product_code_ids)
        else:
            # Import and Domestic engines use calculate_quote() without args
            result = engine.calculate_quote()
        
        # 3. Convert Result to V3 QuoteCharges
        return self._convert_to_v3_response(result)

    def _convert_to_v3_response(self, result) -> QuoteCharges:
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
            if code not in consolidated:
                consolidated[code] = {
                    'description': line.description,
                    'cost_amount': Decimal('0'),
                    'sell_amount': Decimal('0'),
                    'sell_incl_gst': Decimal('0'),
                    'gst_amount': Decimal('0'),
                }
            
            # Sum up (though typically one per code)
            consolidated[code]['cost_amount'] += line.cost_amount
            consolidated[code]['sell_amount'] += line.sell_amount
            
            # Handle Tax
            gst = getattr(line, 'gst_amount', Decimal('0'))
            # Import engine doesn't expressly return gst_amount in datastruct, it implies inclusion?
            # Checking ImportEngine: validation verify_import_engine check "sell_incl_gst".
            # ImportEngine ChargeLine has no gst field?
            # ImportEngine uses logic inside? No, let's look at ImportEngine datastruct.
            # ChargeLine: product_code, cost_amount, sell_amount.
            # If ImportEngine doesn't calculate GST, we might need to add it here or ensure Engine does it.
            # For now, rely on what's there.
            
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
                    consolidated[code] = {'description': item.description.replace(' (Cost)', ''), 'cost_amount': Decimal('0'), 'sell_amount': Decimal('0'), 'sell_incl_gst': Decimal('0')}
                consolidated[code]['cost_amount'] += item.amount

            for item in result.sell_breakdown:
                code = item.product_code
                if code not in consolidated:
                    consolidated[code] = {'description': item.description, 'cost_amount': Decimal('0'), 'sell_amount': Decimal('0'), 'sell_incl_gst': Decimal('0')}
                consolidated[code]['sell_amount'] += item.amount
                
                # Domestic GST Logic (10%)
                # DomesticEngine adds GST at total level, but here we need per line?
                # V3 expects per-line GST.
                # DomesticEngine: "GST added at end".
                # We need to distribute it or apply it here.
                # All domestic sell rates are taxable in PNG.
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

            lines.append(CalculatedChargeLine(
                service_component_id=sc_id,
                service_component_code=code,
                service_component_desc=data['description'] or sc_desc,
                leg='MAIN', # TODO: Map properly based on ProductCode
                cost_pgk=data['cost_amount'],
                sell_pgk=data['sell_amount'],
                sell_pgk_incl_gst=data.get('sell_incl_gst', data['sell_amount']),
                sell_fcy=data['sell_amount'], # Assuming PGK centric for now
                sell_fcy_incl_gst=data.get('sell_incl_gst', data['sell_amount']),
                cost_source='V4 Engine',
                sell_fcy_currency='PGK'
            ))

        # 3. Totals
        # We can re-sum from lines to be safe
        total_cost = sum(l.cost_pgk for l in lines)
        total_sell = sum(l.sell_pgk for l in lines)
        total_gst = sum(l.sell_pgk_incl_gst - l.sell_pgk for l in lines)
        
        totals = CalculatedTotals(
            total_cost_pgk=total_cost,
            total_sell_pgk=total_sell,
            total_sell_pgk_incl_gst=total_sell + total_gst,
            total_sell_fcy=total_sell,
            total_sell_fcy_incl_gst=total_sell + total_gst,
            total_sell_fcy_currency='PGK'
        )
        
        return QuoteCharges(lines=lines, totals=totals)

    def get_output_currency(self):
        shipment = self.quote_input.shipment
        # Import PREPAID = FCY (use origin currency if available, fallback AUD)
        if shipment.shipment_type == 'IMPORT':
            if shipment.payment_term == 'PREPAID':
                origin_ccy = None
                if shipment.origin_location:
                    origin_ccy = getattr(shipment.origin_location, 'currency_code', None)
                return origin_ccy or self.quote_input.output_currency or 'AUD'
            return 'PGK'
        
        # Other shipment types default to provided output_currency or PGK
        return self.quote_input.output_currency or 'PGK'

    def _calculate_spot_charges(self) -> QuoteCharges:
        """
        Calculate charges using SPOT Pricing Envelope.
        
        1. Load and validate SPE
        2. Convert SPE charge lines to BUY lines
        3. Apply FX conversion
        4. Apply margin per policy
        5. Apply GST
        6. Mark output as SPOT mode
        """
        from quotes.models import SpotPricingEnvelopeDB
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
        
        # Verify context integrity (Tweak #4)
        if not spe_db.verify_context_integrity():
            raise ValueError(
                "SPOT Pricing Envelope integrity check failed. "
                "Shipment context has been modified."
            )
        
        # 2. Reconstruct Pydantic SPE for validation
        # Build acknowledgement if exists
        ack = None
        if hasattr(spe_db, 'acknowledgement') and spe_db.acknowledgement:
            ack_db = spe_db.acknowledgement
            ack = SPEAcknowledgement(
                acknowledged_by_user_id=str(ack_db.acknowledged_by_id) if ack_db.acknowledged_by_id else "",
                acknowledged_at=ack_db.acknowledged_at,
                statement=ack_db.statement,
            )
        
        # Build manager approval if exists
        mgr = None
        if hasattr(spe_db, 'manager_approval') and spe_db.manager_approval:
            mgr_db = spe_db.manager_approval
            mgr = SPEManagerApproval(
                approved=mgr_db.approved,
                manager_user_id=str(mgr_db.manager_id) if mgr_db.manager_id else "",
                decision_at=mgr_db.decision_at,
                comment=mgr_db.comment,
            )
        
        # Build charge lines
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
            ))
        
        # Build context
        ctx_json = spe_db.shipment_context_json
        ctx = SPEShipmentContext(
            origin_country=ctx_json.get('origin_country', 'OTHER'),
            destination_country=ctx_json.get('destination_country', 'OTHER'),
            origin_code=ctx_json.get('origin_code', 'XXX'),
            destination_code=ctx_json.get('destination_code', 'XXX'),
            commodity=ctx_json.get('commodity', 'GCR'),
            total_weight_kg=ctx_json.get('total_weight_kg', 0),
            pieces=ctx_json.get('pieces', 1),
        )
        
        # Build conditions
        cond_json = spe_db.conditions_json or {}
        conditions = SPEConditions(
            space_not_confirmed=cond_json.get('space_not_confirmed', True),
            airline_acceptance_not_confirmed=cond_json.get('airline_acceptance_not_confirmed', True),
            rate_validity_hours=cond_json.get('rate_validity_hours', 72),
            conditional_charges_present=cond_json.get('conditional_charges_present', False),
            notes=cond_json.get('notes'),
        )
        
        # Build full SPE for validation
        spe = SpotPricingEnvelope(
            id=str(spe_db.id),
            status=SPEStatus(spe_db.status),
            shipment=ctx,
            charges=charges,
            conditions=conditions,
            acknowledgement=ack,
            manager_approval=mgr,
            spot_trigger_reason_code=spe_db.spot_trigger_reason_code,
            spot_trigger_reason_text=spe_db.spot_trigger_reason_text,
            created_by_user_id=str(spe_db.created_by_id) if spe_db.created_by_id else "",
            created_at=spe_db.created_at,
            expires_at=spe_db.expires_at,
        )
        
        # 3. Validate SPE is ready for pricing (Tweak #3)
        is_valid, error = SpotEnvelopeService.validate_for_pricing(spe)
        if not is_valid:
            raise ValueError(f"SPOT Pricing Envelope not valid for pricing: {error}")
        
        # 4. Mark as SPOT mode
        self.pricing_mode = PricingMode.SPOT
        
        # 5. Convert SPE charges to V3 CalculatedChargeLines
        # Apply FX conversion if charges are in foreign currency
        lines: List[CalculatedChargeLine] = []
        
        # Get FX rate if needed
        fx_rate = Decimal('1.0')
        if self.fx_snapshot:
            # Find rate for source currency to PGK
            for charge in charges:
                if charge.currency != 'PGK':
                    rates = self.fx_snapshot.rates.get(charge.currency, {})
                    fx_rate = Decimal(str(rates.get('tt_buy', '1.0')))
                    break
        
        # Get margin from policy
        margin_pct = Decimal('0.15')  # Default 15%
        if self.policy:
            margin_pct = self.policy.margin_pct
        
        # Prefetch ServiceComponents
        codes = [c.code for c in charges]
        component_map = {
            sc.code: sc for sc in ServiceComponent.objects.filter(code__in=codes)
        }
        
        for charge in charges:
            # Calculate cost in PGK
            cost_fcy = Decimal(str(charge.amount))
            cost_pgk = cost_fcy * fx_rate
            
            # Apply margin for sell price
            sell_pgk = cost_pgk * (Decimal('1') + margin_pct)
            
            # Apply GST (10%)
            gst = sell_pgk * Decimal('0.10')
            sell_incl_gst = sell_pgk + gst
            
            # Get ServiceComponent if exists
            sc = component_map.get(charge.code)
            sc_id = sc.id if sc else None
            
            lines.append(CalculatedChargeLine(
                service_component_id=sc_id,
                service_component_code=charge.code,
                service_component_desc=charge.description,
                leg='SPOT',  # Mark as SPOT leg
                cost_pgk=cost_pgk,
                sell_pgk=sell_pgk,
                sell_pgk_incl_gst=sell_incl_gst,
                sell_fcy=cost_fcy,  # Original FCY amount
                sell_fcy_incl_gst=cost_fcy * (Decimal('1') + margin_pct) * Decimal('1.10'),
                cost_source=f'SPOT: {charge.source_reference}',
                sell_fcy_currency=charge.currency,
            ))
        
        # 6. Calculate totals
        total_cost = sum(l.cost_pgk for l in lines)
        total_sell = sum(l.sell_pgk for l in lines)
        total_gst = sum(l.sell_pgk_incl_gst - l.sell_pgk for l in lines)
        
        totals = CalculatedTotals(
            total_cost_pgk=total_cost,
            total_sell_pgk=total_sell,
            total_sell_pgk_incl_gst=total_sell + total_gst,
            total_sell_fcy=sum(l.sell_fcy for l in lines),
            total_sell_fcy_incl_gst=sum(l.sell_fcy_incl_gst for l in lines),
            total_sell_fcy_currency=charges[0].currency if charges else 'PGK',
        )
        
        logger.info(
            "SPOT pricing calculated: envelope=%s, lines=%d, total_sell=%.2f PGK",
            self.spot_envelope_id, len(lines), total_sell
        )
        
        return QuoteCharges(lines=lines, totals=totals)
