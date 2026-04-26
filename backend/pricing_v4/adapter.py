import uuid
import json
import logging
import re
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List, Optional
from uuid import UUID

from core.commodity import DEFAULT_COMMODITY_CODE
from core.models import FxSnapshot, Policy
from django.db import models
from core.dataclasses import (
    QuoteInput, QuoteCharges, CalculatedChargeLine, CalculatedTotals
)
from core.charge_rules import evaluate_charge_rule, normalize_charge_rule
from pricing_v4.engine.export_engine import ExportPricingEngine, PaymentTerm as ExportPaymentTerm
from pricing_v4.engine.import_engine import ImportPricingEngine, PaymentTerm, ServiceScope
from pricing_v4.engine.domestic_engine import DomesticPricingEngine
from pricing_v4.models import ProductCode, CustomerDiscount
from services.models import ServiceComponent
from quotes.completeness import evaluate_from_lines
from quotes.currency_rules import determine_quote_currency
from quotes.quote_result_contract import basis_for_unit, quantity_for_unit

logger = logging.getLogger(__name__)

DOMESTIC_AIRFREIGHT_CODES = {
    'DOM-FRT-AIR',
    'DOM-EXPRESS',
    'DOM-VALUABLE',
    'DOM-LIVE-ANIMAL',
    'DOM-OVERSIZE',
}

GENERIC_SPOT_DESCRIPTIONS = {
    "SPOT ORIGIN CHARGE",
    "SPOT FREIGHT CHARGE",
    "SPOT DESTINATION CHARGE",
    "SPOT CHARGE",
}


def _is_generic_spot_description(value: Optional[str]) -> bool:
    return str(value or "").strip().upper() in GENERIC_SPOT_DESCRIPTIONS


def _spot_charge_display_description(charge_line) -> str:
    product_code = getattr(charge_line, "effective_resolved_product_code", None)
    if product_code:
        return product_code.description or product_code.code

    for candidate in (
        getattr(charge_line, "source_label", None),
        getattr(charge_line, "description", None),
        getattr(charge_line, "normalized_label", None),
    ):
        value = str(candidate or "").strip()
        if value and not _is_generic_spot_description(value):
            return value

    return str(getattr(charge_line, "description", "") or "").strip() or "Spot Charge"


def _spot_charge_display_code(charge_line) -> str:
    product_code = getattr(charge_line, "effective_resolved_product_code", None)
    if product_code:
        return product_code.code
    return getattr(charge_line, "code", None) or "SPOT_CHARGE"


class PricingMode:
    """Pricing mode constants."""
    NORMAL = "NORMAL"
    SPOT = "SPOT"


