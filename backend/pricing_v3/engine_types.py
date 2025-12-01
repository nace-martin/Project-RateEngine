from dataclasses import dataclass, field
from decimal import Decimal
from typing import List, Optional, Dict

@dataclass
class ChargeBreak:
    rate: Decimal
    from_value: Decimal = Decimal("0.00")
    to_value: Optional[Decimal] = None

@dataclass
class BuyCharge:
    source: str  # 'CONTRACT', 'SPOT', 'LOCAL_FEE'
    supplier_id: Optional[int]
    component_code: str
    currency: str
    
    method: str  # Uses ChargeMethod values
    unit: Optional[str]  # Uses ChargeUnit values
    
    min_charge: Decimal = Decimal("0.00")
    flat_amount: Optional[Decimal] = None
    rate_per_unit: Optional[Decimal] = None
    
    percent_value: Optional[Decimal] = None
    percent_of_component: Optional[str] = None
    
    breaks: List[ChargeBreak] = field(default_factory=list)
    description: str = ""

@dataclass
class SellLine:
    """
    Represents a single line item in the quote sell-side breakdown.
    Can represent a component charge, CAF (Currency Adjustment Factor), or other surcharge.
    
    This replaces the old SellCharge 1:1 mapping to support scenarios where
    1 BuyCharge may generate multiple SellLines (e.g., freight + CAF).
    """
    line_type: str  # 'COMPONENT', 'CAF', 'SURCHARGE'
    component_code: Optional[str] = None
    description: str = ""
    
    # Financial values (all in respective currencies)
    cost_pgk: Decimal = Decimal("0.00")
    sell_pgk: Decimal = Decimal("0.00")
    sell_fcy: Decimal = Decimal("0.00")
    sell_currency: str = "PGK"
    
    # Calculation metadata
    margin_percent: Decimal = Decimal("0.00")  # As decimal (0.20 = 20%)
    exchange_rate: Decimal = Decimal("1.0")    # Rate used for sell_fcy conversion
    source: str = ""  # 'CONTRACT', 'SPOT', 'LOCAL_FEE', 'CALCULATED'
    
    # Original buy charge reference (for audit trail)
    buy_charge_ref: Optional[str] = None

@dataclass
class QuoteComputeResult:
    """
    Complete quote computation result with buy/sell breakdowns and totals.
    This is the primary output of the ChargeEngine.
    """
    # Raw buy charges from resolver
    buy_lines: List[BuyCharge] = field(default_factory=list)
    
    # Processed sell lines (includes component charges + CAF + surcharges)
    sell_lines: List[SellLine] = field(default_factory=list)
    
    # Totals (all sell lines summed)
    total_cost_pgk: Decimal = Decimal("0.00")
    total_sell_pgk: Decimal = Decimal("0.00")
    total_sell_fcy: Decimal = Decimal("0.00")
    sell_currency: str = "PGK"
    
    # Individual amounts for transparency
    caf_pgk: Decimal = Decimal("0.00")  # CAF portion in PGK
    caf_fcy: Decimal = Decimal("0.00")  # CAF portion in foreign currency
    
    # Exchange rates used (for audit/display)
    exchange_rates: Dict[str, Decimal] = field(default_factory=dict)
    
    # Metadata
    computation_date: Optional[str] = None
    notes: List[str] = field(default_factory=list)
