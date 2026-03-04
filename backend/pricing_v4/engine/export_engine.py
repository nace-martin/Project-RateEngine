# backend/pricing_v4/engine/export_engine.py
"""
Export Pricing Engine - Greenfield Implementation

Design Principles:
- Rule 5: No pricing logic in ORM queries - simple lookups only
- Pricing rules live in Python code, not database queries
- All calculations are linear, readable, auditable

AMENDMENTS:
- Security Screening: is_additive=True means rate_per_kg + rate_per_shipment are ADDED
- FSC: percent_rate field for percentage-based surcharges
- Payment Terms: PREPAID quotes in PGK, COLLECT quotes in FCY (destination currency)
- PNG GST: Proper classification using get_png_gst_category()
- Global Surcharges: Support for Surcharge table fallbacks
- Customs Brokerage: Default PGK 300.00 if rate missing
- Airline Fuel Surcharge: Default PGK 0.80/kg
- Security Surcharge: Default PGK 0.20/kg + PGK 45.00 flat
- Terminal Fee: Default PGK 150.00 if rate missing
- Handling Fee: Default PGK 50.00 if rate missing
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List, Optional
from enum import Enum

from pricing_v4.models import (
    ProductCode, ExportCOGS, ExportSellRate,
    LocalSellRate, LocalCOGSRate, Surcharge
)
from core.charge_rules import evaluate_charge_rule
from quotes.tax_policy import get_png_gst_category

# Categories that are location-based (not lane-based)
LOCAL_CATEGORIES = ['CLEARANCE', 'CARTAGE', 'HANDLING', 'DOCUMENTATION', 'SCREENING', 'AGENCY', 'SURCHARGE', 'TERMINAL']


class PaymentTerm(Enum):
    COLLECT = "COLLECT"
    PREPAID = "PREPAID"


@dataclass
class ChargeLineResult:
    """Result of a single charge line calculation."""
    product_code_id: int
    product_code: str
    description: str
    category: str
    
    # Cost values (what EFM pays) - always in PGK for Export
    cost_amount: Decimal
    cost_currency: str
    cost_source: str  # 'COGS' or 'N/A' if no cost
    agent_name: Optional[str]  # Rate Provider (e.g., EFM AU)
    
    # Sell values (what EFM charges) - in quote currency
    sell_amount: Decimal
    sell_currency: str
    
    # Margin (calculated, not stored)
    margin_amount: Decimal
    margin_percent: Decimal
    
    # Tax (PNG GST Classification)
    gst_category: str = ''  # service_in_PNG, export_service, offshore_service, imported_goods
    gst_rate: Decimal = Decimal('0')
    gst_amount: Decimal = Decimal('0')
    sell_incl_gst: Decimal = Decimal('0')
    
    # Status
    is_rate_missing: bool = False
    notes: str = ''
    
    # Conversion flags
    fx_applied: bool = False
    caf_applied: bool = False
    margin_applied: bool = False


@dataclass
class QuoteResult:
    """Complete quote result."""
    origin: str
    destination: str
    quote_date: date
    chargeable_weight_kg: Decimal
    
    # Charge lines
    lines: List[ChargeLineResult]
    
    # Totals (in quote currency)
    total_cost: Decimal
    total_sell: Decimal
    total_margin: Decimal
    total_gst: Decimal
    total_sell_incl_gst: Decimal
    
    # Currency and conversion info
    currency: str
    quote_currency: str = 'PGK'
    payment_term: str = 'PREPAID'
    fx_rate_used: Optional[Decimal] = None
    effective_fx_rate: Optional[Decimal] = None
    caf_rate: Optional[Decimal] = None



class ExportPricingEngine:
    """
    Calculates Export quotes.
    
    Rule 5: Simple queries, rules in code.
    Rule 9: Focused on POM→BNE corridor first.
    """
    
    # Default rates
    DEFAULT_MARGIN = Decimal('0.20')  # 20%
    DEFAULT_CAF = Decimal('0.05')     # 5%
    DEFAULT_BROKERAGE_FEE = Decimal('300.00')
    DEFAULT_AIR_FUEL_SURCHARGE = Decimal('0.80') # K0.80 per kg
    
    # Security Surcharge: K0.20/kg + K45.00 flat
    DEFAULT_SECURITY_SCREEN_RATE = Decimal('0.20')
    DEFAULT_SECURITY_SCREEN_FLAT = Decimal('45.00')
    
    # Terminal and Handling
    DEFAULT_TERMINAL_FEE = Decimal('150.00')
    DEFAULT_HANDLING_FEE = Decimal('50.00')
    
    def __init__(
        self,
        quote_date: date,
        origin: str,
        destination: str,
        chargeable_weight_kg: Decimal,
        payment_term: PaymentTerm = PaymentTerm.PREPAID,
        tt_buy: Optional[Decimal] = None,
        tt_sell: Optional[Decimal] = None,
        caf_rate: Optional[Decimal] = None,
        margin_rate: Optional[Decimal] = None,
        destination_currency: str = 'AUD',
    ):
        self.quote_date = quote_date
        self.origin = origin
        self.destination = destination
        self.chargeable_weight_kg = chargeable_weight_kg
        self.payment_term = payment_term
        
        # FX rates
        self.tt_buy = tt_buy or Decimal('0.35')
        self.tt_sell = tt_sell or Decimal('0.36')
        self.caf_rate = caf_rate if caf_rate is not None else self.DEFAULT_CAF
        self.margin_rate = margin_rate if margin_rate is not None else self.DEFAULT_MARGIN
        
        # Destination currency for COLLECT quotes
        self.destination_currency = destination_currency
        
        # Determine quote currency based on payment term
        self.quote_currency = self._determine_quote_currency()
        
        # Cache for calculated values (needed for percentage surcharges)
        self._sell_cache: Dict[int, Decimal] = {}
        self._cost_cache: Dict[int, Decimal] = {}
    
    def _determine_quote_currency(self) -> str:
        if self.payment_term == PaymentTerm.COLLECT:
            return self.destination_currency
        return 'PGK'
    
    def _convert_pgk_to_fcy(self, amount: Decimal) -> Decimal:
        effective_rate = self.tt_sell * (Decimal('1') + self.caf_rate)
        if effective_rate == 0: return amount
        fcy = amount / effective_rate
        return fcy.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    
    def _apply_margin(self, amount: Decimal) -> Decimal:
        return (amount * (Decimal('1') + self.margin_rate)).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP)
    
    def _get_effective_fx_rate(self) -> Decimal:
        return self.tt_sell * (Decimal('1') + self.caf_rate)
    
    # =========================================================================
    # PUBLIC API
    # =========================================================================
    
    @staticmethod
    def get_product_codes(is_dg: bool = False, service_scope: str = 'P2P') -> List[int]:
        if service_scope == 'A2A':
            service_scope = 'P2P'

        # All codes requested are now mandatory
        codes = ExportPricingEngine.get_mandatory_product_codes(is_dg, service_scope)
        
        # Origin Clearance (D2A, D2D)
        if service_scope in ('D2A', 'D2D'):
            codes.append(1020)  # EXP-CLEAR - Customs Clearance (Origin)
            codes.append(1071)  # EXP-VCH - Valuable Cargo Handling
            codes.append(1072)  # EXP-LPC - Livestock Processing Fee
        
        # Deduplicate and sort
        return sorted(list(set(codes)))

    @staticmethod
    def get_mandatory_product_codes(is_dg: bool = False, service_scope: str = 'P2P') -> List[int]:
        if service_scope == 'A2A': service_scope = 'P2P'

        codes = [
            1001,  # EXP-FRT-AIR - Air Freight
            1002,  # EXP-FSC-AIR - Airline Export Fuel Surcharge
            1010,  # EXP-DOC - Documentation
            1011,  # EXP-AWB - AWB Fee
            1030,  # EXP-TERM - Terminal Handling
            1032,  # EXP-HANDLE - Handling Fee
            1040,  # EXP-SCREEN - Security Screening
        ]
        
        if service_scope in ('D2A', 'D2D'):
            codes.extend([
                1020,  # EXP-CLEAR - Customs Clearance (Origin)
                1021,  # EXP-AGENCY - Agency Fee
                1031,  # EXP-BUILDUP - Build-Up
                1050,  # EXP-PICKUP - Pickup/Collection
                1060,  # EXP-FSC-PICKUP - Fuel Surcharge on Pickup
            ])
        
        if service_scope in ('D2D', 'A2D'):
            codes.extend([
                1080,  # EXP-CLEAR-DEST
                1081,  # EXP-DELIVERY-DEST
            ])
            
        if is_dg:
            codes.append(1070)
            
        return codes
    
    def calculate_quote(self, product_code_ids: List[int], is_dg: bool = False, service_scope: str = 'P2P') -> QuoteResult:
        self._prefetch_rates(product_code_ids)
        mandatory_ids = self.get_mandatory_product_codes(is_dg, service_scope)
        lines = []
        regular_ids = []
        percent_ids = []
        
        for pc_id in product_code_ids:
            pc = self._get_product_code(pc_id)
            if pc and pc.default_unit == ProductCode.UNIT_PERCENT:
                percent_ids.append(pc_id)
            else:
                regular_ids.append(pc_id)
        
        for pc_id in regular_ids:
            line = self._calculate_charge_line(pc_id, mandatory_ids)
            if line:
                lines.append(line)
                self._sell_cache[pc_id] = line.sell_amount
                self._cost_cache[pc_id] = line.cost_amount
        
        for pc_id in percent_ids:
            line = self._calculate_percentage_charge(pc_id)
            if line:
                lines.append(line)
        
        total_cost = sum(line.cost_amount for line in lines)
        total_sell = sum(line.sell_amount for line in lines)
        total_margin = sum(line.margin_amount for line in lines)
        total_gst = sum(line.gst_amount for line in lines)
        total_sell_incl_gst = sum(line.sell_incl_gst for line in lines)
        
        return QuoteResult(
            origin=self.origin, destination=self.destination, quote_date=self.quote_date,
            chargeable_weight_kg=self.chargeable_weight_kg, lines=lines,
            total_cost=total_cost, total_sell=total_sell, total_margin=total_margin,
            total_gst=total_gst, total_sell_incl_gst=total_sell_incl_gst,
            currency=self.quote_currency, quote_currency=self.quote_currency,
            payment_term=self.payment_term.value if hasattr(self.payment_term, 'value') else str(self.payment_term),
            fx_rate_used=self.tt_sell if self.payment_term == PaymentTerm.COLLECT else None,
            effective_fx_rate=self._get_effective_fx_rate() if self.payment_term == PaymentTerm.COLLECT else None,
            caf_rate=self.caf_rate if self.payment_term == PaymentTerm.COLLECT else None,
        )
    
    def _prefetch_rates(self, product_code_ids: List[int]):
        self._pc_cache = {}
        self._cogs_rate_cache = {}
        self._sell_rate_cache = {}
        self._surcharge_cache = {}
        pcs = ProductCode.objects.filter(id__in=product_code_ids)
        for pc in pcs: self._pc_cache[pc.id] = pc
        cogs_qs = ExportCOGS.objects.filter(
            product_code_id__in=product_code_ids, origin_airport=self.origin, destination_airport=self.destination,
            valid_from__lte=self.quote_date, valid_until__gte=self.quote_date
        ).select_related('agent')
        for rate in cogs_qs: self._cogs_rate_cache[rate.product_code_id] = rate
        sell_qs = ExportSellRate.objects.filter(
            product_code_id__in=product_code_ids, origin_airport=self.origin, destination_airport=self.destination,
            valid_from__lte=self.quote_date, valid_until__gte=self.quote_date
        )
        for rate in sell_qs:
            pc_id = rate.product_code_id
            if self.payment_term == PaymentTerm.COLLECT:
                if rate.currency == self.quote_currency: self._sell_rate_cache[pc_id] = rate
                elif pc_id not in self._sell_rate_cache: self._sell_rate_cache[pc_id] = rate
            else:
                # PREPAID export must use PGK sell rates only.
                if rate.currency == 'PGK':
                    self._sell_rate_cache[pc_id] = rate
        surcharges = Surcharge.objects.filter(
            product_code_id__in=product_code_ids, service_type__in=['EXPORT_AIR', 'EXPORT_ORIGIN', 'ALL'],
            is_active=True, valid_from__lte=self.quote_date, valid_until__gte=self.quote_date
        )
        for s in surcharges:
            if s.origin_filter and s.origin_filter != self.origin: continue
            if s.destination_filter and s.destination_filter != self.destination: continue
            self._surcharge_cache[(s.product_code_id, s.rate_side)] = s

    def _get_product_code(self, product_code_id: int) -> Optional[ProductCode]:
        return self._pc_cache.get(product_code_id) if hasattr(self, '_pc_cache') else ProductCode.objects.filter(id=product_code_id).first()
    
    def _get_cogs(self, product_code_id: int) -> Optional[any]:
        pc = self._get_product_code(product_code_id)
        if pc and pc.category in LOCAL_CATEGORIES:
            local = LocalCOGSRate.objects.filter(
                product_code_id=product_code_id, location=self.origin, direction='EXPORT',
                valid_from__lte=self.quote_date, valid_until__gte=self.quote_date
            ).first()
            if local: return local
        if hasattr(self, '_cogs_rate_cache') and product_code_id in self._cogs_rate_cache: return self._cogs_rate_cache[product_code_id]
        if hasattr(self, '_surcharge_cache'): return self._surcharge_cache.get((product_code_id, 'COGS'))
        return None
    
    def _get_sell_rate(self, product_code_id: int) -> Optional[any]:
        pc = self._get_product_code(product_code_id)
        if pc and pc.category in LOCAL_CATEGORIES:
            payment_term_value = self.payment_term.value if hasattr(self.payment_term, 'value') else str(self.payment_term)
            local_rates = LocalSellRate.objects.filter(
                product_code_id=product_code_id, location=self.origin, direction='EXPORT',
                payment_term__in=[payment_term_value, 'ANY'], valid_from__lte=self.quote_date, valid_until__gte=self.quote_date
            )
            preferred_currency = None
            if self.payment_term == PaymentTerm.COLLECT:
                preferred_currency = self.destination_currency or self.quote_currency
            elif self.payment_term == PaymentTerm.PREPAID:
                preferred_currency = self.quote_currency or 'PGK'

            if preferred_currency:
                rates = local_rates.filter(currency=preferred_currency)
                local = rates.filter(payment_term=payment_term_value).first() or rates.filter(payment_term='ANY').first()
                if local:
                    return local
                if self.payment_term == PaymentTerm.PREPAID:
                    # PREPAID export must not silently fall back to non-PGK rows.
                    return None

            # Fallback: exact payment term first, then ANY term, in any currency.
            local = local_rates.filter(payment_term=payment_term_value).first() or local_rates.filter(payment_term='ANY').first()
            if local:
                return local
        if hasattr(self, '_sell_rate_cache') and product_code_id in self._sell_rate_cache: return self._sell_rate_cache[product_code_id]
        if hasattr(self, '_surcharge_cache'): return self._surcharge_cache.get((product_code_id, 'SELL'))
        return None
    
    def _calculate_charge_line(self, product_code_id: int, mandatory_ids: List[int] = None) -> Optional[ChargeLineResult]:
        pc = self._get_product_code(product_code_id)
        if not pc: return None
        cogs = self._get_cogs(product_code_id)
        sell_rate = self._get_sell_rate(product_code_id)
        
        if not sell_rate:
            # 1. Customs Brokerage Default (PGK 300.00)
            if product_code_id == 1020:
                return self._create_default_line(pc, self.DEFAULT_BROKERAGE_FEE, "Default Customs Brokerage Fee")
            
            # 2. Airline Fuel Surcharge Default (PGK 0.80/kg)
            if product_code_id == 1002:
                sell_amount = (self.chargeable_weight_kg * self.DEFAULT_AIR_FUEL_SURCHARGE).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                return self._create_default_line(pc, sell_amount, f"Default Airline Fuel Surcharge (K{self.DEFAULT_AIR_FUEL_SURCHARGE}/kg)")

            # 3. Security Surcharge Default (PGK 0.20/kg + PGK 45.00 flat)
            if product_code_id == 1040:
                sell_amount = (self.chargeable_weight_kg * self.DEFAULT_SECURITY_SCREEN_RATE) + self.DEFAULT_SECURITY_SCREEN_FLAT
                sell_amount = sell_amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                return self._create_default_line(pc, sell_amount, f"Default Security Surcharge (K{self.DEFAULT_SECURITY_SCREEN_RATE}/kg + K{self.DEFAULT_SECURITY_SCREEN_FLAT} flat)")

            # 4. Terminal and Handling Defaults
            if product_code_id == 1030: # Terminal
                return self._create_default_line(pc, self.DEFAULT_TERMINAL_FEE, "Default Terminal Fee")
            if product_code_id == 1032: # Handling
                return self._create_default_line(pc, self.DEFAULT_HANDLING_FEE, "Default Handling Fee")

            if mandatory_ids and product_code_id in mandatory_ids:
                return ChargeLineResult(
                    product_code_id=pc.id, product_code=pc.code, description=pc.description,
                    category=pc.category, cost_amount=Decimal('0'), cost_currency='PGK',
                    cost_source='N/A', agent_name=None, sell_amount=Decimal('0'),
                    sell_currency=self.quote_currency, margin_amount=Decimal('0'),
                    margin_percent=Decimal('0'), gst_amount=Decimal('0'), sell_incl_gst=Decimal('0'),
                    is_rate_missing=True, notes=f"Mandatory sell rate missing for {pc.code}",
                )
            return None
        
        agent_name = getattr(cogs, 'agent', None)
        if agent_name: agent_name = agent_name.name
        cost_amount = self._calculate_amount(cogs) if cogs else Decimal('0')
        sell_amount_base = self._calculate_amount(sell_rate)
        
        fx_applied, caf_applied, margin_applied = False, False, False
        rate_is_fcy = (sell_rate.currency == self.quote_currency)
        if self.payment_term == PaymentTerm.COLLECT:
            if rate_is_fcy: sell_amount = sell_amount_base
            else:
                sell_with_margin = self._apply_margin(sell_amount_base)
                margin_applied = True
                sell_amount = self._convert_pgk_to_fcy(sell_with_margin)
                fx_applied, caf_applied = True, True
        else:
            sell_amount = sell_amount_base
        
        margin_cost_base = cost_amount
        if self.payment_term == PaymentTerm.COLLECT and rate_is_fcy and cost_amount > 0:
            margin_cost_base = self._convert_pgk_to_fcy(cost_amount)
            
        margin_amount = sell_amount - margin_cost_base
        margin_percent = (margin_amount / margin_cost_base * 100 if margin_cost_base > 0 else Decimal('0'))
        
        gst_category, gst_rate = get_png_gst_category(product_code=pc, shipment_type='EXPORT', leg='ORIGIN')
        gst_amount = (sell_amount * gst_rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        sell_incl_gst = sell_amount + gst_amount
        
        return ChargeLineResult(
            product_code_id=pc.id, product_code=pc.code, description=pc.description,
            category=pc.category, cost_amount=cost_amount, cost_currency=getattr(cogs, 'currency', 'PGK'),
            cost_source='COGS' if cogs else 'N/A', agent_name=agent_name, sell_amount=sell_amount,
            sell_currency=getattr(sell_rate, 'currency', 'PGK') if not fx_applied else self.quote_currency, 
            margin_amount=margin_amount, margin_percent=margin_percent,
            gst_category=gst_category, gst_rate=gst_rate, gst_amount=gst_amount, sell_incl_gst=sell_incl_gst,
            is_rate_missing=False, notes='', fx_applied=fx_applied, caf_applied=caf_applied, margin_applied=margin_applied,
        )

    def _create_default_line(self, pc: ProductCode, sell_amount: Decimal, notes: str) -> ChargeLineResult:
        gst_category, gst_rate = get_png_gst_category(product_code=pc, shipment_type='EXPORT', leg='ORIGIN')
        gst_amount = (sell_amount * gst_rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        return ChargeLineResult(
            product_code_id=pc.id, product_code=pc.code, description=pc.description,
            category=pc.category, cost_amount=Decimal('0'), cost_currency='PGK',
            cost_source='Default', agent_name=None, sell_amount=sell_amount,
            sell_currency='PGK', margin_amount=sell_amount,
            margin_percent=Decimal('100.00'), gst_amount=gst_amount, sell_incl_gst=sell_amount+gst_amount,
            is_rate_missing=False, notes=notes,
        )
    
    def _calculate_percentage_charge(self, product_code_id: int) -> Optional[ChargeLineResult]:
        pc = self._get_product_code(product_code_id); base_pc = pc.percent_of_product_code if pc else None
        if not pc or not base_pc: return None
        sell_rate = self._get_sell_rate(product_code_id)
        if not sell_rate or not sell_rate.percent_rate: return None
        base_sell = self._sell_cache.get(base_pc.id, Decimal('0')); base_cost = self._cost_cache.get(base_pc.id, Decimal('0'))
        percent = sell_rate.percent_rate / Decimal('100')
        sell_amount = (base_sell * percent).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        cost_amount = (base_cost * percent).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        margin_amount = sell_amount - cost_amount
        margin_percent = (margin_amount / cost_amount * 100) if cost_amount > 0 else Decimal('0')
        gst_category, gst_rate = get_png_gst_category(product_code=pc, shipment_type='EXPORT', leg='ORIGIN')
        gst_amount = (sell_amount * gst_rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        return ChargeLineResult(
            product_code_id=pc.id, product_code=pc.code,
            description=f"{pc.description} ({sell_rate.percent_rate}% of {base_pc.code})",
            category=pc.category, cost_amount=cost_amount, cost_currency='PGK',
            cost_source=f'{sell_rate.percent_rate}% of COGS', sell_amount=sell_amount,
            sell_currency=sell_rate.currency, margin_amount=margin_amount, margin_percent=margin_percent,
            gst_category=gst_category, gst_rate=gst_rate, gst_amount=gst_amount, sell_incl_gst=sell_amount+gst_amount,
            is_rate_missing=False, notes=f'Based on {base_pc.code}: K{base_sell}', agent_name=None,
        )
    
    def _calculate_amount(self, rate) -> Decimal:
        weight = self.chargeable_weight_kg
        if hasattr(rate, 'amount') and not hasattr(rate, 'rate_per_kg'): # Surcharge table
            amount = weight * rate.amount if rate.rate_type == 'PER_KG' else rate.amount
        elif rate.weight_breaks: amount = self._calculate_weight_break(rate.weight_breaks, weight)
        elif getattr(rate, 'is_additive', False) and rate.rate_per_kg and rate.rate_per_shipment:
            amount = (weight * rate.rate_per_kg) + rate.rate_per_shipment
        elif rate.rate_per_kg:
            amount = weight * rate.rate_per_kg
            if rate.min_charge and amount < rate.min_charge: amount = rate.min_charge
        elif rate.rate_per_shipment: amount = rate.rate_per_shipment
        else: amount = Decimal('0')
        if hasattr(rate, 'min_charge') and rate.min_charge and amount < rate.min_charge: amount = rate.min_charge
        if hasattr(rate, 'max_charge') and rate.max_charge and amount > rate.max_charge: amount = rate.max_charge
        return amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    
    def _calculate_weight_break(self, breaks: list, weight: Decimal) -> Decimal:
        if not breaks: return Decimal('0')
        sorted_breaks = sorted(breaks, key=lambda x: Decimal(str(x.get('min_kg', 0))), reverse=True)
        for tier in sorted_breaks:
            if weight >= Decimal(str(tier.get('min_kg', 0))): return weight * Decimal(str(tier.get('rate', 0)))
        return weight * Decimal(str(sorted_breaks[-1].get('rate', 0)))