def _normalize_station_code(value: Optional[str]) -> str:
    raw = str(value or "").strip().upper()
    if not raw:
        return ""

    match = re.match(r"^([A-Z]{3})(?:\b|\s|-|/)", raw)
    if match:
        return match.group(1)

    if re.fullmatch(r"[A-Z]{3}", raw):
        return raw

    return raw


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
        self.pricing_mode = PricingMode.SPOT if spot_envelope_id else PricingMode.NORMAL
        self._source_result_context: dict[str, object] = {}
        self._audit_warnings: list[str] = []
        self._audit_metadata: dict[str, object] = {}
        
        # Fetch Policy and FX just like V3 did, so views can save them to Quote
        try:
            self.policy = Policy.objects.filter(is_active=True).latest('effective_from')
        except Policy.DoesNotExist:
            self.policy = None
            
        try:
            self.fx_snapshot = FxSnapshot.objects.latest('as_of_timestamp')
        except FxSnapshot.DoesNotExist:
            self.fx_snapshot = None

    def _reset_audit_capture(self) -> None:
        self._source_result_context = {}
        self._audit_warnings = []
        self._audit_metadata = {}

    def _dedupe_strings(self, values: List[str]) -> List[str]:
        seen = set()
        ordered: List[str] = []
        for value in values:
            normalized = str(value or "").strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            ordered.append(normalized)
        return ordered

    def _record_fx_fallback(self, direction: str, currency: str) -> None:
        curr = str(currency or "").upper() or "UNKNOWN"
        warning = f"FX {direction.upper()} rate missing for {curr}; used 1.0 fallback."
        self._audit_warnings.append(warning)
        self._audit_metadata.setdefault("fx_fallbacks", [])
        fx_fallbacks = self._audit_metadata["fx_fallbacks"]
        if isinstance(fx_fallbacks, list):
            fx_fallbacks.append(
                {
                    "direction": direction.upper(),
                    "currency": curr,
                    "fallback_rate": "1.0",
                }
            )

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

        fx_rates = self._get_fx_rates_dict()

        def discount_amount_to_pgk(amount: Decimal, currency: Optional[str]) -> Decimal:
            curr = (currency or 'PGK').upper()
            if curr == 'PGK':
                return amount
            fx_sell = self._get_fx_sell_rate(curr, fx_rates)
            if fx_sell <= 0:
                logger.warning("Invalid FX sell rate for discount currency %s; using 1.0", curr)
                fx_sell = Decimal('1')
            return amount * fx_sell
        
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
                    discount_amount_pgk = discount_amount_to_pgk(discount.discount_value, discount.currency)
                    discounted_sell = max(Decimal('0'), original_sell - discount_amount_pgk)
                    
                elif discount.discount_type == CustomerDiscount.TYPE_FIXED_CHARGE:
                    # Replace the entire sell price with fixed charge (normalized to PGK).
                    discounted_sell = discount_amount_to_pgk(discount.discount_value, discount.currency)
                    
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
        self._reset_audit_capture()
        
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
        charges = self._calculate_totals(final_lines)
        source_context = self._source_result_context or {}
        service_notes = source_context.get("service_notes") or charges.totals.notes
        charges.totals.service_notes = str(service_notes) if service_notes else None
        customer_notes = source_context.get("customer_notes")
        charges.totals.customer_notes = str(customer_notes) if customer_notes else None
        internal_notes = source_context.get("internal_notes")
        charges.totals.internal_notes = str(internal_notes) if internal_notes else None
        warnings = list(source_context.get("warnings") or [])
        warnings.extend(self._audit_warnings)
        if charges.totals.notes:
            warnings.append(str(charges.totals.notes))
        charges.totals.warnings = self._dedupe_strings(warnings)
        audit_metadata = {}
        source_audit_metadata = source_context.get("audit_metadata")
        if isinstance(source_audit_metadata, dict):
            audit_metadata.update(source_audit_metadata)
        for key, value in self._audit_metadata.items():
            if key not in audit_metadata:
                audit_metadata[key] = value
                continue
            existing = audit_metadata[key]
            if isinstance(existing, list) and isinstance(value, list):
                audit_metadata[key] = existing + value
            elif isinstance(existing, dict) and isinstance(value, dict):
                merged = dict(existing)
                merged.update(value)
                audit_metadata[key] = merged
            else:
                audit_metadata[key] = value
        charges.totals.audit_metadata = audit_metadata
        return charges

    def _calculate_standard_lines(self) -> List[CalculatedChargeLine]:
        """Run standard V4 pricing engine and return raw charge lines."""
        shipment = self.quote_input.shipment
        commodity_code = getattr(shipment, "commodity_code", DEFAULT_COMMODITY_CODE)
        engine = None
        result = None
        
        # Validate shipment type using the shared RoutingMap (single source of truth)
        # Lazy import to avoid circular dependency (dispatcher.py imports adapter.py)
        from pricing_v4.dispatcher import RoutingMap
        RoutingMap.get_engine_class(shipment.shipment_type)
        
        # Calculate chargeable weight (Max of Actual vs Volumetric)
        chargeable_weight = self._calculate_chargeable_weight()
        
        origin_code = _normalize_station_code(getattr(shipment.origin_location, "code", None))
        dest_code = _normalize_station_code(getattr(shipment.destination_location, "code", None))

        if shipment.shipment_type == 'EXPORT':
            # Export Engine - now supports payment term and FCY conversion
            # Get FX rates from snapshot
            fx_rates = self._get_fx_rates_dict()

            # Convert payment term string to enum and enforce resolved currency rules:
            # - STANDARD mode: country-based rule output (AUD/USD/PGK)
            # - SPOT mode: PGK
            export_payment_term = ExportPaymentTerm(shipment.payment_term) if shipment.payment_term else ExportPaymentTerm.PREPAID
            quote_currency = self.get_output_currency()
            # Keep engine quote currency aligned with resolved output currency.
            # This is critical for SPOT mode where output is forced to PGK.
            destination_currency = quote_currency
            
            # Get TT rates for the quote currency
            fx_info = fx_rates.get(quote_currency, {})
            tt_buy = Decimal(str(fx_info.get('tt_buy', '2.50'))) if fx_info else Decimal('2.50')
            tt_sell = Decimal(str(fx_info.get('tt_sell', '2.78'))) if fx_info else Decimal('2.78')
            
            # Get CAF and margin from policy or use defaults
            caf_rate = None
            margin_rate = None
            if self.policy:
                if self.policy.caf_export_pct is not None:
                    caf_rate = Decimal(str(self.policy.caf_export_pct))
                if self.policy.margin_pct is not None:
                    margin_rate = Decimal(str(self.policy.margin_pct))
            
            engine = ExportPricingEngine(
                quote_date=self.quote_input.quote_date,
                origin=origin_code,
                destination=dest_code,
                chargeable_weight_kg=chargeable_weight,
                payment_term=export_payment_term,
                tt_buy=tt_buy,
                tt_sell=tt_sell,
                caf_rate=caf_rate,
                margin_rate=margin_rate,
                destination_currency=destination_currency,
                preferred_agent_id=self.quote_input.agent_id,
                preferred_carrier_id=self.quote_input.carrier_id,
                buy_currency=self.quote_input.buy_currency,
            )
        elif shipment.shipment_type == 'IMPORT':
            # Import Engine
            # Convert strings to enum values
            payment_term_enum = PaymentTerm(shipment.payment_term)
            service_scope_enum = ServiceScope(shipment.service_scope)
            
            # Prepare FX data
            fx_rates = self._get_fx_rates_dict()
            # PRIORITY: Use the currency already determined by the View/User (Customer Preference)
            # If not set, fallback to adapter logic
            quote_currency = self.get_output_currency()
            
            fx_info = fx_rates.get(quote_currency, {})
            # Use defaults if missing (same as Export)
            tt_buy = Decimal(str(fx_info.get('tt_buy', '0.35'))) if fx_info else Decimal('0.35')
            tt_sell = Decimal(str(fx_info.get('tt_sell', '0.36'))) if fx_info else Decimal('0.36')
            
            # Get specific policy overrides if any (reuse Export policy fields or define Import ones?)
            # Assuming shared policy margin/caf for now or defaults in engine
            caf_rate = None
            margin_rate = None
            if self.policy:
                if self.policy.caf_import_pct is not None:
                     caf_rate = Decimal(str(self.policy.caf_import_pct))
                if self.policy.margin_pct is not None:
                     margin_rate = Decimal(str(self.policy.margin_pct))

            engine = ImportPricingEngine(
                quote_date=self.quote_input.quote_date,
                origin=origin_code,
                destination=dest_code,
                chargeable_weight_kg=chargeable_weight,
                payment_term=payment_term_enum,
                service_scope=service_scope_enum,
                tt_buy=tt_buy,
                tt_sell=tt_sell,
                caf_rate=caf_rate,
                margin_rate=margin_rate,
                fx_rates=fx_rates,
                quote_currency=quote_currency,
                preferred_agent_id=self.quote_input.agent_id,
                preferred_carrier_id=self.quote_input.carrier_id,
                buy_currency=self.quote_input.buy_currency,
            )
        elif shipment.shipment_type == 'DOMESTIC':
            # Domestic Engine
            engine = DomesticPricingEngine(
                cogs_origin=origin_code,
                destination=dest_code,
                weight_kg=chargeable_weight,
                service_scope=shipment.service_scope,
                quote_date=self.quote_input.quote_date,
                commodity_code=commodity_code,
                preferred_agent_id=self.quote_input.agent_id,
                preferred_carrier_id=self.quote_input.carrier_id,
                buy_currency=self.quote_input.buy_currency,
            )
        # Note: RoutingMap.get_engine_class() above already validated the
        # shipment_type, so reaching here is impossible. Guard retained for
        # defensive completeness.
        else:
            raise NotImplementedError(f"Unsupported shipment type: {shipment.shipment_type}")
            
        # 2. Run Calculation
        # Export Engine requires product_code_ids; others may not
        if shipment.shipment_type == 'EXPORT':
            product_code_ids = ExportPricingEngine.get_product_codes(
                is_dg=shipment.is_dangerous_goods,
                service_scope=shipment.service_scope,
                commodity_code=commodity_code,
                origin=origin_code,
                destination=dest_code,
                payment_term=shipment.payment_term,
                quote_date=self.quote_input.quote_date,
            )
            result = engine.calculate_quote(
                product_code_ids,
                is_dg=shipment.is_dangerous_goods,
                service_scope=shipment.service_scope,
                commodity_code=commodity_code,
            )
        else:
            # Import and Domestic engines use calculate_quote() without args
            if shipment.shipment_type == 'IMPORT':
                result = engine.calculate_quote(commodity_code=commodity_code)
            else:
                result = engine.calculate_quote()
        
        # 3. Convert Result to V3 QuoteCharges (now returns List[CalculatedChargeLine])
        return self._convert_result_to_lines(result)

    def _convert_result_to_lines(self, result) -> List[CalculatedChargeLine]:
        lines: List[CalculatedChargeLine] = []
        self._source_result_context = {
            "service_notes": getattr(result, "service_notes", None),
            "customer_notes": getattr(result, "customer_notes", None),
            "internal_notes": getattr(result, "internal_notes", None),
            "warnings": list(getattr(result, "warnings", []) or []),
            "audit_metadata": getattr(result, "audit_metadata", {}) or {},
        }
        
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
        if hasattr(result, 'line_items'):
            import_or_export_lines = result.line_items
        elif hasattr(result, 'lines'): # Export
            import_or_export_lines = result.lines
        elif hasattr(result, 'origin_lines'): # Import
            import_or_export_lines = result.origin_lines + result.freight_lines + result.destination_lines
            
        shipment_metrics = {
            "chargeable_weight": self._calculate_chargeable_weight(),
            "pieces": sum(int(getattr(piece, "pieces", 0) or 0) for piece in getattr(self.quote_input.shipment, "pieces", []) or []),
        }

        # Process Import/Export Style (Unified lines)
        for line in import_or_export_lines:
            code = line.product_code
            # Map V4 category to V3 bucket
            # Use the leg from the V4 engine if available
            leg = getattr(line, 'leg', 'MAIN')
            
            # Map V4 category/leg to V3 bucket
            v4_category = getattr(line, 'category', 'HANDLING')
            bucket = 'origin_charges'
            if code == 'EXP-FSC-AIR':
                # Rule: Reclassify Airline Export Fuel Surcharge to Origin Charges
                bucket = 'origin_charges'
                leg = 'ORIGIN'
            elif code == 'IMP-FSC-AIR':
                # Rule: Reclassify Airline Import Fuel Surcharge to Destination Charges
                bucket = 'destination_charges'
                leg = 'DESTINATION'
            elif v4_category == 'FREIGHT' or leg == 'FREIGHT':
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
                    'cost_source': getattr(line, 'cost_source', None),
                    'gst_category': getattr(line, 'gst_category', None),
                    'gst_rate': getattr(line, 'gst_rate', Decimal('0')),
                    'gst_amount': getattr(line, 'gst_amount', Decimal('0')),
                    'agent_name': getattr(line, 'agent_name', None),  # NEW
                    'product_code': getattr(line, 'product_code', None) or code,
                    'component': getattr(line, 'component', None),
                    'basis': getattr(line, 'basis', None),
                    'rule_family': getattr(line, 'rule_family', None),
                    'service_family': getattr(line, 'service_family', None),
                    'unit_type': getattr(line, 'unit_type', None),
                    'quantity': quantity_for_unit(getattr(line, 'unit_type', None), shipment_metrics),
                    'rate': getattr(line, 'rate', None),
                    'rate_source': getattr(line, 'rate_source', None),
                    'canonical_cost_source': getattr(line, 'cost_source', None),
                    'calculation_notes': getattr(line, 'calculation_notes', None),
                    'is_spot_sourced': bool(getattr(line, 'is_spot_sourced', False)),
                    'is_manual_override': bool(getattr(line, 'is_manual_override', False)),
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
        if not hasattr(result, 'line_items') and hasattr(result, 'cogs_breakdown'):
            for item in result.cogs_breakdown:
                code = item.product_code
                bucket = 'airfreight' if code in DOMESTIC_AIRFREIGHT_CODES else 'origin_charges'
                leg = 'MAIN' if bucket == 'airfreight' else 'ORIGIN'
                if code not in consolidated:
                    consolidated[code] = {
                        'description': item.description.replace(' (Cost)', ''),
                        'cost_amount': Decimal('0'),
                        'sell_amount': Decimal('0'),
                        'sell_incl_gst': Decimal('0'),
                        'bucket': bucket,
                        'leg': leg,
                        'agent_name': getattr(item, 'agent_name', None),
                        'product_code': code,
                        'component': 'FREIGHT' if bucket == 'airfreight' else 'ORIGIN_LOCAL',
                        'basis': 'Per KG' if bucket == 'airfreight' else 'Per Shipment',
                        'rule_family': getattr(item, 'rule_family', None),
                        'unit_type': 'KG' if bucket == 'airfreight' else 'SHIPMENT',
                        'quantity': quantity_for_unit('KG' if bucket == 'airfreight' else 'SHIPMENT', shipment_metrics),
                    }  # Domestic simplified
                consolidated[code]['cost_amount'] += item.amount

            for item in result.sell_breakdown:
                code = item.product_code
                bucket = 'airfreight' if code in DOMESTIC_AIRFREIGHT_CODES else 'origin_charges'
                leg = 'MAIN' if bucket == 'airfreight' else 'ORIGIN'
                if code not in consolidated:
                    consolidated[code] = {
                        'description': item.description,
                        'cost_amount': Decimal('0'),
                        'sell_amount': Decimal('0'),
                        'sell_incl_gst': Decimal('0'),
                        'bucket': bucket,
                        'leg': leg,
                        'agent_name': None,
                        'product_code': code,
                        'component': 'FREIGHT' if bucket == 'airfreight' else 'ORIGIN_LOCAL',
                        'basis': 'Per KG' if bucket == 'airfreight' else 'Per Shipment',
                        'rule_family': getattr(item, 'rule_family', None),
                        'unit_type': 'KG' if bucket == 'airfreight' else 'SHIPMENT',
                        'quantity': quantity_for_unit('KG' if bucket == 'airfreight' else 'SHIPMENT', shipment_metrics),
                    }
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
            engine_cost_source = str(data.get('cost_source') or '').strip()
            if engine_cost_source and engine_cost_source != 'N/A':
                cost_source = engine_cost_source
            elif isinstance(agent_name, str) and agent_name:
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
                    sell_pgk = self._convert_fcy_to_pgk(sell_fcy, fx_sell_rate)
                    sell_pgk_incl_gst = self._convert_fcy_to_pgk(sell_fcy_incl_gst, fx_sell_rate)
                else:
                    sell_pgk = sell_fcy
                    sell_pgk_incl_gst = sell_fcy_incl_gst

                if fx_buy_rate > 0:
                    cost_pgk = self._convert_fcy_to_pgk(cost_fcy, fx_buy_rate)
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
                    product_code=data.get('product_code') or code,
                    component=data.get('component'),
                    basis=data.get('basis'),
                    rule_family=data.get('rule_family'),
                    service_family=data.get('service_family'),
                    unit_type=data.get('unit_type'),
                    quantity=data.get('quantity'),
                    rate=data.get('rate'),
                    rate_source=data.get('rate_source'),
                    canonical_cost_source=data.get('canonical_cost_source'),
                    calculation_notes=data.get('calculation_notes'),
                    is_spot_sourced=bool(data.get('is_spot_sourced', False)),
                    is_manual_override=bool(data.get('is_manual_override', False)),
                    cost_source=cost_source,  # NEW: Use agent name if available
                    is_rate_missing=data.get('is_rate_missing', False),
                    # GST Fields
                    gst_category=data.get('gst_category'),
                    gst_rate=data.get('gst_rate', Decimal('0')),
                    gst_amount=(sell_fcy_incl_gst - sell_fcy).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
                ))
            else:
                cost_fcy = None
                cost_fcy_currency = None
                if cost_currency != 'PGK':
                    cost_fcy = data['cost_amount']
                    cost_fcy_currency = cost_currency
                    fx_buy_rate = self._get_fx_buy_rate(cost_currency, self._get_fx_rates_dict())
                    cost_pgk = self._convert_fcy_to_pgk(data['cost_amount'], fx_buy_rate) if fx_buy_rate > 0 else data['cost_amount']
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
                    cost_fcy=cost_fcy,
                    cost_fcy_currency=cost_fcy_currency,
                    bucket=data.get('bucket', 'origin_charges'),
                    product_code=data.get('product_code') or code,
                    component=data.get('component'),
                    basis=data.get('basis'),
                    rule_family=data.get('rule_family'),
                    service_family=data.get('service_family'),
                    unit_type=data.get('unit_type'),
                    quantity=data.get('quantity'),
                    rate=data.get('rate'),
                    rate_source=data.get('rate_source'),
                    canonical_cost_source=data.get('canonical_cost_source'),
                    calculation_notes=data.get('calculation_notes'),
                    is_spot_sourced=bool(data.get('is_spot_sourced', False)),
                    is_manual_override=bool(data.get('is_manual_override', False)),
                    cost_source=cost_source,  # NEW: Use agent name if available
                    is_rate_missing=data.get('is_rate_missing', False),
                    # GST Fields
                    gst_category=data.get('gst_category'),
                    gst_rate=data.get('gst_rate', Decimal('0')),
                    gst_amount=data.get('gst_amount', Decimal('0')),
                ))

        # 3. Apply Prioritized Sorting
        # Priority 1: Customs Clearance
        # Priority 2: Agency Fees
        # Priority 3: Ancillary/Local charges (Documentation, AWB, Handling, Terminal, etc.)
        # Priority 4: Freight/Main
        def sort_priority(line: CalculatedChargeLine):
            code = line.service_component_code.upper()
            
            # Base priority by bucket to keep sections grouped
            # 0: Origin, 1: Freight, 2: Destination
            bucket_map = {'origin_charges': 0, 'airfreight': 100, 'destination_charges': 200}
            base_prio = bucket_map.get(line.bucket, 300)

            # Internal priority within bucket
            item_prio = 50
            if 'CLEAR' in code:
                item_prio = 1
            elif 'AGENCY' in code:
                item_prio = 2
            elif any(k in code for k in ['DOC', 'AWB', 'HANDLING', 'TERMINAL', 'LOADING', 'CARTAGE', 'SCREEN', 'PICKUP', 'FSC-CARTAGE', 'FSC-AIR']):
                item_prio = 10
            elif 'FRT' in code or 'FREIGHT' in code:
                item_prio = 90
                
            return base_prio + item_prio

        lines.sort(key=sort_priority)
        return lines

    def get_output_currency(self):
        """Determine output currency using global shipment/payment-country rules."""
        shipment = self.quote_input.shipment

        origin_country = None
        if shipment.origin_location:
            origin_country = getattr(shipment.origin_location, 'country_code', None)

        destination_country = None
        if shipment.destination_location:
            destination_country = getattr(shipment.destination_location, 'country_code', None)

        return determine_quote_currency(
            shipment_type=shipment.shipment_type,
            payment_term=shipment.payment_term,
            origin_country_code=origin_country,
            destination_country_code=destination_country,
        )

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
        self._record_fx_fallback("BUY", currency)
        return Decimal('1')

    def _get_fx_sell_rate(self, currency: str, rates: dict) -> Decimal:
        if currency == 'PGK':
            return Decimal('1')
        info = rates.get(currency, {})
        if info and info.get('tt_sell'):
            return Decimal(str(info['tt_sell']))
        logger.warning("No FX SELL rate found for %s; using 1.0", currency)
        self._record_fx_fallback("SELL", currency)
        return Decimal('1')

    def _convert_fcy_to_pgk(self, amount: Decimal, fx_rate: Decimal, caf_pct: Decimal = Decimal('0')) -> Decimal:
        """
        Convert FCY to PGK using the stored TT BUY rate.
        CAF Rule: When using TT BUY to convert FCY -> PGK, subtract the CAF percentage.
        """
        if fx_rate <= 0:
            return amount
            
        rate = fx_rate * (Decimal('1') - caf_pct)
        if rate <= 0:
            return amount
            
        # The system usually stores rates as FCY per PGK (e.g., 0.3342 AUD per 1 PGK),
        # but may also contain PGK per FCY (>1). Use a safe heuristic:
        if rate >= 1:
            return amount * rate
        return amount / rate

    def _convert_pgk_to_fcy(self, amount: Decimal, fx_rate: Decimal, caf_pct: Decimal = Decimal('0')) -> Decimal:
        """
        Convert PGK to FCY using the stored TT SELL rate.
        CAF Rule: When using TT SELL to convert PGK -> FCY, add the CAF percentage.
        """
        if fx_rate <= 0:
            return amount
            
        rate = fx_rate * (Decimal('1') + caf_pct)
        if rate <= 0:
            return amount
            
        if rate >= 1:
            return amount / rate
        return amount * rate

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
        """
        Calculates final totals from individual charge lines with strict filtering.
        Ensures that missing rates and informational lines do NOT bleed into the commercial totals.
        """
        # 1. STRICT FILTERING: Explicitly exclude 'informational' and 'missing' rates from financial totals.
        # This prevents "Ghost Charges" or "Zero-Value placeholders" from distorting the Quote Amount.
        billable_lines = [
            l for l in lines 
            if not getattr(l, "is_informational", False) 
            and not getattr(l, "conditional", False)
            and not getattr(l, "is_rate_missing", False)
        ]

        # 2. SUMMATION INTEGRITY: Sum from the strictly filtered billable lines only.
        total_cost_pgk = sum((l.cost_pgk for l in billable_lines), Decimal('0.00'))
        total_sell_pgk = sum((l.sell_pgk for l in billable_lines), Decimal('0.00'))
        total_sell_pgk_incl_gst = sum((l.sell_pgk_incl_gst for l in billable_lines), Decimal('0.00'))
        
        # Calculate FCY totals by summing converted line items directly.
        # Currency Pipeline Verification: sell_fcy was calculated using TT SELL in the earlier conversion pass.
        total_sell_fcy = sum((l.sell_fcy for l in billable_lines), Decimal('0.00')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        total_sell_fcy_incl_gst = sum((l.sell_fcy_incl_gst for l in billable_lines), Decimal('0.00')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        fx_rates = self._get_fx_rates_dict()
        output_currency = self.get_output_currency()
        
        shipment = getattr(self.quote_input, "shipment", None)
        shipment_type = getattr(shipment, "shipment_type", None)
        service_scope = getattr(shipment, "service_scope", None)
        is_dg = getattr(shipment, "is_dangerous_goods", False)
        commodity_code = getattr(shipment, "commodity_code", DEFAULT_COMMODITY_CODE)
        origin_code = _normalize_station_code(getattr(getattr(shipment, "origin_location", None), "code", None))
        destination_code = _normalize_station_code(getattr(getattr(shipment, "destination_location", None), "code", None))
        quote_date = getattr(self.quote_input, "quote_date", None)
        payment_term = getattr(shipment, "payment_term", None)
        
        # 3. COMPLETENESS EVALUATION (Safety Handlers)
        coverage = evaluate_from_lines(lines, shipment_type, service_scope)
        
        # Base completeness signal: required components by scope.
        has_missing_rates = not coverage.is_complete

        # Normal mode should use the same required-component coverage model as the
        # deterministic SPOT trigger. Extra missing standard lines in an already
        # covered bucket should be visible in logs, but must not force the quote
        # into INCOMPLETE or re-route a covered lane into the SPOT UX.
        if self.pricing_mode != PricingMode.SPOT:
            non_blocking_missing_codes = [
                getattr(line, "service_component_code", "UNKNOWN")
                for line in lines
                if getattr(line, "is_rate_missing", False)
            ]
            if non_blocking_missing_codes and coverage.is_complete:
                logger.info(
                    "Ignoring non-blocking missing standard lines after required scope coverage was satisfied: %s",
                    ", ".join(non_blocking_missing_codes),
                )

        totals = CalculatedTotals(
            total_cost_pgk=total_cost_pgk,
            total_sell_pgk=total_sell_pgk,
            total_sell_pgk_incl_gst=total_sell_pgk_incl_gst,
            total_sell_fcy=total_sell_fcy,
            total_sell_fcy_incl_gst=total_sell_fcy_incl_gst,
            total_sell_fcy_currency=output_currency,
            has_missing_rates=has_missing_rates,
            notes=coverage.notes,
        )
        return QuoteCharges(lines=lines, totals=totals)

    def _merge_charge_lines(
        self, 
        standard_lines: List[CalculatedChargeLine], 
        spot_lines: List[CalculatedChargeLine]
    ) -> List[CalculatedChargeLine]:
        """
        Unified merge: SPOT lines replace standard lines in matching buckets.
        
        This applies to ALL shipment types (Export, Import, Domestic).
        Per AGENTS.md: "Spot freight charges MUST replace standard freight
        charges for the same leg/route, never append."
        """
        if not spot_lines:
            return standard_lines

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
        from quotes.spot_models import SPEChargeLineDB, SpotPricingEnvelopeDB
        from quotes.spot_services import SpotEnvelopeService
        from quotes.spot_schemas import (
            SpotPricingEnvelope,
            SPEShipmentContext,
            SPEChargeLine,
            SPEConditions,
            SPEAcknowledgement,
            SPEStatus,
        )
        
        # 1. Load SPE from database
        try:
            spe_db = SpotPricingEnvelopeDB.objects.prefetch_related(
                models.Prefetch(
                    "charge_lines",
                    queryset=SPEChargeLineDB.objects.select_related(
                        "resolved_product_code",
                        "manual_resolved_product_code",
                    ),
                ),
                'acknowledgement'
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
        
        charges = []
        for cl in spe_db.charge_lines.all():
            if cl.amount is None or cl.amount <= 0:
                logger.warning(
                    "Skipping invalid SPE charge line with non-positive amount: spe=%s line=%s amount=%s",
                    spe_db.id,
                    cl.id,
                    cl.amount,
                )
                continue
            charges.append(SPEChargeLine(
                code=_spot_charge_display_code(cl),
                description=_spot_charge_display_description(cl),
                amount=float(cl.amount),
                currency=cl.currency,
                unit=cl.unit,
                bucket=cl.bucket,
                is_primary_cost=cl.is_primary_cost,
                conditional=cl.conditional,
                exclude_from_totals=getattr(cl, "exclude_from_totals", False),
                percentage_basis=getattr(cl, "percentage_basis", None),
                calculation_type=getattr(cl, "calculation_type", None),
                unit_type=getattr(cl, "unit_type", None),
                rate=float(cl.rate) if getattr(cl, "rate", None) is not None else None,
                min_amount=float(cl.min_amount) if getattr(cl, "min_amount", None) is not None else None,
                max_amount=float(cl.max_amount) if getattr(cl, "max_amount", None) is not None else None,
                percent=float(cl.percent) if getattr(cl, "percent", None) is not None else None,
                percent_basis=getattr(cl, "percent_basis", None),
                rule_meta=getattr(cl, "rule_meta", {}) or {},
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
        output_currency = self.get_output_currency()
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
        
        bucket_has_base: Dict[str, bool] = {}
        for charge in charges:
            if charge.unit != "percentage" and not charge.conditional and not getattr(charge, "exclude_from_totals", False):
                bucket_has_base[charge.bucket] = True

        ordered_charges = sorted(
            charges,
            key=lambda c: 1 if ((c.calculation_type or "").lower() == "percent_of" or c.unit == "percentage") else 0
        )

        basis_amounts: Dict[str, Decimal] = {
            "freight": Decimal("0"),
            "origin": Decimal("0"),
            "destination": Decimal("0"),
            "total": Decimal("0"),
        }
        shipment_context = {
            "chargeable_weight_kg": chargeable_weight,
            "shipment_count": Decimal("1"),
            "awb_count": Decimal("1"),
            "trip_count": Decimal("1"),
            "set_count": Decimal("1"),
            "man_count": Decimal("1"),
            "line_count": Decimal(len(charges)),
            "basis_amounts": basis_amounts,
        }

        for charge in ordered_charges:
            # [FIX] Handle conditional/informational charges
            is_percentage = charge.unit == "percentage" or (charge.calculation_type or "").lower() == "percent_of"
            is_info = (
                charge.conditional
                or getattr(charge, "exclude_from_totals", False)
                or (is_percentage and not bucket_has_base.get(charge.bucket, False))
            )
            
            # Determine CAF pct
            caf_pct = Decimal("0")
            if self.policy:
                shipment_type = self.quote_input.shipment.shipment_type
                if shipment_type == 'IMPORT':
                    caf_pct = Decimal(str(self.policy.caf_import_pct))
                elif shipment_type == 'EXPORT':
                    caf_pct = Decimal(str(self.policy.caf_export_pct))

            fx_buy = self._get_fx_buy_rate(charge.currency, fx_rates)
            
            # Canonical rule evaluator (supports FLAT, PER_UNIT, MIN_OR_PER_UNIT, PERCENT_OF, etc.)
            rule = {
                "calculation_type": charge.calculation_type,
                "unit_type": charge.unit_type,
                "rate": charge.rate,
                "min_amount": charge.min_amount,
                "max_amount": charge.max_amount,
                "percent": charge.percent,
                "percent_basis": charge.percent_basis or charge.percentage_basis,
                "rule_meta": charge.rule_meta or {},
                # Legacy fallback fields (for backward compatibility)
                "amount": charge.amount,
                "unit": charge.unit,
                "min_charge": charge.min_charge,
                "percentage_basis": charge.percentage_basis,
            }
            normalized_rule = normalize_charge_rule(rule)
            cost_fcy = evaluate_charge_rule(rule, shipment_context)
            if cost_fcy < 0:
                cost_fcy = Decimal("0")
                
            # Convert to PGK using TT BUY (subtracts CAF per hardcoded rule)
            cost_pgk = self._convert_fcy_to_pgk(cost_fcy, fx_buy, caf_pct)
            
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
                # Convert sell price to output currency using TT SELL (adds CAF per hardcoded rule)
                sell_fcy = self._convert_pgk_to_fcy(sell_pgk, output_fx_sell, caf_pct)
                sell_fcy_incl_gst = self._convert_pgk_to_fcy(sell_incl_gst, output_fx_sell, caf_pct)
            
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
            unit_type = str(getattr(sc, "unit", None) or getattr(charge, "unit_type", None) or "SHIPMENT").upper()
            canonical_component = (
                "FREIGHT"
                if charge.bucket == "airfreight"
                else ("DESTINATION_LOCAL" if charge.bucket == "destination_charges" else "ORIGIN_LOCAL")
            )
            quantity = quantity_for_unit(
                unit_type,
                {
                    "chargeable_weight": shipment_context["chargeable_weight_kg"],
                    "pieces": int(shipment_context["shipment_count"]),
                },
            )
            canonical_cost_source = "PARTNER_SPOT"
            rate_source = "PARTNER_SPOT"
            
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
                product_code=charge.code,
                component=canonical_component,
                basis=basis_for_unit(unit_type),
                rule_family=normalized_rule.get("calculation_type"),
                unit_type=unit_type,
                quantity=quantity,
                rate=normalized_rule.get("percent") or normalized_rule.get("rate"),
                rate_source=rate_source,
                canonical_cost_source=canonical_cost_source,
                calculation_notes=charge.description,
                is_spot_sourced=True,
                is_manual_override=False,
                is_informational=is_info,
                is_rate_missing=False,
                # GST Fields
                gst_category=charge_mock.gst_category if hasattr(charge_mock, 'gst_category') else None,
                gst_rate=gst_rate,
                gst_amount=(sell_fcy_incl_gst - sell_fcy).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
            ))

            # Track computed non-conditional base amounts for percentage basis lookups.
            if not charge.conditional and not getattr(charge, "exclude_from_totals", False):
                code_key = (charge.code or "").lower()
                basis_amounts[code_key] = basis_amounts.get(code_key, Decimal("0")) + cost_fcy
                if charge.bucket == "airfreight":
                    basis_amounts["freight"] += cost_fcy
                elif charge.bucket == "origin_charges":
                    basis_amounts["origin"] += cost_fcy
                elif charge.bucket == "destination_charges":
                    basis_amounts["destination"] += cost_fcy
                basis_amounts["total"] += cost_fcy
            
        return lines
