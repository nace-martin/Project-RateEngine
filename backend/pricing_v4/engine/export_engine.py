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
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List, Optional
from enum import Enum

from pricing_v4.models import (
    ProductCode, ExportCOGS, ExportSellRate,
    LocalSellRate, LocalCOGSRate
)
from quotes.tax_policy import get_png_gst_category

# Categories that are location-based (not lane-based)
LOCAL_CATEGORIES = ['CLEARANCE', 'CARTAGE', 'HANDLING', 'DOCUMENTATION', 'SCREENING']


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
    
    Payment Term determines quote currency:
    - PREPAID: Quote in PGK (shipper in PNG pays)
    - COLLECT: Quote in FCY (consignee abroad pays) with CAF/margin applied
    
    For COLLECT, PGK amounts are converted to FCY using:
    - effective_rate = tt_sell × (1 + CAF)  # CAF is ADDED for Export
    - fcy_amount = pgk_amount × effective_rate
    """
    
    # Default rates
    DEFAULT_MARGIN = Decimal('0.20')  # 20%
    DEFAULT_CAF = Decimal('0.05')     # 5%
    
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
        """
        Payment Term determines quote currency.
        Export PREPAID = PGK (shipper in PNG pays)
        Export COLLECT = FCY (consignee abroad pays)
        """
        if self.payment_term == PaymentTerm.COLLECT:
            return self.destination_currency
        return 'PGK'
    
    def _convert_pgk_to_fcy(self, amount: Decimal) -> Decimal:
        """
        PGK → FCY conversion for Export COLLECT.
        
        FX Rate Convention:
        - Rates are stored as "PGK per 1 FCY" (e.g., TT_SELL = 2.78 means 1 AUD = 2.78 PGK)
        - To convert PGK to FCY, we DIVIDE: AUD = PGK / TT_SELL
        
        CAF for Export:
        - CAF is ADDED to make the effective rate higher (less favorable for customer)
        - This results in a smaller FCY amount for the same PGK value
        - effective_rate = TT_SELL × (1 + CAF)
        - fcy_amount = PGK / effective_rate
        
        Example:
        - PGK 100, TT_SELL = 2.78, CAF = 5%
        - effective_rate = 2.78 × 1.05 = 2.919
        - AUD = 100 / 2.919 = 34.26 AUD
        """
        effective_rate = self.tt_sell * (Decimal('1') + self.caf_rate)
        fcy = amount / effective_rate
        return fcy.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    
    def _apply_margin(self, amount: Decimal) -> Decimal:
        """Apply margin (always last)."""
        return (amount * (Decimal('1') + self.margin_rate)).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP
        )
    
    def _get_effective_fx_rate(self) -> Decimal:
        """Get effective FX rate with CAF applied."""
        return self.tt_sell * (Decimal('1') + self.caf_rate)
    
    # =========================================================================
    # PUBLIC API
    # =========================================================================
    
    @staticmethod
    def get_product_codes(is_dg: bool = False, service_scope: str = 'P2P') -> List[int]:
        """
        Get the list of ProductCode IDs to include in an Export quote.
        
        This is where conditional logic lives (Option A approach).
        ProductCodes are included/excluded based on shipment attributes.
        
        Args:
            is_dg: True if shipment contains dangerous goods
            service_scope: 'P2P' (Port to Port), 'D2A' (Door to Airport),
                'D2D' (Door to Door), 'A2D' (Airport to Door)
            
        Returns:
            List of ProductCode IDs to quote
        """

        if service_scope == 'A2A':
            service_scope = 'P2P'

        # Standard Export charges (always included in all scopes)
        codes = [
            1001,  # EXP-FRT-AIR - Air Freight
            1010,  # EXP-DOC - Documentation
            1011,  # EXP-AWB - AWB Fee
            1021,  # EXP-AGENCY - Agency Fee
            1030,  # EXP-TERM - Terminal Handling
            1031,  # EXP-BUILDUP - Build-Up
            1032,  # EXP-HANDLE - Handling Fee
            1040,  # EXP-SCREEN - Security Screening
            1050,  # EXP-PICKUP - Pickup/Collection (Requested to be always applied)
            1060,  # EXP-FSC-PICKUP - Fuel Surcharge on Pickup (Requested to be always applied)
        ]
        
        # Origin Pickup (D2A, D2D)
        if service_scope in ('D2A', 'D2D'):
            codes.append(1020)  # EXP-CLEAR - Customs Clearance (Origin)
        
        # Destination Charges (D2D, A2D)
        if service_scope in ('D2D', 'A2D'):
            codes.append(1080)  # EXP-CLEAR-DEST
            codes.append(1081)  # EXP-DELIVERY-DEST
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
            currency=self.quote_currency,
            quote_currency=self.quote_currency,
            payment_term=self.payment_term.value if hasattr(self.payment_term, 'value') else str(self.payment_term),
            fx_rate_used=self.tt_sell if self.payment_term == PaymentTerm.COLLECT else None,
            effective_fx_rate=self._get_effective_fx_rate() if self.payment_term == PaymentTerm.COLLECT else None,
            caf_rate=self.caf_rate if self.payment_term == PaymentTerm.COLLECT else None,
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
        ).select_related('agent')  # OPTIMIZATION: Fetch Agent to display provider name
        for rate in cogs_qs:
            self._cogs_rate_cache[rate.product_code_id] = rate
            
        # 3. ExportSellRate - with FCY preference for COLLECT
        # For COLLECT: Prefer FCY (quote_currency) rates, fallback to PGK
        # For PREPAID: Use PGK rates
        sell_qs = ExportSellRate.objects.filter(
            product_code_id__in=product_code_ids,
            origin_airport=self.origin,
            destination_airport=self.destination,
            valid_from__lte=self.quote_date,
            valid_until__gte=self.quote_date
        )
        
        # Group by product_code to allow currency preference
        for rate in sell_qs:
            pc_id = rate.product_code_id
            
            if self.payment_term == PaymentTerm.COLLECT:
                # For COLLECT: Prefer FCY rate (quote_currency), fallback to PGK
                if rate.currency == self.quote_currency:
                    # FCY rate found - use it (will skip conversion later)
                    self._sell_rate_cache[pc_id] = rate
                elif pc_id not in self._sell_rate_cache:
                    # No FCY rate yet - use PGK as fallback
                    self._sell_rate_cache[pc_id] = rate
            else:
                # For PREPAID: Prefer PGK rates
                if rate.currency == 'PGK':
                    self._sell_rate_cache[pc_id] = rate
                elif pc_id not in self._sell_rate_cache:
                    self._sell_rate_cache[pc_id] = rate

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
        """
        Get COGS for a product code.
        Routes to LocalCOGSRate for local categories, ExportCOGS for freight.
        """
        # Check if this is a local category
        pc = self._get_product_code(product_code_id)
        if pc and pc.category in LOCAL_CATEGORIES:
            return self._get_local_cogs(product_code_id)
        
        # Lane-based lookup for FREIGHT
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
    
    def _get_local_cogs(self, product_code_id: int) -> Optional[ExportCOGS]:
        """
        Lookup local COGS from centralized table (by origin, direction=EXPORT).
        Falls back to legacy ExportCOGS table if no LocalCOGSRate is found.
        """
        # Try new LocalCOGSRate table first
        local_rate = LocalCOGSRate.objects.filter(
            product_code_id=product_code_id,
            location=self.origin,
            direction='EXPORT',
            valid_from__lte=self.quote_date,
            valid_until__gte=self.quote_date
        ).first()
        
        if local_rate:
            return local_rate
        
        # Fallback: Check legacy ExportCOGS table (lane-based)
        # This ensures backward compatibility during migration
        return ExportCOGS.objects.filter(
            product_code_id=product_code_id,
            origin_airport=self.origin,
            destination_airport=self.destination,
            valid_from__lte=self.quote_date,
            valid_until__gte=self.quote_date,
        ).first()
    
    def _get_sell_rate(self, product_code_id: int) -> Optional[ExportSellRate]:
        """
        Get Sell Rate for a product code.
        Routes to LocalSellRate for local categories, ExportSellRate for freight.
        """
        # Check if this is a local category
        pc = self._get_product_code(product_code_id)
        if pc and pc.category in LOCAL_CATEGORIES:
            return self._get_local_sell_rate(product_code_id)
        
        # Lane-based lookup for FREIGHT
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
    
    def _get_local_sell_rate(self, product_code_id: int) -> Optional[ExportSellRate]:
        """
        Lookup local sell rate from centralized table.
        Falls back to legacy ExportSellRate table if no LocalSellRate is found.
        
        Priority: Exact payment_term match first, then fallback to 'ANY'.
        """
        payment_term_value = self.payment_term.value if hasattr(self.payment_term, 'value') else str(self.payment_term)
        
        # Try new LocalSellRate table first
        base_qs = LocalSellRate.objects.filter(
            product_code_id=product_code_id,
            location=self.origin,
            direction='EXPORT',
            payment_term__in=[payment_term_value, 'ANY'],
            valid_from__lte=self.quote_date,
            valid_until__gte=self.quote_date
        )

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
        
        # Fallback: Check legacy ExportSellRate table (lane-based)
        # This ensures backward compatibility during migration
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
        For COLLECT, PGK amounts are converted to FCY with CAF and margin.
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
                agent_name=None,
                sell_amount=Decimal('0'),
                sell_currency=self.quote_currency,
                margin_amount=Decimal('0'),
                margin_percent=Decimal('0'),
                gst_amount=Decimal('0'),
                sell_incl_gst=Decimal('0'),
                is_rate_missing=True,
                notes=f"No sell rate found for {pc.code}",
            )
        
        # 4. Calculate COGS amount (always in PGK for Export)
        agent_name = None
        if cogs:
            cost_amount = self._calculate_amount(cogs)
            cost_source = 'COGS'
            if cogs.agent:
                agent_name = cogs.agent.name
        else:
            cost_amount = Decimal('0')
            cost_source = 'N/A (Sell Only)'
        
        # 5. Calculate Sell amount
        sell_amount_base = self._calculate_amount(sell_rate)
        
        # 6. Determine if FCY conversion is needed
        # If sell_rate is already in quote_currency (FCY), use directly
        # If sell_rate is in PGK and we need FCY (COLLECT), convert
        fx_applied = False
        caf_applied = False
        margin_applied = False
        
        rate_is_fcy = (sell_rate.currency == self.quote_currency)
        
        if self.payment_term == PaymentTerm.COLLECT:
            if rate_is_fcy:
                # FCY rate found - use directly, no conversion needed
                sell_amount = sell_amount_base
                sell_currency = sell_rate.currency
                # No FX conversion, but we may still want margin applied
                # For FCY rates, assume margin is already built into the rate card
            else:
                # PGK rate - need to convert to FCY
                # Step 1: Apply margin to PGK amount first
                sell_with_margin = self._apply_margin(sell_amount_base)
                margin_applied = True
                
                # Step 2: Convert PGK → FCY with CAF
                sell_amount = self._convert_pgk_to_fcy(sell_with_margin)
                fx_applied = True
                caf_applied = True
                sell_currency = self.quote_currency
        else:
            # PREPAID: Keep in PGK, no FX conversion needed
            sell_amount = sell_amount_base
            sell_currency = 'PGK'
        
        # 7. Calculate Margin for display
        # For COLLECT with PGK→FCY conversion, margin was applied before conversion
        # For COLLECT with FCY rate, margin is built into the rate card
        if margin_applied:
            margin_base = sell_amount_base * self.margin_rate
            margin_amount = margin_base if not fx_applied else self._convert_pgk_to_fcy(margin_base)
            margin_cost_base = cost_amount
        else:
            # FCY rate or PREPAID - calculate margin as difference
            # For COLLECT with FCY sell rates, convert cost to quote currency for margin display.
            margin_cost_base = cost_amount
            if self.payment_term == PaymentTerm.COLLECT and rate_is_fcy and cost_amount > 0:
                margin_cost_base = self._convert_pgk_to_fcy(cost_amount)
            margin_amount = sell_amount - margin_cost_base
        
        margin_percent = (
            (self.margin_rate * 100) if margin_applied else
            ((sell_amount - margin_cost_base) / margin_cost_base * 100 if margin_cost_base > 0 else Decimal('0'))
        )
        
        # 8. Calculate GST using PNG classification
        gst_category, gst_rate = get_png_gst_category(
            product_code=pc,
            shipment_type='EXPORT',
            leg='ORIGIN'  # Export origin services
        )
        gst_amount = (sell_amount * gst_rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        sell_incl_gst = sell_amount + gst_amount
        
        return ChargeLineResult(
            product_code_id=pc.id,
            product_code=pc.code,
            description=pc.description,
            category=pc.category,
            cost_amount=cost_amount,
            cost_currency=cogs.currency if cogs else 'PGK',
            cost_source=cost_source,
            agent_name=agent_name,
            sell_amount=sell_amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
            sell_currency=sell_currency,
            margin_amount=margin_amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
            margin_percent=margin_percent.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP) if isinstance(margin_percent, Decimal) else Decimal(str(margin_percent)).quantize(Decimal('0.01')),
            gst_category=gst_category,
            gst_rate=gst_rate,
            gst_amount=gst_amount,
            sell_incl_gst=sell_incl_gst,
            is_rate_missing=False,
            notes='',
            fx_applied=fx_applied,
            caf_applied=caf_applied,
            margin_applied=margin_applied,
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
                agent_name=None,
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
                agent_name=None,
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
        
        # 7. Calculate GST using PNG classification
        gst_category, gst_rate = get_png_gst_category(
            product_code=pc,
            shipment_type='EXPORT',
            leg='ORIGIN'  # Export percentage surcharges are origin-based
        )
        gst_amount = (sell_amount * gst_rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
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
            gst_category=gst_category,
            gst_rate=gst_rate,
            gst_amount=gst_amount,
            sell_incl_gst=sell_incl_gst,
            is_rate_missing=False,
            notes=f'Based on {base_pc.code}: K{base_sell}',
            agent_name=None,
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
