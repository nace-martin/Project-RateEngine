import json
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Optional, Dict
from datetime import date

from .engine_types import BuyCharge, SellLine, QuoteComputeResult
from .resolvers import QuoteContext

class ChargeEngine:
    """
    Transforms buy-side charges into sell-side quotes with margins, FX conversions, and CAF.
    
    Key responsibilities:
    1. Convert buy costs to PGK (using buy-side FX rates, no buffer)
    2. Apply component-specific margins
    3. Convert sell prices to output currency (using sell-side FX rates WITH buffer)
    4. Calculate CAF (Currency Adjustment Factor) as separate line
    5. Return structured QuoteComputeResult
    """
    
    def __init__(self, context: QuoteContext):
        self.context = context
        self.rates_cache = self._load_rates()
        self.freight_component_codes = ['FRT_AIR', 'OCEAN_FREIGHT', 'FRT_SEA']  # Configure as needed

    def calculate_sell_charges(self, buy_charges: List[BuyCharge]) -> QuoteComputeResult:
        """
        Main entry point: Transform buy charges into complete quote result.
        
        Process:
        1. Convert each BuyCharge → SellLine (component charges)
        2. Calculate CAF as separate SellLine (% of freight)
        3. Sum totals
        4. Return QuoteComputeResult
        """
        sell_lines = []
        
        # Step 1: Process each buy charge into a sell line
        for buy in buy_charges:
            sell_line = self._create_sell_line_from_buy(buy)
            sell_lines.append(sell_line)
        
        # Step 2: Calculate CAF (Currency Adjustment Factor) as separate line
        caf_line, caf_pgk, caf_fcy = self._calculate_caf(sell_lines)
        if caf_line:
            sell_lines.append(caf_line)
        
        # Step 3: Calculate totals
        total_cost_pgk = sum(
            line.cost_pgk for line in sell_lines 
            if line.line_type == 'COMPONENT'
        )
        total_sell_pgk = sum(line.sell_pgk for line in sell_lines)
        total_sell_fcy = sum(line.sell_fcy for line in sell_lines)
        
        # Step 4: Build result
        return QuoteComputeResult(
            buy_lines=buy_charges,
            sell_lines=sell_lines,
            total_cost_pgk=total_cost_pgk,
            total_sell_pgk=total_sell_pgk,
            total_sell_fcy=total_sell_fcy,
            sell_currency=self.context.quote.output_currency,
            caf_pgk=caf_pgk,
            caf_fcy=caf_fcy,
            exchange_rates=self._get_exchange_rate_summary(),
            computation_date=str(date.today()),
            notes=[]
        )

    def _create_sell_line_from_buy(self, buy: BuyCharge) -> SellLine:
        """
        Convert a single BuyCharge into a SellLine.
        
        Steps:
        1. Calculate cost amount in FCY (foreign currency)
        2. Convert to PGK (buy-side FX, NO buffer)
        3. Apply component-specific margin
        4. Convert to sell currency (sell-side FX, WITH buffer)
        """
        sell_currency = self.context.quote.output_currency
        
        # 1. Calculate Buy Amount in FCY
        cost_fcy = self._calculate_buy_amount_fcy(buy)
        
        # 2. Convert to PGK (Buy-Side FX, no buffer)
        fx_rate_buy = self._get_exchange_rate(buy.currency, "PGK", use_buffer=False)
        cost_pgk = (cost_fcy * fx_rate_buy).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        
        # 3. Apply Margin
        margin = self._get_component_margin(buy.component_code)
        sell_pgk = (cost_pgk * (Decimal("1.0") + margin)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        
        # 4. Convert to Sell Currency (Sell-Side FX, WITH buffer)
        fx_rate_sell = self._get_exchange_rate("PGK", sell_currency, use_buffer=True)
        sell_fcy = (sell_pgk * fx_rate_sell).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        
        return SellLine(
            line_type='COMPONENT',
            component_code=buy.component_code,
            description=buy.description or f"{buy.component_code} Charge",
            cost_pgk=cost_pgk,
            sell_pgk=sell_pgk,
            sell_fcy=sell_fcy,
            sell_currency=sell_currency,
            margin_percent=margin,
            exchange_rate=fx_rate_sell,
            source=buy.source,
            buy_charge_ref=buy.component_code  # Audit trail
        )

    def _calculate_caf(self, sell_lines: List[SellLine]) -> tuple:
        """
        Calculate Currency Adjustment Factor as % of freight components.
        
        CAF is typically 5% of total freight charges and appears as a separate line.
        
        Returns:
            (caf_sell_line, caf_pgk, caf_fcy)
        """
        # Sum up freight component sell values (PGK)
        freight_total_pgk = sum(
            line.sell_pgk 
            for line in sell_lines 
            if line.component_code in self.freight_component_codes
        )
        
        # Get CAF percentage from policy based on mode
        mode = getattr(self.context, 'mode', 'EXPORT') # Default to EXPORT if missing
        if mode == 'IMPORT':
            caf_percent = getattr(self.context.policy, 'caf_import_pct', Decimal("0.05"))
        else:
            caf_percent = getattr(self.context.policy, 'caf_export_pct', Decimal("0.10"))
        
        if freight_total_pgk <= 0:
            return (None, Decimal("0.00"), Decimal("0.00"))
        
        # Calculate CAF amounts
        caf_pgk = (freight_total_pgk * caf_percent).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        
        # Convert to sell currency
        sell_currency = self.context.quote.output_currency
        fx_rate = self._get_exchange_rate("PGK", sell_currency, use_buffer=True)
        caf_fcy = (caf_pgk * fx_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        
        # Create CAF sell line
        caf_line = SellLine(
            line_type='CAF',
            component_code=None,
            description=f"Currency Adjustment Factor ({caf_percent * 100:.1f}%)",
            cost_pgk=Decimal("0.00"),  # CAF has no cost
            sell_pgk=caf_pgk,
            sell_fcy=caf_fcy,
            sell_currency=sell_currency,
            margin_percent=Decimal("0.00"),
            exchange_rate=fx_rate,
            source='CALCULATED'
        )
        
        return (caf_line, caf_pgk, caf_fcy)

    def _get_component_margin(self, component_code: str) -> Decimal:
        """
        Lookup component-specific margin from ComponentMargin model.
        
        Fallback hierarchy:
        1. ComponentMargin for this component
        2. Customer Profile default margin
        3. Policy default margin
        """
        from .models import ComponentMargin
        from services.models import ServiceComponent
        
        try:
            # Lookup component
            component = ServiceComponent.objects.get(code=component_code)
            
            # Try to find active margin rule
            margin_rule = ComponentMargin.objects.filter(
                component=component,
                is_active=True,
                customer_segment=''  # Default segment (can be enhanced later)
            ).first()
            
            if margin_rule:
                return margin_rule.margin_percent
        except (ServiceComponent.DoesNotExist, AttributeError):
            pass
        
        # Fallback to profile/policy
        return self._get_default_margin()
    
    def _get_default_margin(self) -> Decimal:
        """Fallback margin from customer profile or policy."""
        profile = self.context.customer_profile
        if profile and profile.default_margin_percent is not None:
            return profile.default_margin_percent / Decimal("100.0")
        
        return self.context.policy.margin_pct

    def _calculate_buy_amount_fcy(self, buy: BuyCharge) -> Decimal:
        """
        Calculate the total buy amount in foreign currency based on method.
        """
        qty = self.context.chargeable_weight  # Default to weight
        
        if buy.method == 'FLAT':
            return buy.flat_amount or Decimal("0.00")
        
        elif buy.method == 'PER_UNIT':
            # TODO: Check unit type (KG, SHIPMENT, CBM, etc.)
            rate = buy.rate_per_unit or Decimal("0.00")
            amount = rate * qty
            # Apply minimum
            return max(amount, buy.min_charge)
        
        elif buy.method == 'WEIGHT_BREAK':
            # Find appropriate break
            for brk in buy.breaks:
                if qty >= brk.from_value and (brk.to_value is None or qty < brk.to_value):
                    amount = brk.rate * qty
                    return max(amount, buy.min_charge)
            return buy.min_charge
        
        elif buy.method == 'PERCENT':
            # Percentage charges need to be calculated after base charges
            # For now, return 0 and handle separately if needed
            # TODO: Implement percentage charge resolution
            return Decimal("0.00")
        
        return Decimal("0.00")

    def _get_exchange_rate(self, from_curr: str, to_curr: str, use_buffer: bool = False) -> Decimal:
        """
        Get exchange rate from FxSnapshot.
        
        Args:
            from_curr: Source currency code
            to_curr: Target currency code
            use_buffer: If True, apply FX buffer (sell-side only)
        
        Returns:
            Exchange rate as Decimal
        """
        if from_curr == to_curr:
            return Decimal("1.0")

        rates = self.rates_cache
        rate = Decimal("1.0")
        
        # Foreign Currency → PGK (Buy-Side)
        if from_curr != "PGK" and to_curr == "PGK":
            info = rates.get(from_curr)
            if info and info.get("tt_buy"):
                rate = Decimal(str(info["tt_buy"]))
        
        # PGK → Foreign Currency (Sell-Side)
        elif from_curr == "PGK" and to_curr != "PGK":
            info = rates.get(to_curr)
            if info and info.get("tt_sell"):
                base_rate = Decimal(str(info["tt_sell"]))
                rate = Decimal("1.0") / base_rate
        
        # Apply Buffer (Sell-Side Only)
        if use_buffer:
            buffer_pct = self.context.fx_snapshot.fx_buffer_percent or Decimal("0.0")
            # Buffer makes the rate less favorable (higher cost for customer)
            rate *= (Decimal("1.0") + buffer_pct)
        
        return rate

    def _get_exchange_rate_summary(self) -> Dict[str, Decimal]:
        """
        Return summary of exchange rates used for audit/display.
        """
        sell_curr = self.context.quote.output_currency
        rates = {}
        
        if sell_curr != "PGK":
            # PGK → Sell Currency (with buffer)
            rates[f"PGK_to_{sell_curr}"] = self._get_exchange_rate("PGK", sell_curr, use_buffer=True)
            rates[f"{sell_curr}_to_PGK"] = self._get_exchange_rate(sell_curr, "PGK", use_buffer=False)
        
        return rates

    def _load_rates(self) -> Dict:
        """Load FX rates from FxSnapshot."""
        rates = self.context.fx_snapshot.rates
        if isinstance(rates, str):
            return json.loads(rates)
        return rates or {}
