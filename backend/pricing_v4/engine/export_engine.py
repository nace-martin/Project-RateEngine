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
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List, Optional

from pricing_v4.models import ProductCode, ExportCOGS, ExportSellRate


@dataclass
class ChargeLineResult:
    """Result of a single charge line calculation."""
    product_code_id: int
    product_code: str
    description: str
    category: str
    
    # Cost values (what EFM pays)
    cost_amount: Decimal
    cost_currency: str
    cost_source: str  # 'COGS' or 'N/A' if no cost
    
    # Sell values (what EFM charges)
    sell_amount: Decimal
    sell_currency: str
    
    # Margin (calculated, not stored)
    margin_amount: Decimal
    margin_percent: Decimal
    
    # Tax
    gst_amount: Decimal
    sell_incl_gst: Decimal
    
    # Status
    is_rate_missing: bool
    notes: str


@dataclass
class QuoteResult:
    """Complete quote result."""
    origin: str
    destination: str
    quote_date: date
    chargeable_weight_kg: Decimal
    
    # Charge lines
    lines: List[ChargeLineResult]
    
    # Totals
    total_cost: Decimal
    total_sell: Decimal
    total_margin: Decimal
    total_gst: Decimal
    total_sell_incl_gst: Decimal
    
    # Currency
    currency: str


