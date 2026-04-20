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
- Payment Terms:
  - PREPAID quotes in destination FCY (AUD for AU, otherwise USD)
  - COLLECT quotes in PGK
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

from core.commodity import DEFAULT_COMMODITY_CODE
from pricing_v4.commodity_rules import get_auto_product_code_ids
from pricing_v4.models import (
    ProductCode, ExportCOGS, ExportSellRate,
    LocalSellRate, LocalCOGSRate, Surcharge
)
from pricing_v4.category_rules import (
    is_local_rate_category,
    resolve_export_local_location,
)
from core.charge_rules import (
    CALCULATION_FLAT,
    CALCULATION_PERCENT_OF_BASE,
    RuleEvaluation,
    evaluate_percent_of_base_rule,
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
    rule_family: str = CALCULATION_FLAT


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
        
        # Destination currency for PREPAID quotes
        self.destination_currency = destination_currency
        
        # Determine quote currency based on payment term
        self.quote_currency = self._determine_quote_currency()
        
        # Cache for calculated values (needed for percentage surcharges)
        self._sell_cache: Dict[int, Decimal] = {}
        self._cost_cache: Dict[int, Decimal] = {}
    
    def _determine_quote_currency(self) -> str:
        if self.payment_term == PaymentTerm.PREPAID:
            return self.destination_currency
        return 'PGK'
    
    def _convert_pgk_to_fcy(self, amount: Decimal) -> Decimal:
        effective_rate = self.tt_sell * (Decimal('1') + self.caf_rate)
        if effective_rate <= 0:
            return amount
        # FX snapshots may store either FCY/PGK (<1) or PGK/FCY (>1).
        # Use the same orientation heuristic as the adapter conversion helpers.
        if effective_rate >= 1:
            fcy = amount / effective_rate
        else:
            fcy = amount * effective_rate
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
    def get_product_codes(
        is_dg: bool = False,
        service_scope: str = 'P2P',
        commodity_code: str = DEFAULT_COMMODITY_CODE,
        origin: Optional[str] = None,
        destination: Optional[str] = None,
        payment_term: Optional[str] = None,
        quote_date: Optional[date] = None,
    ) -> List[int]:
        if service_scope == 'A2A':
            service_scope = 'P2P'

        codes = ExportPricingEngine.get_requested_product_code_ids(
            is_dg=is_dg,
            service_scope=service_scope,
            commodity_code=commodity_code,
            origin=origin,
            destination=destination,
            payment_term=payment_term,
            quote_date=quote_date,
        )
        
        # Origin Clearance (D2A, D2D)
        if service_scope in ('D2A', 'D2D'):
            codes.append(1020)  # EXP-CLEAR - Customs Clearance (Origin)
        
        # Deduplicate and sort
        return sorted(list(set(codes)))

    @staticmethod
    def get_requested_product_code_ids(
        is_dg: bool = False,
        service_scope: str = 'P2P',
        commodity_code: str = DEFAULT_COMMODITY_CODE,
        origin: Optional[str] = None,
        destination: Optional[str] = None,
        payment_term: Optional[str] = None,
        quote_date: Optional[date] = None,
    ) -> List[int]:
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

        codes.extend(get_auto_product_code_ids(
            shipment_type='EXPORT',
            service_scope=service_scope,
            commodity_code=commodity_code,
            origin_code=origin,
            destination_code=destination,
            payment_term=payment_term,
            quote_date=quote_date,
        ))
            
        return sorted(list(set(codes)))
    
    def calculate_quote(
        self,
        product_code_ids: List[int],
        is_dg: bool = False,
        service_scope: str = 'P2P',
        commodity_code: str = DEFAULT_COMMODITY_CODE,
    ) -> QuoteResult:
        self._prefetch_rates(product_code_ids)
        requested_product_code_ids = self.get_requested_product_code_ids(
            is_dg=is_dg,
            service_scope=service_scope,
            commodity_code=commodity_code,
            origin=self.origin,
            destination=self.destination,
            payment_term=self.payment_term.value if hasattr(self.payment_term, 'value') else str(self.payment_term),
            quote_date=self.quote_date,
        )
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
            line = self._calculate_charge_line(pc_id, requested_product_code_ids)
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

        line_items = [self._to_quote_line_item(line) for line in lines]
        total_cost_pgk = sum((self._convert_amount_to_pgk(line.cost_amount, line.cost_currency) for line in lines), Decimal('0.00'))
        total_sell_pgk = sum((self._convert_amount_to_pgk(line.sell_amount, line.sell_currency) for line in lines), Decimal('0.00'))

        return QuoteResult(
            line_items=line_items,
            total_cost_pgk=total_cost_pgk,
            total_sell_pgk=total_sell_pgk,
            fx_applied=any(item.fx_applied for item in line_items),
            tax_breakdown=build_tax_breakdown(line_items, converter=self._convert_amount_to_pgk),
            origin=self.origin, destination=self.destination, quote_date=self.quote_date,
            chargeable_weight_kg=self.chargeable_weight_kg,
            direction='EXPORT',
            payment_term=self.payment_term.value if hasattr(self.payment_term, 'value') else str(self.payment_term),
            service_scope=service_scope,
            currency=self.quote_currency, quote_currency=self.quote_currency,
            total_margin=total_margin, total_gst=total_gst, total_sell_incl_gst=total_sell_incl_gst,
            fx_rate_used=self.tt_sell if self.payment_term == PaymentTerm.PREPAID else None,
            effective_fx_rate=self._get_effective_fx_rate() if self.payment_term == PaymentTerm.PREPAID else None,
            caf_rate=self.caf_rate if self.payment_term == PaymentTerm.PREPAID else None,
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
        ).order_by('product_code_id', '-valid_from', '-updated_at', '-id')
        sell_candidates: Dict[int, List[ExportSellRate]] = {}
        for rate in sell_qs:
            sell_candidates.setdefault(rate.product_code_id, []).append(rate)
        for pc_id, candidates in sell_candidates.items():
            selected_rate = self._select_export_sell_rate(candidates)
            if selected_rate:
                self._sell_rate_cache[pc_id] = selected_rate
        surcharges = Surcharge.objects.filter(
            product_code_id__in=product_code_ids, service_type__in=['EXPORT_AIR', 'EXPORT_ORIGIN', 'ALL'],
            is_active=True, valid_from__lte=self.quote_date, valid_until__gte=self.quote_date
        )
        for s in surcharges:
            if s.origin_filter and s.origin_filter != self.origin: continue
            if s.destination_filter and s.destination_filter != self.destination: continue
            self._surcharge_cache[(s.product_code_id, s.rate_side)] = s

    def _select_export_sell_rate(self, candidates: List[ExportSellRate]) -> Optional[ExportSellRate]:
        """
        Pick one active export sell row deterministically.

        Safe fallbacks matter here because the engine only knows how to convert a
        PGK sell row into another quote currency. It must not treat an arbitrary
        foreign-currency row as a PGK base and then apply margin/FX again.
        """
        if not candidates:
            return None

        if self.payment_term == PaymentTerm.COLLECT:
            for rate in candidates:
                if rate.currency == 'PGK':
                    return rate
            return None

        for rate in candidates:
            if rate.currency == self.quote_currency:
                return rate

        for rate in candidates:
            if rate.currency == 'PGK':
                return rate

        return None

    def _get_product_code(self, product_code_id: int) -> Optional[ProductCode]:
        return self._pc_cache.get(product_code_id) if hasattr(self, '_pc_cache') else ProductCode.objects.filter(id=product_code_id).first()
    
    def _get_cogs(self, product_code_id: int) -> Optional[any]:
        pc = self._get_product_code(product_code_id)
        if pc and is_local_rate_category(pc.category):
            local_location = resolve_export_local_location(
                code=pc.code,
                description=pc.description,
                origin_airport=self.origin,
                destination_airport=self.destination,
            )
            local = LocalCOGSRate.objects.filter(
                product_code_id=product_code_id,
                location=local_location,
                direction='EXPORT',
                valid_from__lte=self.quote_date, valid_until__gte=self.quote_date
            ).order_by('-valid_from', '-updated_at', '-id').first()
            if local:
                return local
            return None
        if hasattr(self, '_cogs_rate_cache') and product_code_id in self._cogs_rate_cache: return self._cogs_rate_cache[product_code_id]
        if hasattr(self, '_surcharge_cache'): return self._surcharge_cache.get((product_code_id, 'COGS'))
        return None
    
    def _get_sell_rate(self, product_code_id: int) -> Optional[any]:
        pc = self._get_product_code(product_code_id)
        if pc and is_local_rate_category(pc.category):
            payment_term_value = self.payment_term.value if hasattr(self.payment_term, 'value') else str(self.payment_term)
            local_location = resolve_export_local_location(
                code=pc.code,
                description=pc.description,
                origin_airport=self.origin,
                destination_airport=self.destination,
            )
            local_rates = LocalSellRate.objects.filter(
                product_code_id=product_code_id,
                location=local_location,
                direction='EXPORT',
                payment_term__in=[payment_term_value, 'ANY'], valid_from__lte=self.quote_date, valid_until__gte=self.quote_date
            )
            # Enforce rate-type compatibility to avoid selecting placeholder FIXED rows
            # for percent-based ProductCodes (e.g., EXP-FSC-PICKUP).
            if pc.default_unit == ProductCode.UNIT_PERCENT:
                local_rates = local_rates.filter(
                    rate_type='PERCENT',
                    percent_of_product_code__isnull=False,
                )
            else:
                local_rates = local_rates.exclude(rate_type='PERCENT')

            preferred_currency = None
            if self.payment_term == PaymentTerm.PREPAID:
                preferred_currency = self.destination_currency or self.quote_currency
            elif self.payment_term == PaymentTerm.COLLECT:
                preferred_currency = self.quote_currency or 'PGK'

            if preferred_currency:
                rates = local_rates.filter(currency=preferred_currency)
                local = rates.filter(payment_term=payment_term_value).first() or rates.filter(payment_term='ANY').first()
                if local:
                    return local
                if self.payment_term == PaymentTerm.COLLECT:
                    # COLLECT export must not silently fall back to non-PGK rows.
                    return None
                if preferred_currency == 'PGK':
                    # PREPAID export in PGK must not misinterpret a foreign-currency
                    # sell row as a PGK base amount.
                    return None

                pgk_rates = local_rates.filter(currency='PGK')
                local = pgk_rates.filter(payment_term=payment_term_value).first() or pgk_rates.filter(payment_term='ANY').first()
                if local:
                    return local
                return None

            return None
        if hasattr(self, '_sell_rate_cache') and product_code_id in self._sell_rate_cache: return self._sell_rate_cache[product_code_id]
        if hasattr(self, '_surcharge_cache'): return self._surcharge_cache.get((product_code_id, 'SELL'))
        return None
    
    def _calculate_charge_line(self, product_code_id: int, requested_product_code_ids: List[int] = None) -> Optional[ChargeLineResult]:
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

            if requested_product_code_ids and product_code_id in requested_product_code_ids:
                return ChargeLineResult(
                    product_code_id=pc.id, product_code=pc.code, description=pc.description,
                    category=pc.category, cost_amount=Decimal('0'), cost_currency='PGK',
                    cost_source='N/A', agent_name=None, sell_amount=Decimal('0'),
                    sell_currency=self.quote_currency, margin_amount=Decimal('0'),
                    margin_percent=Decimal('0'), gst_amount=Decimal('0'), sell_incl_gst=Decimal('0'),
                    is_rate_missing=True, notes=f"Requested sell rate missing for {pc.code}",
                )
            return None
        
        agent_name = getattr(cogs, 'agent', None)
        if agent_name: agent_name = agent_name.name
        cost_eval = self._calculate_amount(cogs) if cogs else RuleEvaluation(CALCULATION_FLAT, Decimal('0.00'))
        sell_eval = self._calculate_amount(sell_rate)
        cost_amount = cost_eval.amount
        sell_amount_base = sell_eval.amount
        
        fx_applied, caf_applied, margin_applied = False, False, False
        rate_is_fcy = (sell_rate.currency == self.quote_currency)
        if self.payment_term == PaymentTerm.PREPAID:
            if rate_is_fcy: sell_amount = sell_amount_base
            else:
                sell_with_margin = self._apply_margin(sell_amount_base)
                margin_applied = True
                sell_amount = self._convert_pgk_to_fcy(sell_with_margin)
                fx_applied, caf_applied = True, True
        else:
            sell_amount = sell_amount_base
        
        margin_cost_base = cost_amount
        if self.payment_term == PaymentTerm.PREPAID and rate_is_fcy and cost_amount > 0:
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
            rule_family=sell_eval.rule_family if sell_eval.amount > 0 else cost_eval.rule_family,
        )

    def _create_default_line(self, pc: ProductCode, sell_amount: Decimal, notes: str) -> ChargeLineResult:
        sell_currency = 'PGK'
        if self.quote_currency != 'PGK':
            sell_amount = self._convert_pgk_to_fcy(sell_amount)
            sell_currency = self.quote_currency
        gst_category, gst_rate = get_png_gst_category(product_code=pc, shipment_type='EXPORT', leg='ORIGIN')
        gst_amount = (sell_amount * gst_rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        return ChargeLineResult(
            product_code_id=pc.id, product_code=pc.code, description=pc.description,
            category=pc.category, cost_amount=Decimal('0'), cost_currency='PGK',
            cost_source='Default', agent_name=None, sell_amount=sell_amount,
            sell_currency=sell_currency, margin_amount=sell_amount,
            margin_percent=Decimal('100.00'), gst_amount=gst_amount, sell_incl_gst=sell_amount+gst_amount,
            is_rate_missing=False, notes=notes, rule_family=CALCULATION_FLAT,
        )
    
    def _calculate_percentage_charge(self, product_code_id: int) -> Optional[ChargeLineResult]:
        pc = self._get_product_code(product_code_id); base_pc = pc.percent_of_product_code if pc else None
        if not pc or not base_pc: return None
        sell_rate = self._get_sell_rate(product_code_id)
        if not sell_rate or not sell_rate.percent_rate: return None
        base_sell = self._sell_cache.get(base_pc.id, Decimal('0')); base_cost = self._cost_cache.get(base_pc.id, Decimal('0'))
        percent_eval = evaluate_percent_of_base_rule(sell_rate.percent_rate, base_sell)
        cost_eval = evaluate_percent_of_base_rule(sell_rate.percent_rate, base_cost)
        sell_amount = percent_eval.amount
        cost_amount = cost_eval.amount
        margin_amount = sell_amount - cost_amount
        margin_percent = (margin_amount / cost_amount * 100) if cost_amount > 0 else Decimal('0')
        gst_category, gst_rate = get_png_gst_category(product_code=pc, shipment_type='EXPORT', leg='ORIGIN')
        gst_amount = (sell_amount * gst_rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        return ChargeLineResult(
            product_code_id=pc.id, product_code=pc.code,
            description=f"{pc.description} ({sell_rate.percent_rate}% of {base_pc.code})",
            category=pc.category, cost_amount=cost_amount, cost_currency='PGK',
            cost_source=f'{sell_rate.percent_rate}% of COGS', sell_amount=sell_amount,
            sell_currency=self.quote_currency, margin_amount=margin_amount, margin_percent=margin_percent,
            gst_category=gst_category, gst_rate=gst_rate, gst_amount=gst_amount, sell_incl_gst=sell_amount+gst_amount,
            is_rate_missing=False, notes=f'Based on {base_pc.code}: K{base_sell}', agent_name=None,
            rule_family=CALCULATION_PERCENT_OF_BASE,
        )
    
    def _calculate_amount(self, rate) -> RuleEvaluation:
        return evaluate_rate_lookup_rule(
            rate=rate,
            quantity=self.chargeable_weight_kg,
        )

    def _convert_amount_to_pgk(self, amount: Decimal, currency: str) -> Decimal:
        if currency == 'PGK':
            return amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        effective_rate = self._get_effective_fx_rate()
        if effective_rate <= 0:
            return amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        if effective_rate >= 1:
            pgk = amount * effective_rate
        else:
            pgk = amount / effective_rate
        return pgk.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    @staticmethod
    def _to_quote_line_item(line: ChargeLineResult) -> QuoteLineItem:
        leg = 'ORIGIN'
        if line.category == 'FREIGHT' or 'FRT' in line.product_code.upper():
            leg = 'FREIGHT'
        elif 'DEST' in line.product_code.upper() or 'DEST' in line.description.upper():
            leg = 'DESTINATION'
        component = QuoteComponent.ORIGIN_LOCAL
        if leg == 'FREIGHT':
            component = QuoteComponent.FREIGHT
        elif leg == 'DESTINATION':
            component = QuoteComponent.DESTINATION_LOCAL
        unit_type = 'KG' if leg == 'FREIGHT' else 'SHIPMENT'
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
            leg=leg,
            cost_amount=line.cost_amount,
            cost_currency=line.cost_currency,
            cost_source=normalize_cost_source(
                line.cost_source,
                is_spot_sourced=is_spot_sourced,
                is_manual_override=is_manual_override,
                is_rate_missing=line.is_rate_missing,
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
            included_in_total=not line.is_rate_missing,
            rate_source=normalize_rate_source(
                line.cost_source,
                is_spot_sourced=is_spot_sourced,
                is_manual_override=is_manual_override,
                is_rate_missing=line.is_rate_missing,
            ),
            calculation_notes=line.notes or None,
            is_spot_sourced=is_spot_sourced,
            is_manual_override=is_manual_override,
            is_rate_missing=line.is_rate_missing,
            notes=line.notes,
            fx_applied=line.fx_applied,
            caf_applied=line.caf_applied,
            margin_applied=line.margin_applied,
        )
