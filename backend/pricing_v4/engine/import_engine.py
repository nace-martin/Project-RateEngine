"""
Import Pricing Engine V4
========================
Implements pricing logic per PricingPolicy.md

Key Rules:
1. CAF adjusts the FX rate, not the amount
2. FX conversion before margin
3. Margin applied last
4. FSC only on Pickup/Cartage
5. Direction determines CAF direction (Import = subtract)
6. Payment Term determines quote currency
7. Service Scope determines which legs are chargeable
8. PNG GST: Proper classification using get_png_gst_category()
"""
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List, Optional, Literal
from enum import Enum
import logging

from core.commodity import DEFAULT_COMMODITY_CODE
from pricing_v4.models import (
    ImportCOGS, ImportSellRate, ProductCode,
    LocalSellRate, LocalCOGSRate
)
from pricing_v4.category_rules import is_local_rate_category
from pricing_v4.commodity_rules import get_auto_product_code_ids, is_product_code_enabled
from core.charge_rules import (
    CALCULATION_FLAT,
    CALCULATION_LOOKUP_RATE,
    RuleEvaluation,
    evaluate_rate_lookup_rule,
)
from quotes.tax_policy import get_png_gst_category
from quotes.quote_result_contract import (
    QuoteComponent,
    basis_for_unit,
    normalize_cost_source,
    normalize_rate_source,
)
from pricing_v4.engine.result_types import QuoteLineItem, QuoteResult, build_tax_breakdown

logger = logging.getLogger(__name__)

class PaymentTerm(Enum):
    COLLECT = "COLLECT"
    PREPAID = "PREPAID"


class ServiceScope(Enum):
    A2A = "A2A"  # Airport to Airport
    A2D = "A2D"  # Airport to Door
    D2A = "D2A"  # Door to Airport
    D2D = "D2D"  # Door to Door


@dataclass
class ChargeLine:
    """Single charge line result."""
    product_code_id: int
    product_code: str
    description: str
    category: str
    leg: str  # 'ORIGIN', 'FREIGHT', 'DESTINATION'
    
    # Cost in original currency
    cost_amount: Decimal
    cost_currency: str
    cost_source: str = 'N/A'
    agent_name: Optional[str] = None  # Rate Provider
    
    # Sell in quote currency
    sell_amount: Decimal = Decimal('0')
    sell_currency: str = 'PGK'
    
    # Margin info
    margin_amount: Decimal = Decimal('0')
    margin_percent: Decimal = Decimal('0')
    
    # Flags
    fx_applied: bool = False
    caf_applied: bool = False
    margin_applied: bool = False
    
    # PNG GST Classification
    gst_category: str = ''  # service_in_PNG, export_service, offshore_service, imported_goods
    gst_rate: Decimal = Decimal('0')
    gst_amount: Decimal = Decimal('0')
    sell_incl_gst: Decimal = Decimal('0')
    
    notes: str = ""
    rule_family: str = CALCULATION_LOOKUP_RATE


