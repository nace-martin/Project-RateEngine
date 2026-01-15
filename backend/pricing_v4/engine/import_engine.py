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
"""
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List, Optional, Literal
from enum import Enum
import logging

from pricing_v4.models import ImportCOGS, ImportSellRate, ProductCode

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
    agent_name: Optional[str]  # NEW: Rate Provider
    
    # Sell in quote currency
    sell_amount: Decimal
    sell_currency: str
    
    # Margin info
    margin_amount: Decimal
    margin_percent: Decimal
    
    # Flags
    fx_applied: bool = False
    caf_applied: bool = False
    margin_applied: bool = False
    
    notes: str = ""


@dataclass
class QuoteResult:
    """Complete quote result."""
    origin: str
    destination: str
    quote_date: date
    chargeable_weight_kg: Decimal
    
    direction: str
    payment_term: str
    service_scope: str
    
    quote_currency: str
    
    # Breakdown
    origin_lines: List[ChargeLine] = field(default_factory=list)
    freight_lines: List[ChargeLine] = field(default_factory=list)
    destination_lines: List[ChargeLine] = field(default_factory=list)
    
    # Totals
    total_cost: Decimal = Decimal('0')
    total_sell: Decimal = Decimal('0')
    total_margin: Decimal = Decimal('0')
    
    # FX info used
    fx_rate_used: Optional[Decimal] = None
    effective_fx_rate: Optional[Decimal] = None
    caf_rate: Optional[Decimal] = None


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
        
        # Determine quote currency from payment term
        self.quote_currency = self._determine_quote_currency()
        
        # Cache for FSC calculations
        self._cost_cache: Dict[str, Decimal] = {}
    
    def _determine_quote_currency(self) -> str:
        """
        Payment Term determines quote currency.
        Import COLLECT = PGK (consignee in PNG pays)
        Import PREPAID = FCY (shipper abroad pays)
        """
        if self.payment_term == PaymentTerm.COLLECT:
            return 'PGK'
        else:  # PREPAID
            return 'AUD'  # Or could be determined by origin country
    
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
    
    def _convert_fcy_to_pgk(self, amount: Decimal) -> Decimal:
        """
        FCY → PGK conversion (Import).
        Uses TT BUY, CAF subtracted, DIVIDE.
        
        Per PricingPolicy.md:
        effective_rate = tt_buy × (1 − CAF)
        amount_pgk = fcy_amount ÷ effective_rate
        """
        effective_rate = self.tt_buy * (Decimal('1') - self.caf_rate)
        pgk = amount / effective_rate
        return pgk.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    
    def _convert_pgk_to_fcy(self, amount: Decimal) -> Decimal:
        """
        PGK → FCY conversion (for Prepaid dest charges).
        Uses TT SELL, CAF subtracted (Import), MULTIPLY.
        
        Note: For Import, CAF is subtracted regardless of conversion direction.
        """
        effective_rate = self.tt_sell * (Decimal('1') - self.caf_rate)
        fcy = amount * effective_rate
        return fcy.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    
    def _apply_margin(self, amount: Decimal) -> Decimal:
        """Apply margin (always last)."""
        return (amount * (Decimal('1') + self.margin_rate)).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP
        )
    
    def _calculate_cogs_amount(self, cogs, pc: ProductCode) -> Decimal:
        """Calculate COGS amount for a rate record."""
        amount = Decimal('0')
        
        # Percentage-based (FSC)
        if cogs.percent_rate:
            # FSC - find base charge
            base_pc = pc.percent_of_product_code
            if base_pc and base_pc.code in self._cost_cache:
                base_amount = self._cost_cache[base_pc.code]
                amount = base_amount * (cogs.percent_rate / Decimal('100'))
            return amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        
        # Weight breaks
        if cogs.weight_breaks:
            wb = sorted(cogs.weight_breaks, key=lambda x: Decimal(str(x['min_kg'])), reverse=True)
            for tier in wb:
                if self.weight >= Decimal(str(tier['min_kg'])):
                    amount = self.weight * Decimal(str(tier['rate']))
                    break
        elif cogs.rate_per_kg:
            amount = self.weight * cogs.rate_per_kg
        
        # Flat rate
        if cogs.rate_per_shipment:
            if amount == 0:
                amount = cogs.rate_per_shipment
            elif hasattr(cogs, 'is_additive') and cogs.is_additive:
                amount += cogs.rate_per_shipment
        
        # Min/Max
        if cogs.min_charge and amount < cogs.min_charge:
            amount = cogs.min_charge
        if cogs.max_charge and amount > cogs.max_charge:
            amount = cogs.max_charge
        
        return amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    
    def _get_leg_for_product_code(self, pc: ProductCode) -> str:
        """Determine which leg a ProductCode belongs to."""
        code = pc.code.upper()
        
        if 'ORIGIN' in code or code in ['IMP-PICKUP', 'IMP-FSC-PICKUP']:
            return 'ORIGIN'
        elif 'DEST' in code or code in ['IMP-CLEAR', 'IMP-CARTAGE-DEST', 'IMP-FSC-CARTAGE-DEST']:
            return 'DESTINATION'
        elif 'FRT' in code or 'FREIGHT' in code:
            return 'FREIGHT'
        else:
            # Default based on category
            if pc.category in ['CARTAGE', 'CLEARANCE']:
                return 'DESTINATION'
            return 'ORIGIN'
    
    def calculate_quote(self) -> QuoteResult:
        """
        Calculate complete import quote.
        """
        active_legs = self._get_active_legs()
        
        result = QuoteResult(
            origin=self.origin,
            destination=self.destination,
            quote_date=self.quote_date,
            chargeable_weight_kg=self.weight,
            direction='IMPORT',
            payment_term=self.payment_term.value,
            service_scope=self.service_scope.value,
            quote_currency=self.quote_currency,
            fx_rate_used=self.tt_buy if self.payment_term == PaymentTerm.COLLECT else self.tt_sell,
            caf_rate=self.caf_rate,
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
            ).first()
            
            if cogs:
                cost = self._calculate_cogs_amount(cogs, pc)
                self._cost_cache[pc.code] = cost
        
        # Second pass: Calculate all charges including FSC
        for pc in import_pcs:
            leg = self._get_leg_for_product_code(pc)
            if leg not in active_legs:
                continue
            
            line = self._calculate_charge_line(pc, leg)
            if line:
                if leg == 'ORIGIN':
                    result.origin_lines.append(line)
                elif leg == 'FREIGHT':
                    result.freight_lines.append(line)
                else:
                    result.destination_lines.append(line)
        
        # Calculate totals
        all_lines = result.origin_lines + result.freight_lines + result.destination_lines
        result.total_cost = sum(line.cost_amount for line in all_lines)
        result.total_sell = sum(line.sell_amount for line in all_lines)
        result.total_margin = sum(line.margin_amount for line in all_lines)
        
        return result
    
    def _calculate_charge_line(self, pc: ProductCode, leg: str) -> Optional[ChargeLine]:
        """Calculate a single charge line."""
        
        # Get COGS
        cogs = ImportCOGS.objects.filter(
            product_code=pc,
            origin_airport=self.origin,
            destination_airport=self.destination,
            valid_from__lte=self.quote_date,
            valid_until__gte=self.quote_date
        ).select_related('agent').first()
        
        # Get explicit Sell (for destination)
        sell_rate = ImportSellRate.objects.filter(
            product_code=pc,
            origin_airport=self.origin,
            destination_airport=self.destination,
            valid_from__lte=self.quote_date,
            valid_until__gte=self.quote_date
        ).first()
        
        # Skip if no rates found
        if not cogs and not sell_rate:
            return None
        
        # Calculate cost
        cost_amount = Decimal('0')
        cost_currency = 'AUD'  # Default for origin
        
        if cogs:
            cost_amount = self._calculate_cogs_amount(cogs, pc)
            cost_currency = cogs.currency
            self._cost_cache[pc.code] = cost_amount
        
        # Determine sell amount based on leg and payment term
        sell_amount = Decimal('0')
        sell_currency = self.quote_currency
        fx_applied = False
        caf_applied = False
        margin_applied = False
        
        if leg == 'DESTINATION' and sell_rate:
            # Destination: Use explicit sell rate
            if sell_rate.percent_rate:
                # FSC percentage
                base_pc = pc.percent_of_product_code
                if base_pc:
                    base_sell = self._get_dest_sell_amount(base_pc)
                    sell_amount = base_sell * (sell_rate.percent_rate / Decimal('100'))
            else:
                sell_amount = self._calculate_sell_amount(sell_rate)
            
            # Convert if needed (PREPAID = FCY quote, dest charges in PGK)
            if self.payment_term == PaymentTerm.PREPAID and sell_rate.currency == 'PGK':
                sell_amount = self._convert_pgk_to_fcy(sell_amount)
                fx_applied = True
                caf_applied = True
            
            sell_currency = self.quote_currency
            
        else:
            # Origin/Freight: Cost-Plus
            sell_amount = cost_amount
            
            # FX conversion if needed
            if self._needs_fx_conversion(leg):
                if cost_currency == 'AUD' and self.quote_currency == 'PGK':
                    sell_amount = self._convert_fcy_to_pgk(cost_amount)
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
                if cost_currency == 'AUD' and sell_currency == 'PGK':
                    cost_in_quote_curr = cost_amount / self.tt_buy  # Simple conversion for display
                else:
                    cost_in_quote_curr = cost_amount
                margin_amount = sell_amount - cost_in_quote_curr
                margin_percent = (margin_amount / cost_in_quote_curr * 100).quantize(Decimal('0.1'))
            else:
                margin_amount = sell_amount - cost_amount
                margin_percent = (margin_amount / cost_amount * 100).quantize(Decimal('0.1'))
        
        return ChargeLine(
            product_code_id=pc.id,
            product_code=pc.code,
            description=pc.description,
            category=pc.category,
            leg=leg,
            cost_amount=cost_amount,
            cost_currency=cost_currency,
            agent_name=cogs.agent.name if cogs and cogs.agent else None,  # NEW
            sell_amount=sell_amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
            sell_currency=sell_currency,
            margin_amount=margin_amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
            margin_percent=margin_percent,
            fx_applied=fx_applied,
            caf_applied=caf_applied,
            margin_applied=margin_applied,
        )
    
    def _calculate_sell_amount(self, sell_rate) -> Decimal:
        """Calculate sell amount from explicit sell rate."""
        amount = Decimal('0')
        
        if sell_rate.weight_breaks:
            wb = sorted(sell_rate.weight_breaks, key=lambda x: Decimal(str(x['min_kg'])), reverse=True)
            for tier in wb:
                if self.weight >= Decimal(str(tier['min_kg'])):
                    amount = self.weight * Decimal(str(tier['rate']))
                    break
        elif sell_rate.rate_per_kg:
            amount = self.weight * sell_rate.rate_per_kg
        
        if sell_rate.rate_per_shipment:
            if amount == 0:
                amount = sell_rate.rate_per_shipment
            elif hasattr(sell_rate, 'is_additive') and sell_rate.is_additive:
                amount += sell_rate.rate_per_shipment
        
        if sell_rate.min_charge and amount < sell_rate.min_charge:
            amount = sell_rate.min_charge
        if sell_rate.max_charge and amount > sell_rate.max_charge:
            amount = sell_rate.max_charge
        
        return amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    
    def _get_dest_sell_amount(self, pc: ProductCode) -> Decimal:
        """Get destination sell amount for FSC base calculation."""
        sell_rate = ImportSellRate.objects.filter(
            product_code=pc,
            origin_airport=self.origin,
            destination_airport=self.destination,
            valid_from__lte=self.quote_date,
            valid_until__gte=self.quote_date
        ).first()
        
        if sell_rate:
            return self._calculate_sell_amount(sell_rate)
        return Decimal('0')
