"""
Spot Bucket Calculator - 5-Pass Pricing Engine for Freeform Spot Charges

This module implements the bucket-based pricing calculation for spot rates,
following the business rules for FX conversion, CAF, and margin application.

PASS 1: Normalize base costs (FCY → PGK using FX BUY, multiply PER_KG by CW)
PASS 2: Calculate percentage-based lines against base costs
PASS 3: Apply CAF/buffer per bucket
PASS 4: Apply margin per bucket  
PASS 5: Convert sell totals to FCY if quoting currency is foreign
"""

import logging
from decimal import Decimal
from typing import Dict, List, Optional

from django.db.models import QuerySet

from quotes.models import Quote, SpotChargeLine
from core.models import FxSnapshot, Policy

logger = logging.getLogger(__name__)


class SpotBucketCalculator:
    """
    Calculates sell-side totals from freeform spot charge lines.
    Implements the 5-pass pricing logic with FX/CAF/margin rules.
    """
    
    # CAF rates by scenario
    CAF_IMPORT_DEFAULT = Decimal('0.05')  # 5% for imports
    CAF_EXPORT_DAP_DEST = Decimal('0.10')  # 10% for export DAP destination charges
    CAF_EXPORT_DEFAULT = Decimal('0.00')  # No CAF for export D2A
    
    # Default margin
    MARGIN_DEFAULT = Decimal('0.20')  # 20%
    MARGIN_PASSTHROUGH = Decimal('0.00')  # 0% for collect/passthrough
    
    def __init__(self, quote: Quote):
        self.quote = quote
        self.fx_snapshot = quote.fx_snapshot or FxSnapshot.objects.filter(is_current=True).first()
        self.policy = quote.policy or Policy.objects.first()
        
        if not self.fx_snapshot:
            raise ValueError("No FX snapshot available for calculation")
        
        # Get chargeable weight from quote's request details
        self.chargeable_weight = self._calculate_chargeable_weight()
        
        # Determine quoting currency based on scenario
        self.quoting_currency = self._determine_quoting_currency()
        
    def _calculate_chargeable_weight(self) -> Decimal:
        """Calculate chargeable weight from quote dimensions."""
        request_data = self.quote.request_details_json or {}
        dimensions = request_data.get('dimensions', [])
        
        total_actual = Decimal('0')
        total_volumetric = Decimal('0')
        
        for dim in dimensions:
            pieces = Decimal(str(dim.get('pieces', 1)))
            length = Decimal(str(dim.get('length_cm', 0)))
            width = Decimal(str(dim.get('width_cm', 0)))
            height = Decimal(str(dim.get('height_cm', 0)))
            gross_weight = Decimal(str(dim.get('gross_weight_kg', 0)))
            
            total_actual += pieces * gross_weight
            # Volumetric = (L × W × H) / 6000 per piece
            if length > 0 and width > 0 and height > 0:
                vol_per_piece = (length * width * height) / Decimal('6000')
                total_volumetric += pieces * vol_per_piece
        
        # Chargeable weight = max(actual, volumetric)
        return max(total_actual, total_volumetric)
    
    def _determine_quoting_currency(self) -> str:
        """
        Determine quoting currency based on shipment scenario.
        
        Rules:
        - Import Collect D2D → PGK
        - Import Collect A2D → PGK
        - Import Prepaid A2D → FCY (USD/AUD based on origin)
        - Export Prepaid D2A → PGK
        - Export Prepaid D2D (DAP) → PGK
        - Export Collect D2A (FCA) → FCY
        """
        direction = self.quote.shipment_type  # IMPORT or EXPORT
        payment_term = self.quote.payment_term  # PREPAID or COLLECT
        scope = self.quote.service_scope  # D2D, A2D, D2A
        incoterm = (self.quote.incoterm or '').upper()
        
        if direction == 'IMPORT':
            if payment_term == 'PREPAID' and scope == 'A2D':
                # Import Prepaid A2D → FCY
                origin = self.quote.origin_location
                if origin and origin.country:
                    if origin.country.code == 'AU':
                        return 'AUD'
                return 'USD'
            # All other imports → PGK
            return 'PGK'
        
        elif direction == 'EXPORT':
            if payment_term == 'COLLECT' and scope == 'D2A':
                # Export Collect D2A (FCA) → FCY
                dest = self.quote.destination_location
                if dest and dest.country and dest.country.currency:
                    return dest.country.currency.code
                return 'USD'
            # All other exports → PGK
            return 'PGK'
        
        return 'PGK'
    
    def _get_rates_dict(self) -> dict:
        """Get rates dictionary from FxSnapshot."""
        rates = self.fx_snapshot.rates
        if isinstance(rates, str):
            import json
            return json.loads(rates)
        return rates or {}
    
    def _get_fx_buy_rate(self, currency: str) -> Decimal:
        """
        Get FX BUY rate for converting FCY → PGK.
        Returns how many PGK to pay for 1 FCY.
        """
        if currency == 'PGK':
            return Decimal('1')
        
        rates = self._get_rates_dict()
        info = rates.get(currency)
        if info and info.get('tt_buy'):
            return Decimal(str(info['tt_buy']))
        
        logger.warning(f"No FX BUY rate found for {currency}, using 1.0")
        return Decimal('1')
    
    def _get_fx_sell_rate(self, currency: str) -> Decimal:
        """
        Get FX SELL rate for converting PGK → FCY.
        Returns how many PGK needed to get 1 FCY (we then divide by this).
        """
        if currency == 'PGK':
            return Decimal('1')
        
        rates = self._get_rates_dict()
        info = rates.get(currency)
        if info and info.get('tt_sell'):
            return Decimal(str(info['tt_sell']))
        
        logger.warning(f"No FX SELL rate found for {currency}, using 1.0")
        return Decimal('1')
    
    def _get_caf_rates(self) -> Dict[str, Decimal]:
        """
        Get CAF rates per bucket based on scenario.
        
        Rules:
        - Import Collect D2D: 5% on all buckets (foreign costs)
        - Export DAP D2D: 10% on destination bucket only
        - Export Collect D2A (FCA): 0% (pass-through)
        """
        direction = self.quote.shipment_type
        payment_term = self.quote.payment_term
        scope = self.quote.service_scope
        incoterm = (self.quote.incoterm or '').upper()
        
        # Default: use policy CAF rates
        caf_import = Decimal(str(self.policy.caf_import_pct)) if self.policy else self.CAF_IMPORT_DEFAULT
        caf_export = Decimal(str(self.policy.caf_export_pct)) if self.policy else self.CAF_EXPORT_DEFAULT
        
        if direction == 'IMPORT':
            # Import: apply CAF to origin and freight (foreign costs)
            return {
                'ORIGIN': caf_import,
                'FREIGHT': caf_import,
                'DESTINATION': Decimal('0'),  # Destination is local PGK
            }
        
        elif direction == 'EXPORT':
            if scope == 'D2D' and incoterm == 'DAP':
                # Export DAP D2D: 10% CAF on destination (foreign costs)
                return {
                    'ORIGIN': Decimal('0'),  # Origin is local PGK
                    'FREIGHT': Decimal('0'),
                    'DESTINATION': caf_export,
                }
            else:
                # Export D2A or other: no CAF
                return {
                    'ORIGIN': Decimal('0'),
                    'FREIGHT': Decimal('0'),
                    'DESTINATION': Decimal('0'),
                }
        
        return {
            'ORIGIN': Decimal('0'),
            'FREIGHT': Decimal('0'),
            'DESTINATION': Decimal('0'),
        }
    
    def _get_margin_rates(self) -> Dict[str, Decimal]:
        """
        Get margin rates per bucket based on scenario.
        
        Rules:
        - Default: 20% margin on all buckets
        - Export Collect D2A (FCA): 0% margin (pass-through to consignee)
        """
        direction = self.quote.shipment_type
        payment_term = self.quote.payment_term
        scope = self.quote.service_scope
        
        # Default margin from policy
        default_margin = Decimal(str(self.policy.margin_pct)) if self.policy else self.MARGIN_DEFAULT
        
        if direction == 'EXPORT' and payment_term == 'COLLECT' and scope == 'D2A':
            # Export Collect D2A: pass-through (0% margin)
            return {
                'ORIGIN': Decimal('0'),
                'FREIGHT': Decimal('0'),
                'DESTINATION': Decimal('0'),
            }
        
        return {
            'ORIGIN': default_margin,
            'FREIGHT': default_margin,
            'DESTINATION': default_margin,
        }
    
    def calculate(self) -> dict:
        """
        Execute the 5-pass pricing calculation.
        
        Returns a dict with bucket totals and grand totals in PGK and FCY.
        """
        lines = list(self.quote.spot_charges.all())
        
        # Initialize storage for line costs
        line_costs_pgk: Dict[str, Decimal] = {}  # line.id -> cost in PGK
        
        # ========== PASS 1: Normalize base costs ==========
        bucket_base_costs = {
            'ORIGIN': Decimal('0'),
            'FREIGHT': Decimal('0'),
            'DESTINATION': Decimal('0'),
        }
        
        non_percentage_lines = [l for l in lines if l.unit_basis != SpotChargeLine.UnitBasis.PERCENTAGE]
        
        for line in non_percentage_lines:
            cost_pgk = self._calculate_line_cost_pgk(line)
            line_costs_pgk[str(line.id)] = cost_pgk
            bucket_base_costs[line.bucket] += cost_pgk
        
        logger.info(f"PASS 1 - Base costs: {bucket_base_costs}")
        
        # ========== PASS 2: Calculate percentage-based lines ==========
        percentage_lines = [l for l in lines if l.unit_basis == SpotChargeLine.UnitBasis.PERCENTAGE]
        
        for line in percentage_lines:
            base_pgk = self._get_percentage_base(line, bucket_base_costs, line_costs_pgk)
            percentage = line.percentage or Decimal('0')
            cost_pgk = base_pgk * (percentage / Decimal('100'))
            
            line_costs_pgk[str(line.id)] = cost_pgk
            bucket_base_costs[line.bucket] += cost_pgk
        
        logger.info(f"PASS 2 - After percentages: {bucket_base_costs}")
        
        # ========== PASS 3: Apply CAF ==========
        caf_rates = self._get_caf_rates()
        bucket_buffered = {}
        
        for bucket, base_cost in bucket_base_costs.items():
            caf = caf_rates.get(bucket, Decimal('0'))
            bucket_buffered[bucket] = base_cost * (Decimal('1') + caf)
        
        logger.info(f"PASS 3 - After CAF: {bucket_buffered}")
        
        # ========== PASS 4: Apply Margin ==========
        margin_rates = self._get_margin_rates()
        bucket_sell_pgk = {}
        
        for bucket, buffered_cost in bucket_buffered.items():
            margin = margin_rates.get(bucket, Decimal('0'))
            bucket_sell_pgk[bucket] = buffered_cost * (Decimal('1') + margin)
        
        logger.info(f"PASS 4 - After margin: {bucket_sell_pgk}")
        
        # ========== PASS 5: Convert to FCY if needed ==========
        grand_total_pgk = sum(bucket_sell_pgk.values())
        grand_total_fcy = None
        
        if self.quoting_currency != 'PGK':
            fx_sell = self._get_fx_sell_rate(self.quoting_currency)
            if fx_sell > 0:
                grand_total_fcy = grand_total_pgk / fx_sell
        
        logger.info(f"PASS 5 - Final: PGK={grand_total_pgk}, FCY={grand_total_fcy} ({self.quoting_currency})")
        
        return {
            'chargeable_weight': str(self.chargeable_weight),
            'quoting_currency': self.quoting_currency,
            'buckets': {
                'origin': {
                    'cost_pgk': str(bucket_base_costs['ORIGIN']),
                    'sell_pgk': str(bucket_sell_pgk['ORIGIN']),
                    'caf_rate': str(caf_rates['ORIGIN']),
                    'margin_rate': str(margin_rates['ORIGIN']),
                },
                'freight': {
                    'cost_pgk': str(bucket_base_costs['FREIGHT']),
                    'sell_pgk': str(bucket_sell_pgk['FREIGHT']),
                    'caf_rate': str(caf_rates['FREIGHT']),
                    'margin_rate': str(margin_rates['FREIGHT']),
                },
                'destination': {
                    'cost_pgk': str(bucket_base_costs['DESTINATION']),
                    'sell_pgk': str(bucket_sell_pgk['DESTINATION']),
                    'caf_rate': str(caf_rates['DESTINATION']),
                    'margin_rate': str(margin_rates['DESTINATION']),
                },
            },
            'totals': {
                'origin_sell_pgk': str(bucket_sell_pgk['ORIGIN']),
                'freight_sell_pgk': str(bucket_sell_pgk['FREIGHT']),
                'destination_sell_pgk': str(bucket_sell_pgk['DESTINATION']),
                'grand_total_pgk': str(grand_total_pgk),
                'grand_total_fcy': str(grand_total_fcy) if grand_total_fcy is not None else None,
            },
        }
    
    def _calculate_line_cost_pgk(self, line: SpotChargeLine) -> Decimal:
        """Calculate cost in PGK for a non-percentage line."""
        amount = line.amount or Decimal('0')
        
        # Handle PER_KG: multiply by chargeable weight, apply minimum
        if line.unit_basis == SpotChargeLine.UnitBasis.PER_KG:
            calculated = amount * self.chargeable_weight
            # Apply minimum if specified
            if line.min_charge:
                min_charge = Decimal(str(line.min_charge))
                amount = max(calculated, min_charge)
            else:
                amount = calculated
        
        # Convert to PGK using FX BUY rate
        if line.currency == 'PGK':
            return amount
        else:
            fx_buy = self._get_fx_buy_rate(line.currency)
            return amount * fx_buy
    
    def _get_percentage_base(
        self,
        line: SpotChargeLine,
        bucket_costs: Dict[str, Decimal],
        line_costs: Dict[str, Decimal],
    ) -> Decimal:
        """Get the base amount that a percentage line applies to."""
        applies_to = line.percent_applies_to
        
        if applies_to == SpotChargeLine.PercentAppliesTo.SPECIFIC_LINE:
            if line.target_line_id:
                return line_costs.get(str(line.target_line_id), Decimal('0'))
            return Decimal('0')
        
        elif applies_to == SpotChargeLine.PercentAppliesTo.BUCKET_ORIGIN:
            return bucket_costs.get('ORIGIN', Decimal('0'))
        
        elif applies_to == SpotChargeLine.PercentAppliesTo.BUCKET_FREIGHT:
            return bucket_costs.get('FREIGHT', Decimal('0'))
        
        elif applies_to == SpotChargeLine.PercentAppliesTo.BUCKET_DESTINATION:
            return bucket_costs.get('DESTINATION', Decimal('0'))
        
        elif applies_to == SpotChargeLine.PercentAppliesTo.BUCKET_TOTAL:
            return sum(bucket_costs.values())
        
        return Decimal('0')