class ImportPricingEngine:
    """
    Import Pricing Engine following PricingPolicy.md
    
    Scenario Matrix (Import only):
    | Term | Scope | Quote | Active Legs | FX Applied To |
    |------|-------|-------|-------------|---------------|
    | PREP | A2D   | FCY   | Dest        | Dest: PGK→FCY |
    | COLL | A2D   | PGK   | Dest        | None          |
    | COLL | D2D   | PGK   | O+F+D       | O+F: FCY→PGK  |
    """
    
    # Default rates (should be configurable)
    DEFAULT_MARGIN = Decimal('0.20')  # 20%
    DEFAULT_CAF = Decimal('0.05')     # 5%
    ORIGIN_FSC_RATE = Decimal('0.20') # 20% on Pickup
    DEST_FSC_RATE = Decimal('0.10')   # 10% on Cartage
    
    def __init__(
        self,
        quote_date: date,
        origin: str,
        destination: str,
        chargeable_weight_kg: Decimal,
        payment_term: PaymentTerm,
        service_scope: ServiceScope,
        tt_buy: Optional[Decimal] = None,
        tt_sell: Optional[Decimal] = None,
        caf_rate: Optional[Decimal] = None,
        margin_rate: Optional[Decimal] = None,
        fx_rates: Optional[Dict] = None,
        quote_currency: Optional[str] = None,
    ):
        self.quote_date = quote_date
        self.origin = origin
        self.destination = destination
        self.weight = chargeable_weight_kg
        self.payment_term = payment_term
        self.service_scope = service_scope
        
        self.tt_buy = tt_buy or Decimal('0.35')  # Default TT BUY
        self.tt_sell = tt_sell or Decimal('0.36')  # Default TT SELL
        self.caf_rate = caf_rate or self.DEFAULT_CAF
        self.margin_rate = margin_rate or self.DEFAULT_MARGIN
        self.fx_rates = fx_rates or {}
        self._warnings: List[str] = []
        self._audit_metadata: Dict[str, List[dict[str, str]]] = {"fx_fallbacks": []}
        
        # Determine quote currency (prefer explicit override, else derive)
        self.quote_currency = quote_currency or self._determine_quote_currency()
        
        # Cache for FSC calculations
        self._cost_cache: Dict[str, Decimal] = {}
    
    def _determine_quote_currency(self) -> str:
        """
        Payment Term determines quote currency.
        Import COLLECT = PGK (consignee in PNG pays)
        Import PREPAID = FCY (shipper abroad pays), default USD.

        Note: In production flow, adapter/view passes explicit quote_currency
        derived from canonical country/payment rules.
        """
        if self.payment_term == PaymentTerm.COLLECT:
            return 'PGK'
        return 'USD'
    
    def _get_active_legs(self) -> List[str]:
        """
        Service Scope determines which legs are in scope.
        """
        if self.service_scope == ServiceScope.A2D:
            return ['DESTINATION']
        elif self.service_scope == ServiceScope.D2A:
            return ['ORIGIN', 'FREIGHT']
        elif self.service_scope == ServiceScope.D2D:
            return ['ORIGIN', 'FREIGHT', 'DESTINATION']
        else:  # A2A
            return ['FREIGHT']
    
    def _needs_fx_conversion(self, leg: str) -> bool:
        """
        Determine if a leg needs FX conversion based on scenario matrix.
        """
        if self.payment_term == PaymentTerm.COLLECT:
            # PGK quote - Origin/Freight (FCY) need conversion
            if self.service_scope == ServiceScope.D2D:
                return leg in ['ORIGIN', 'FREIGHT']
            elif self.service_scope == ServiceScope.A2D:
                return False  # Dest already in PGK
        else:  # PREPAID
            # FCY quote - Destination (PGK) needs conversion
            if self.service_scope == ServiceScope.A2D:
                return leg == 'DESTINATION'
            elif self.service_scope == ServiceScope.D2D:
                return leg == 'DESTINATION'
        return False
    
    def _get_rate_for_currency(self, currency: str, rate_type: str = 'tt_sell') -> Decimal:
        """Get FX rate for specific currency."""
        if currency == 'PGK':
            return Decimal('1.0')
        
        # Check standard rates
        if currency == self.quote_currency:
             return self.tt_buy if rate_type == 'tt_buy' else self.tt_sell
             
        # Look up in fx_rates
        info = self.fx_rates.get(currency)
        if info and info.get(rate_type):
            return Decimal(str(info[rate_type]))
            
        logger.warning(f"Missing {rate_type} rate for {currency}, defaulting to 1.0")
        warning = f"FX {rate_type.upper()} rate missing for {currency}; used 1.0 fallback."
        if warning not in self._warnings:
            self._warnings.append(warning)
        self._audit_metadata.setdefault("fx_fallbacks", []).append(
            {
                "currency": str(currency or "").upper() or "UNKNOWN",
                "direction": rate_type.upper(),
                "fallback_rate": "1.0",
            }
        )
        return Decimal('1.0')

    def _convert_fcy_to_pgk(self, amount: Decimal, currency: Optional[str] = None) -> Decimal:
        """
        FCY → PGK conversion (Import).
        Uses TT BUY, CAF subtracted, DIVIDE.
        """
        rate = self.tt_buy
        if currency:
            rate = self._get_rate_for_currency(currency, 'tt_buy')
            
        effective_rate = rate * (Decimal('1') - self.caf_rate)
        if effective_rate == 0: return amount # Prevent div/0
        
        pgk = amount / effective_rate
        return pgk.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    
    def _convert_pgk_to_fcy(self, amount: Decimal, target_currency: Optional[str] = None) -> Decimal:
        """
        PGK → FCY conversion.
        Uses TT SELL, CAF subtracted (Import), MULTIPLY.
        """
        rate = self.tt_sell
        if target_currency:
             rate = self._get_rate_for_currency(target_currency, 'tt_sell')
             
        effective_rate = rate * (Decimal('1') - self.caf_rate)
        fcy = amount * effective_rate
        return fcy.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    
    def _convert_cross_currency(self, amount: Decimal, from_curr: str, to_curr: str) -> Decimal:
        """Convert any currency to any currency via PGK."""
        if from_curr == to_curr:
            return amount
            
        # 1. Convert source to PGK (using TT BUY)
        if from_curr == 'PGK':
            amount_pgk = amount
        else:
            amount_pgk = self._convert_fcy_to_pgk(amount, from_curr)
            
        # 2. Convert PGK to target (using TT SELL)
        if to_curr == 'PGK':
            return amount_pgk
        else:
            return self._convert_pgk_to_fcy(amount_pgk, to_curr)

    def _apply_margin(self, amount: Decimal) -> Decimal:
        """Apply margin (always last)."""
        return (amount * (Decimal('1') + self.margin_rate)).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP
        )
    
    def _calculate_cogs_amount(self, cogs, pc: ProductCode) -> RuleEvaluation:
        """Calculate COGS amount for a rate record."""
        base_amount = Decimal('0.00')
        if cogs.percent_rate:
            base_pc = pc.percent_of_product_code
            if base_pc and base_pc.code in self._cost_cache:
                base_amount = self._cost_cache[base_pc.code]
        return evaluate_rate_lookup_rule(
            rate=cogs,
            quantity=self.weight,
            base_amount=base_amount,
        )
    
    def _get_leg_for_product_code(self, pc: ProductCode) -> str:
        """Determine which leg a ProductCode belongs to."""
        code = pc.code.upper()
        
        if 'ORIGIN' in code or code in ['IMP-PICKUP', 'IMP-FSC-PICKUP']:
            return 'ORIGIN'
        elif 'DEST' in code or code in ['IMP-CLEAR', 'IMP-CARTAGE-DEST', 'IMP-FSC-CARTAGE-DEST']:
            return 'DESTINATION'
        elif pc.domain == 'IMPORT' and '-SPECIAL' in code:
            return 'DESTINATION'
        elif 'FRT' in code or 'FREIGHT' in code:
            return 'FREIGHT'
        else:
            # Default based on category
            if pc.category in ['CARTAGE', 'CLEARANCE']:
                return 'DESTINATION'
            return 'ORIGIN'
    
    def calculate_quote(self, commodity_code: str = DEFAULT_COMMODITY_CODE) -> QuoteResult:
        """
        Calculate complete import quote.
        """
        active_legs = self._get_active_legs()
        payment_term_value = self.payment_term.value if hasattr(self.payment_term, 'value') else str(self.payment_term)
        requested_product_code_ids = self.get_requested_product_code_ids(
            is_dg=False,
            service_scope=self.service_scope.value,
            commodity_code=commodity_code,
            origin=self.origin,
            destination=self.destination,
            payment_term=payment_term_value,
            quote_date=self.quote_date,
        )
        
        result = QuoteResult(
            origin=self.origin,
            destination=self.destination,
            quote_date=self.quote_date,
            chargeable_weight_kg=self.weight,
            direction='IMPORT',
            payment_term=self.payment_term.value,
            service_scope=self.service_scope.value,
            quote_currency=self.quote_currency,
            currency=self.quote_currency,
            fx_rate_used=self.tt_buy if self.payment_term == PaymentTerm.COLLECT else self.tt_sell,
            caf_rate=self.caf_rate,
            warnings=list(self._warnings),
            audit_metadata=self._audit_metadata,
        )
        
        # Calculate effective FX rate
        if self.payment_term == PaymentTerm.COLLECT:
            result.effective_fx_rate = self.tt_buy * (Decimal('1') - self.caf_rate)
        else:
            result.effective_fx_rate = self.tt_sell * (Decimal('1') - self.caf_rate)
        
        # Get all Import ProductCodes
        import_pcs = ProductCode.objects.filter(domain='IMPORT').order_by('id')

        # First pass: Calculate base costs (for FSC dependencies)
        for pc in import_pcs:
            if not is_product_code_enabled(
                shipment_type='IMPORT',
                service_scope=self.service_scope.value,
                commodity_code=commodity_code,
                product_code_id=pc.id,
                origin_code=self.origin,
                destination_code=self.destination,
                payment_term=payment_term_value,
                quote_date=self.quote_date,
            ):
                continue
            leg = self._get_leg_for_product_code(pc)
            if leg not in active_legs:
                continue
            
            # Skip percentage-based codes in first pass
            if pc.default_unit == 'PERCENT':
                continue
            
            cogs = ImportCOGS.objects.filter(
                product_code=pc,
                origin_airport=self.origin,
                destination_airport=self.destination,
                valid_from__lte=self.quote_date,
                valid_until__gte=self.quote_date
            ).order_by('-valid_from', '-updated_at', '-id').first()
            
            if cogs:
                cost_eval = self._calculate_cogs_amount(cogs, pc)
                self._cost_cache[pc.code] = cost_eval.amount
        
        # Second pass: Calculate all charges including FSC
        for pc in import_pcs:
            if not is_product_code_enabled(
                shipment_type='IMPORT',
                service_scope=self.service_scope.value,
                commodity_code=commodity_code,
                product_code_id=pc.id,
                origin_code=self.origin,
                destination_code=self.destination,
                payment_term=payment_term_value,
                quote_date=self.quote_date,
            ):
                continue
            leg = self._get_leg_for_product_code(pc)
            if leg not in active_legs:
                continue
            
            line = self._calculate_charge_line(pc, leg)
            
            # If no line but the engine explicitly requested this ProductCode,
            # create a missing-rate placeholder so the gap remains visible.
            if not line and pc.id in requested_product_code_ids:
                # [AMENDMENT] Requested Customs Brokerage Fee Default (PGK 300.00)
                if pc.id == 2020:
                    line = ChargeLine(
                        product_code_id=pc.id, product_code=pc.code, description=pc.description,
                        category=pc.category, leg=leg, cost_amount=Decimal('0'),
                        cost_currency='PGK', cost_source='Default', agent_name=None, sell_amount=Decimal('300.00'),
                        sell_currency=self.quote_currency, margin_amount=Decimal('300.00'),
                        margin_percent=Decimal('100.00'), notes="Default Customs Brokerage Fee applied.",
                        rule_family=CALCULATION_FLAT,
                    )
                    # Handle FCY conversion for PREPAID quotes
                    if self.quote_currency != 'PGK':
                        line.sell_amount = self._convert_pgk_to_fcy(Decimal('300.00'))
                        line.fx_applied = True
                        line.caf_applied = True
                    
                    # Apply GST Classification
                    gst_cat, gst_r = get_png_gst_category(product_code=pc, shipment_type='IMPORT', leg=leg)
                    line.gst_category = gst_cat
                    line.gst_rate = gst_r
                    # Force GST to 0 if rate is missing to prevent AUD 0.00 base with non-zero GST
                    line.gst_amount = Decimal('0.00')
                    line.sell_incl_gst = Decimal('0.00')
                else:
                    line = ChargeLine(
                        product_code_id=pc.id,
                        product_code=pc.code,
                        description=pc.description,
                        category=pc.category,
                        leg=leg,
                        cost_amount=Decimal('0'),
                        cost_currency='PGK',
                        cost_source='N/A',
                        agent_name=None,
                        sell_amount=Decimal('0'),
                        sell_currency=self.quote_currency,
                        margin_amount=Decimal('0'),
                        margin_percent=Decimal('0'),
                        notes=f"Requested rate missing for {pc.code}",
                        rule_family=CALCULATION_LOOKUP_RATE,
                    )
                    line.is_rate_missing = True # Dynamically added for adapter detection

            if line:
                if leg == 'ORIGIN':
                    result.line_items.append(self._to_quote_line_item(line))
                elif leg == 'FREIGHT':
                    result.line_items.append(self._to_quote_line_item(line))
                else:
                    result.line_items.append(self._to_quote_line_item(line))
        
        # Calculate totals
        all_lines = result.line_items
        result.total_cost_pgk = sum((self._convert_cross_currency(line.cost_amount, line.cost_currency, 'PGK') for line in all_lines), Decimal('0.00'))
        result.total_sell_pgk = sum((self._convert_cross_currency(line.sell_amount, line.sell_currency, 'PGK') for line in all_lines), Decimal('0.00'))
        result.total_margin = sum(line.margin_amount for line in all_lines)
        result.total_gst = sum(line.gst_amount for line in all_lines)
        result.total_sell_incl_gst = sum(line.sell_incl_gst for line in all_lines)
        result.fx_applied = any(line.fx_applied for line in all_lines)
        result.tax_breakdown = build_tax_breakdown(
            all_lines,
            converter=lambda amount, currency: self._convert_cross_currency(amount, currency, 'PGK'),
        )
        
        return result

    @staticmethod
    def get_requested_product_code_ids(
        is_dg: bool = False,
        service_scope: str = 'A2A',
        commodity_code: str = DEFAULT_COMMODITY_CODE,
        origin: Optional[str] = None,
        destination: Optional[str] = None,
        payment_term: Optional[str] = None,
        quote_date: Optional[date] = None,
    ) -> List[int]:
        """
        Returns ProductCode IDs the import engine should actively try to price
        or represent with explicit missing-rate placeholders.
        """
        service_scope = service_scope.upper()
        if service_scope == 'P2P': service_scope = 'A2A'

        codes = []
        
        # Freight is requested for all scopes involving linehaul
        if service_scope in ('A2A', 'D2A', 'D2D'):
            codes.append(2001)  # IMP-FRT-AIR

        # Origin local requested for D2A and D2D
        if service_scope in ('D2A', 'D2D'):
            codes.extend([
                2010,  # IMP-DOC-ORIGIN
                2011,  # IMP-AWB-ORIGIN
                2012,  # IMP-AGENCY-ORIGIN
                2030,  # IMP-CTO-ORIGIN
                2040,  # IMP-SCREEN-ORIGIN
                2050,  # IMP-PICKUP
                2060,  # IMP-FSC-PICKUP
            ])

        # Destination local requested for A2D and D2D
        if service_scope in ('A2D', 'D2D'):
            codes.extend([
                2020,  # IMP-CLEAR
                2021,  # IMP-AGENCY-DEST
                2022,  # IMP-DOC-DEST
                2070,  # IMP-HANDLING-DEST
                2071,  # IMP-LOADING-DEST
                2072,  # IMP-CARTAGE-DEST
                2080,  # IMP-FSC-CARTAGE-DEST
            ])

        codes.extend(get_auto_product_code_ids(
            shipment_type='IMPORT',
            service_scope=service_scope,
            commodity_code=commodity_code,
            origin_code=origin,
            destination_code=destination,
            payment_term=payment_term,
            quote_date=quote_date,
        ))

        return sorted(list(set(codes)))
    
    def _calculate_charge_line(self, pc: ProductCode, leg: str) -> Optional[ChargeLine]:
        """Calculate a single charge line."""
        
        # Get COGS - route to local table for destination local categories
        cogs = self._get_cogs(pc, leg)
        
        # Get explicit Sell (for destination) - route to local table for local categories
        if leg == 'DESTINATION':
            sell_rate = self._get_destination_sell_rate(pc)
        else:
            sell_rate = self._get_sell_rate(pc, leg)
        
        # Skip if no rates found
        if not cogs and not sell_rate:
            return None
        
        # Calculate cost
        cost_amount = Decimal('0')
        cost_currency = 'AUD'  # Default for origin
        cost_eval = RuleEvaluation(CALCULATION_LOOKUP_RATE, Decimal('0.00'))
        
        if cogs:
            cost_eval = self._calculate_cogs_amount(cogs, pc)
            cost_amount = cost_eval.amount
            cost_currency = cogs.currency
            self._cost_cache[pc.code] = cost_amount
        
        # Determine sell amount based on leg and payment term
        sell_amount = Decimal('0')
        sell_currency = self.quote_currency
        fx_applied = False
        caf_applied = False
        margin_applied = False
        sell_eval = RuleEvaluation(CALCULATION_LOOKUP_RATE, Decimal('0.00'))
        
        if leg == 'DESTINATION' and sell_rate:
            # Destination: Use explicit sell rate
            base_sell = Decimal('0.00')
            if sell_rate.percent_rate:
                base_pc = pc.percent_of_product_code
                if base_pc:
                    base_sell = self._get_dest_sell_amount(base_pc)
            sell_eval = self._calculate_sell_amount(sell_rate, base_amount=base_sell)
            sell_amount = sell_eval.amount
            
            # Currency handling for destination charges
            # If sell rate currency != quote currency, we must convert.
            if sell_rate.currency != self.quote_currency:
                sell_amount = self._convert_cross_currency(sell_amount, sell_rate.currency, self.quote_currency)
                fx_applied = True
                caf_applied = True
            
            sell_currency = self.quote_currency
            
        else:
            # Origin/Freight: Cost-Plus
            sell_amount = cost_amount
            sell_eval = cost_eval
            
            # FX conversion if needed
            if cost_currency != self.quote_currency:
                sell_amount = self._convert_cross_currency(cost_amount, cost_currency, self.quote_currency)
                fx_applied = True
                caf_applied = True
            
            # Apply margin
            sell_amount = self._apply_margin(sell_amount)
            margin_applied = True
            sell_currency = self.quote_currency
        
        # Calculate margin
        margin_amount = sell_amount - (cost_amount if not fx_applied else Decimal('0'))
        margin_percent = Decimal('0')
        if cost_amount > 0:
            # For proper margin calc, need to compare in same currency
            if fx_applied and cost_currency != sell_currency:
                # Convert cost to sell currency for comparison
                cost_in_quote_curr = self._convert_cross_currency(cost_amount, cost_currency, sell_currency)
                margin_amount = sell_amount - cost_in_quote_curr
                if cost_in_quote_curr > 0:
                    margin_percent = (margin_amount / cost_in_quote_curr * 100).quantize(Decimal('0.1'))
            else:
                margin_amount = sell_amount - cost_amount
                margin_percent = (margin_amount / cost_amount * 100).quantize(Decimal('0.1'))
        
        # Calculate GST using PNG classification
        gst_category, gst_rate = get_png_gst_category(
            product_code=pc,
            shipment_type='IMPORT',
            leg=leg
        )
        gst_amount = (sell_amount * gst_rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        sell_incl_gst = sell_amount + gst_amount
        
        return ChargeLine(
            product_code_id=pc.id,
            product_code=pc.code,
            description=pc.description,
            category=pc.category,
            leg=leg,
            cost_amount=cost_amount,
            cost_currency=cost_currency,
            cost_source='COGS' if cogs else 'N/A',
            agent_name=cogs.agent.name if cogs and cogs.agent else None,
            sell_amount=sell_amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
            sell_currency=sell_currency,
            margin_amount=margin_amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
            margin_percent=margin_percent,
            fx_applied=fx_applied,
            caf_applied=caf_applied,
            margin_applied=margin_applied,
            gst_category=gst_category,
            gst_rate=gst_rate,
            gst_amount=gst_amount,
            sell_incl_gst=sell_incl_gst,
            rule_family=sell_eval.rule_family if sell_eval.amount > 0 else cost_eval.rule_family,
        )

    @staticmethod
    def _to_quote_line_item(line: ChargeLine) -> QuoteLineItem:
        component = QuoteComponent.ORIGIN_LOCAL
        if line.leg == 'FREIGHT':
            component = QuoteComponent.FREIGHT
        elif line.leg == 'DESTINATION':
            component = QuoteComponent.DESTINATION_LOCAL
        unit_type = 'KG' if line.leg == 'FREIGHT' else 'SHIPMENT'
        is_spot_sourced = 'SPOT' in str(line.cost_source or '').upper()
        is_manual_override = any(token in str(line.cost_source or '').upper() for token in ['MANUAL', 'OVERRIDE'])
        return QuoteLineItem(
            product_code_id=line.product_code_id,
            product_code=line.product_code,
            description=line.description,
            component=component,
            basis=basis_for_unit(unit_type),
            rule_family=line.rule_family,
            unit_type=unit_type,
            quantity=Decimal('1.00'),
            currency=line.sell_currency,
            category=line.category,
            leg=line.leg,
            cost_amount=line.cost_amount,
            cost_currency=line.cost_currency,
            cost_source=normalize_cost_source(
                line.cost_source,
                is_spot_sourced=is_spot_sourced,
                is_manual_override=is_manual_override,
            ),
            agent_name=line.agent_name,
            sell_amount=line.sell_amount,
            sell_currency=line.sell_currency,
            margin_amount=line.margin_amount,
            margin_percent=line.margin_percent,
            tax_code=line.gst_category or 'GST',
            tax_amount=line.gst_amount,
            gst_category=line.gst_category,
            gst_rate=line.gst_rate,
            gst_amount=line.gst_amount,
            sell_incl_gst=line.sell_incl_gst,
            rate_source=normalize_rate_source(
                line.cost_source,
                is_spot_sourced=is_spot_sourced,
                is_manual_override=is_manual_override,
            ),
            calculation_notes=line.notes or None,
            is_spot_sourced=is_spot_sourced,
            is_manual_override=is_manual_override,
            is_rate_missing=getattr(line, 'is_rate_missing', False),
            notes=line.notes,
            fx_applied=line.fx_applied,
            caf_applied=line.caf_applied,
            margin_applied=line.margin_applied,
        )
    
    def _calculate_sell_amount(self, sell_rate, *, base_amount: Decimal = Decimal('0.00')) -> RuleEvaluation:
        """Calculate sell amount from explicit sell rate."""
        return evaluate_rate_lookup_rule(
            rate=sell_rate,
            quantity=self.weight,
            base_amount=base_amount,
        )
    
    def _get_dest_sell_amount(self, pc: ProductCode) -> Decimal:
        """Get destination sell amount for FSC base calculation."""
        sell_rate = self._get_destination_sell_rate(pc)
        
        if sell_rate:
            sell_amount = self._calculate_sell_amount(sell_rate).amount
            if sell_rate.currency != self.quote_currency:
                sell_amount = self._convert_cross_currency(sell_amount, sell_rate.currency, self.quote_currency)
            return sell_amount
        return Decimal('0')

    def _get_destination_sell_rate(self, pc: ProductCode):
        """
        Get destination sell rate.
        Routes to LocalSellRate for local categories, ImportSellRate for freight.
        """
        if is_local_rate_category(pc.category):
            return self._get_local_sell_rate(pc)
        
        # Lane-based lookup for FREIGHT
        base_qs = ImportSellRate.objects.filter(
            product_code=pc,
            origin_airport=self.origin,
            destination_airport=self.destination,
            valid_from__lte=self.quote_date,
            valid_until__gte=self.quote_date
        ).order_by('id')

        sell_rate = base_qs.filter(currency=self.quote_currency).first()
        if sell_rate:
            return sell_rate
        if self.payment_term == PaymentTerm.PREPAID:
            pgk = base_qs.filter(currency='PGK').first()
            if pgk: return pgk
        if self.payment_term == PaymentTerm.COLLECT:
            fcy = base_qs.exclude(currency='PGK').first()
            if fcy: return fcy
            
        # Final fallback: Anything we can find (e.g. USD when quote is AUD)
        return base_qs.first()
    
    def _get_cogs(self, pc: ProductCode, leg: Optional[str] = None):
        """
        Get COGS for a product code.
        Destination-local import charges live in LocalCOGSRate.
        Origin-local and freight import charges remain lane-based in ImportCOGS,
        with a LocalCOGSRate fallback for legacy migrated datasets.
        """
        if leg == 'DESTINATION' and is_local_rate_category(pc.category):
            return self._get_local_cogs(pc, leg)

        lane_cogs = ImportCOGS.objects.filter(
            product_code=pc,
            origin_airport=self.origin,
            destination_airport=self.destination,
            valid_from__lte=self.quote_date,
            valid_until__gte=self.quote_date
        ).select_related('agent').order_by('-valid_from', '-updated_at', '-id').first()

        if lane_cogs:
            return lane_cogs

        if leg == 'ORIGIN' and is_local_rate_category(pc.category):
            return self._get_local_cogs(pc, leg)

        return None
    
    def _get_sell_rate(self, pc: ProductCode, leg: str):
        """
        Get sell rate for non-destination legs.
        Uses lane-based ImportSellRate (origin/freight sell is cost-plus).
        """
        # Lane-based lookup
        return ImportSellRate.objects.filter(
            product_code=pc,
            origin_airport=self.origin,
            destination_airport=self.destination,
            currency=self.quote_currency,
            valid_from__lte=self.quote_date,
            valid_until__gte=self.quote_date
        ).order_by('-valid_from', '-updated_at', '-id').first()
    
    def _get_local_cogs(self, pc: ProductCode, leg: str):
        """
        Lookup local COGS from centralized table for IMPORT.

        Lookup order:
        - DESTINATION leg: destination station first.
        - ORIGIN leg: origin station first.
        - Compatibility fallback for legacy migrated datasets: destination station.
        """
        if leg == 'ORIGIN':
            location_candidates = [self.origin, self.destination]
        else:
            location_candidates = [self.destination]

        for location in location_candidates:
            local_rate = LocalCOGSRate.objects.filter(
                product_code=pc,
                location=location,
                direction='IMPORT',
                valid_from__lte=self.quote_date,
                valid_until__gte=self.quote_date
            ).order_by('-valid_from', '-updated_at', '-id').first()
            if local_rate:
                return local_rate

        return None
    
    def _get_local_sell_rate(self, pc: ProductCode):
        """
        Lookup local sell rate from centralized table.
        
        Priority: Exact payment_term match first, then fallback to 'ANY'.
        
        Currency Rules for Import Destination Charges:
        - COLLECT: PGK (consignee in PNG pays in local currency)
        - PREPAID from AU: AUD 
        - PREPAID from other: USD
        """
        payment_term_value = self.payment_term.value if hasattr(self.payment_term, 'value') else str(self.payment_term)
        
        # Try new LocalSellRate table first
        base_qs = LocalSellRate.objects.filter(
            product_code=pc,
            location=self.destination,
            direction='IMPORT',
            payment_term__in=[payment_term_value, 'ANY'],
            valid_from__lte=self.quote_date,
            valid_until__gte=self.quote_date
        )
        # Enforce rate-type compatibility for percentage ProductCodes.
        if pc.default_unit == ProductCode.UNIT_PERCENT:
            base_qs = base_qs.filter(
                rate_type='PERCENT',
                percent_of_product_code__isnull=False,
            )
        else:
            base_qs = base_qs.exclude(rate_type='PERCENT')

        # Priority 1: Match quote currency + exact payment term
        rates = base_qs.filter(currency=self.quote_currency)
        exact = rates.filter(payment_term=payment_term_value).first()
        if exact:
            return exact

        # Priority 2: Match quote currency + ANY term
        any_term = rates.filter(payment_term='ANY').first()
        if any_term:
            return any_term

        # Priority 3: Any currency + exact payment term
        exact_any_currency = base_qs.filter(payment_term=payment_term_value).first()
        if exact_any_currency:
            return exact_any_currency

        # Priority 4: Any currency + ANY term
        any_any = base_qs.filter(payment_term='ANY').first()
        if any_any:
            return any_any

        return None