class ExportPricingEngine:
    """
    Calculates Export quotes.
    
    Rule 5: Simple queries, rules in code.
    Rule 9: Focused on POM→BNE corridor first.
    """
    
    def __init__(
        self,
        quote_date: date,
        origin: str,
        destination: str,
        chargeable_weight_kg: Decimal,
    ):
        self.quote_date = quote_date
        self.origin = origin
        self.destination = destination
        self.chargeable_weight_kg = chargeable_weight_kg
        
        # Cache for calculated values (needed for percentage surcharges)
        self._sell_cache: Dict[int, Decimal] = {}
        self._cost_cache: Dict[int, Decimal] = {}
    
    # =========================================================================
    # PUBLIC API
    # =========================================================================
    
    @staticmethod
    def get_product_codes(is_dg: bool = False) -> List[int]:
        """
        Get the list of ProductCode IDs to include in an Export quote.
        
        This is where conditional logic lives (Option A approach).
        ProductCodes are included/excluded based on shipment attributes.
        
        Args:
            is_dg: True if shipment contains dangerous goods
            
        Returns:
            List of ProductCode IDs to quote
        """
        # Standard Export charges (always included)
        codes = [
            1001,  # EXP-FRT-AIR - Air Freight
            1010,  # EXP-DOC - Documentation
            1011,  # EXP-AWB - AWB Fee
            1020,  # EXP-CLEAR - Customs Clearance
            1021,  # EXP-AGENCY - Agency Fee
            1030,  # EXP-TERM - Terminal Handling
            1031,  # EXP-BUILDUP - Build-Up
            1040,  # EXP-SCREEN - Security Screening
            1050,  # EXP-PICKUP - Pickup/Collection
            1060,  # EXP-FSC-PICKUP - Fuel Surcharge on Pickup
        ]
        
        # Conditional charges
        if is_dg:
            codes.append(1070)  # EXP-DG - DG Acceptance
        
        return codes
    
    def calculate_quote(self, product_code_ids: List[int]) -> QuoteResult:
        """
        Calculate a complete quote for the given product codes.
        
        Args:
            product_code_ids: List of ProductCode IDs to include in quote
            
        Returns:
            QuoteResult with all charge lines and totals
        """
        # OPTIMIZATION: Prefetch rates to prevent N+1 queries
        self._prefetch_rates(product_code_ids)
        
        lines = []
        
        # First pass: calculate all non-percentage charges
        regular_ids = []
        percent_ids = []
        
        for pc_id in product_code_ids:
            pc = self._get_product_code(pc_id)
            if pc and pc.default_unit == ProductCode.UNIT_PERCENT:
                percent_ids.append(pc_id)
            else:
                regular_ids.append(pc_id)
        
        # Calculate regular charges first
        for pc_id in regular_ids:
            line = self._calculate_charge_line(pc_id)
            if line:
                lines.append(line)
                # Cache for percentage calculations
                self._sell_cache[pc_id] = line.sell_amount
                self._cost_cache[pc_id] = line.cost_amount
        
        # Calculate percentage-based surcharges
        for pc_id in percent_ids:
            line = self._calculate_percentage_charge(pc_id)
            if line:
                lines.append(line)
        
        # Calculate totals
        total_cost = sum(line.cost_amount for line in lines)
        total_sell = sum(line.sell_amount for line in lines)
        total_margin = sum(line.margin_amount for line in lines)
        total_gst = sum(line.gst_amount for line in lines)
        total_sell_incl_gst = sum(line.sell_incl_gst for line in lines)
        
        return QuoteResult(
            origin=self.origin,
            destination=self.destination,
            quote_date=self.quote_date,
            chargeable_weight_kg=self.chargeable_weight_kg,
            lines=lines,
            total_cost=total_cost,
            total_sell=total_sell,
            total_margin=total_margin,
            total_gst=total_gst,
            total_sell_incl_gst=total_sell_incl_gst,
            currency='PGK',
        )
    
    # =========================================================================
    # SIMPLE LOOKUPS (Rule 5: No business logic in ORM)
    # =========================================================================
    
    def _prefetch_rates(self, product_code_ids: List[int]):
        """Load all necessary rate data into memory."""
        self._pc_cache = {}
        self._cogs_rate_cache = {}
        self._sell_rate_cache = {}
        
        # 1. ProductCodes
        pcs = ProductCode.objects.filter(id__in=product_code_ids)
        for pc in pcs:
            self._pc_cache[pc.id] = pc
            
        # 2. ExportCOGS
        cogs_qs = ExportCOGS.objects.filter(
            product_code_id__in=product_code_ids,
            origin_airport=self.origin,
            destination_airport=self.destination,
            valid_from__lte=self.quote_date,
            valid_until__gte=self.quote_date
        )
        for rate in cogs_qs:
            self._cogs_rate_cache[rate.product_code_id] = rate
            
        # 3. ExportSellRate
        sell_qs = ExportSellRate.objects.filter(
            product_code_id__in=product_code_ids,
            origin_airport=self.origin,
            destination_airport=self.destination,
            valid_from__lte=self.quote_date,
            valid_until__gte=self.quote_date
        )
        for rate in sell_qs:
            self._sell_rate_cache[rate.product_code_id] = rate

    def _get_product_code(self, product_code_id: int) -> Optional[ProductCode]:
        """Simple lookup. No business logic."""
        if hasattr(self, '_pc_cache') and product_code_id in self._pc_cache:
            return self._pc_cache[product_code_id]
        if hasattr(self, '_pc_cache'):
            # Cache active but item not found -> fallback to DB slightly safer or just return None?
            # Existing logic handled DoesNotExist.
            # If we prefetch, we should trust it, but for safety, fallback if critical.
            # Actually, prefetch uses id_in, so it should catch everything that exists.
            return None
            
        try:
            return ProductCode.objects.get(id=product_code_id)
        except ProductCode.DoesNotExist:
            return None
    
    def _get_cogs(self, product_code_id: int) -> Optional[ExportCOGS]:
        """Simple lookup. No business logic."""
        if hasattr(self, '_cogs_rate_cache') and product_code_id in self._cogs_rate_cache:
            return self._cogs_rate_cache[product_code_id]
        if hasattr(self, '_cogs_rate_cache'):
            return None

        return ExportCOGS.objects.filter(
            product_code_id=product_code_id,
            origin_airport=self.origin,
            destination_airport=self.destination,
            valid_from__lte=self.quote_date,
            valid_until__gte=self.quote_date,
        ).first()
    
    def _get_sell_rate(self, product_code_id: int) -> Optional[ExportSellRate]:
        """Simple lookup. No business logic."""
        if hasattr(self, '_sell_rate_cache') and product_code_id in self._sell_rate_cache:
            return self._sell_rate_cache[product_code_id]
        if hasattr(self, '_sell_rate_cache'):
            return None
            
        return ExportSellRate.objects.filter(
            product_code_id=product_code_id,
            origin_airport=self.origin,
            destination_airport=self.destination,
            valid_from__lte=self.quote_date,
            valid_until__gte=self.quote_date,
        ).first()
    
    # =========================================================================
    # PRICING RULES (in Python code, not ORM)
    # =========================================================================
    
    def _calculate_charge_line(self, product_code_id: int) -> Optional[ChargeLineResult]:
        """
        Calculate a single charge line.
        
        Pricing rules are in code, readable top-to-bottom.
        """
        # 1. Get ProductCode (required)
        pc = self._get_product_code(product_code_id)
        if not pc:
            return None
        
        # 2. Get COGS (optional - some charges are sell-only)
        cogs = self._get_cogs(product_code_id)
        
        # 3. Get Sell Rate (required)
        sell_rate = self._get_sell_rate(product_code_id)
        if not sell_rate:
            return ChargeLineResult(
                product_code_id=pc.id,
                product_code=pc.code,
                description=pc.description,
                category=pc.category,
                cost_amount=Decimal('0'),
                cost_currency='PGK',
                cost_source='N/A',
                sell_amount=Decimal('0'),
                sell_currency='PGK',
                margin_amount=Decimal('0'),
                margin_percent=Decimal('0'),
                gst_amount=Decimal('0'),
                sell_incl_gst=Decimal('0'),
                is_rate_missing=True,
                notes=f"No sell rate found for {pc.code}",
            )
        
        # 4. Calculate COGS amount
        if cogs:
            cost_amount = self._calculate_amount(cogs)
            cost_source = 'COGS'
        else:
            cost_amount = Decimal('0')
            cost_source = 'N/A (Sell Only)'
        
        # 5. Calculate Sell amount
        sell_amount = self._calculate_amount(sell_rate)
        
        # 6. Calculate Margin
        margin_amount = sell_amount - cost_amount
        margin_percent = (
            (margin_amount / cost_amount * 100) if cost_amount > 0 else Decimal('0')
        )
        
        # 7. Calculate GST
        if pc.is_gst_applicable:
            gst_amount = (sell_amount * pc.gst_rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        else:
            gst_amount = Decimal('0')
        
        sell_incl_gst = sell_amount + gst_amount
        
        return ChargeLineResult(
            product_code_id=pc.id,
            product_code=pc.code,
            description=pc.description,
            category=pc.category,
            cost_amount=cost_amount,
            cost_currency=cogs.currency if cogs else 'PGK',
            cost_source=cost_source,
            sell_amount=sell_amount,
            sell_currency=sell_rate.currency,
            margin_amount=margin_amount,
            margin_percent=margin_percent.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
            gst_amount=gst_amount,
            sell_incl_gst=sell_incl_gst,
            is_rate_missing=False,
            notes='',
        )
    
    def _calculate_percentage_charge(self, product_code_id: int) -> Optional[ChargeLineResult]:
        """
        Calculate a percentage-based surcharge.
        
        Example: FSC = 10% of Pickup charge
        """
        # 1. Get ProductCode
        pc = self._get_product_code(product_code_id)
        if not pc:
            return None
        
        # 2. Get base ProductCode (what this is a percentage of)
        base_pc = pc.percent_of_product_code
        if not base_pc:
            return ChargeLineResult(
                product_code_id=pc.id,
                product_code=pc.code,
                description=pc.description,
                category=pc.category,
                cost_amount=Decimal('0'),
                cost_currency='PGK',
                cost_source='N/A',
                sell_amount=Decimal('0'),
                sell_currency='PGK',
                margin_amount=Decimal('0'),
                margin_percent=Decimal('0'),
                gst_amount=Decimal('0'),
                sell_incl_gst=Decimal('0'),
                is_rate_missing=True,
                notes=f"No base product code for percentage calculation",
            )
        
        # 3. Get sell rate for percentage
        sell_rate = self._get_sell_rate(product_code_id)
        if not sell_rate or not sell_rate.percent_rate:
            return ChargeLineResult(
                product_code_id=pc.id,
                product_code=pc.code,
                description=pc.description,
                category=pc.category,
                cost_amount=Decimal('0'),
                cost_currency='PGK',
                cost_source='N/A',
                sell_amount=Decimal('0'),
                sell_currency='PGK',
                margin_amount=Decimal('0'),
                margin_percent=Decimal('0'),
                gst_amount=Decimal('0'),
                sell_incl_gst=Decimal('0'),
                is_rate_missing=True,
                notes=f"No percent_rate found for {pc.code}",
            )
        
        # 4. Get base amount from cache
        base_sell = self._sell_cache.get(base_pc.id, Decimal('0'))
        base_cost = self._cost_cache.get(base_pc.id, Decimal('0'))
        
        # 5. Calculate surcharge
        percent = sell_rate.percent_rate / Decimal('100')
        sell_amount = (base_sell * percent).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        cost_amount = (base_cost * percent).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        
        # 6. Calculate Margin
        margin_amount = sell_amount - cost_amount
        margin_percent = (
            (margin_amount / cost_amount * 100) if cost_amount > 0 else Decimal('0')
        )
        
        # 7. Calculate GST
        if pc.is_gst_applicable:
            gst_amount = (sell_amount * pc.gst_rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        else:
            gst_amount = Decimal('0')
        
        sell_incl_gst = sell_amount + gst_amount
        
        return ChargeLineResult(
            product_code_id=pc.id,
            product_code=pc.code,
            description=f"{pc.description} ({sell_rate.percent_rate}% of {base_pc.code})",
            category=pc.category,
            cost_amount=cost_amount,
            cost_currency='PGK',
            cost_source=f'{sell_rate.percent_rate}% of COGS',
            sell_amount=sell_amount,
            sell_currency=sell_rate.currency,
            margin_amount=margin_amount,
            margin_percent=margin_percent.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP) if cost_amount > 0 else Decimal('0'),
            gst_amount=gst_amount,
            sell_incl_gst=sell_incl_gst,
            is_rate_missing=False,
            notes=f'Based on {base_pc.code}: K{base_sell}',
        )
    
    def _calculate_amount(self, rate) -> Decimal:
        """
        Calculate amount from a rate record.
        
        Pricing rules:
        1. Weight breaks take precedence
        2. If is_additive: per-kg + per-shipment combined
        3. Otherwise: per-kg rate × weight OR flat per-shipment
        4. Apply min/max constraints (unless additive)
        """
        weight = self.chargeable_weight_kg
        zero = Decimal('0')
        
        # Weight break pricing (takes precedence)
        if rate.weight_breaks:
            amount = self._calculate_weight_break(rate.weight_breaks, weight)
        # ADDITIVE: per-kg + flat fee combined (e.g., Security Screening)
        elif getattr(rate, 'is_additive', False) and rate.rate_per_kg and rate.rate_per_shipment:
            kg_amount = weight * rate.rate_per_kg
            flat_amount = rate.rate_per_shipment
            amount = kg_amount + flat_amount
            # For additive, skip min/max
            return amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        elif rate.rate_per_kg:
            amount = weight * rate.rate_per_kg
        elif rate.rate_per_shipment:
            amount = rate.rate_per_shipment
        else:
            amount = zero
        
        # Apply minimum
        if rate.min_charge and amount < rate.min_charge:
            amount = rate.min_charge
        
        # Apply maximum
        if rate.max_charge and amount > rate.max_charge:
            amount = rate.max_charge
        
        return amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    
    def _calculate_weight_break(self, breaks: list, weight: Decimal) -> Decimal:
        """
        Find applicable rate from weight break tiers.
        
        Weight breaks format: [{"min_kg": 0, "rate": "6.30"}, ...]
        """
        if not breaks:
            return Decimal('0')
        
        # Sort breaks descending by min_kg
        sorted_breaks = sorted(
            breaks,
            key=lambda x: Decimal(str(x.get('min_kg', 0))),
            reverse=True,
        )
        
        # Find first tier where weight >= min_kg
        for tier in sorted_breaks:
            min_kg = Decimal(str(tier.get('min_kg', 0)))
            if weight >= min_kg:
                rate_per_kg = Decimal(str(tier.get('rate', 0)))
                return weight * rate_per_kg
        
        # Fallback to lowest tier
        if sorted_breaks:
            rate_per_kg = Decimal(str(sorted_breaks[-1].get('rate', 0)))
            return weight * rate_per_kg
        
        return Decimal('0')
