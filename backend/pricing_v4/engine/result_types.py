from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Dict, Iterable, List, Optional

from core.charge_rules import CALCULATION_LOOKUP_RATE
from quotes.quote_result_contract import (
    QuoteComponent,
    QuoteCostSource,
    QuoteRateSource,
)

ZERO_DECIMAL = Decimal("0.00")


@dataclass
class LegacyBreakdownCharge:
    description: str
    amount: Decimal
    product_code: str = ""
    agent_name: Optional[str] = None


@dataclass
class QuoteLineItem:
    line_id: str = ""
    product_code_id: Optional[int] = None
    product_code: str = ""
    description: str = ""
    component: str = QuoteComponent.OTHER
    basis: str = "Per Shipment"
    rule_family: str = CALCULATION_LOOKUP_RATE
    unit_type: str = "SHIPMENT"
    quantity: Decimal = Decimal("1.00")
    currency: str = "PGK"
    rate: Optional[Decimal] = None
    category: str = ""
    leg: str = "ORIGIN"
    cost_amount: Decimal = ZERO_DECIMAL
    cost_currency: str = "PGK"
    cost_source: str = QuoteCostSource.UNKNOWN
    agent_name: Optional[str] = None
    sell_amount: Decimal = ZERO_DECIMAL
    sell_currency: str = "PGK"
    margin_amount: Decimal = ZERO_DECIMAL
    margin_percent: Decimal = ZERO_DECIMAL
    tax_code: str = ""
    tax_amount: Decimal = ZERO_DECIMAL
    gst_category: str = ""
    gst_rate: Decimal = ZERO_DECIMAL
    gst_amount: Decimal = ZERO_DECIMAL
    sell_incl_gst: Decimal = ZERO_DECIMAL
    included_in_total: bool = True
    rate_source: str = QuoteRateSource.UNKNOWN
    calculation_notes: Optional[str] = None
    is_spot_sourced: bool = False
    is_manual_override: bool = False
    sort_order: int = 0
    is_rate_missing: bool = False
    notes: str = ""
    fx_applied: bool = False
    caf_applied: bool = False
    margin_applied: bool = False


@dataclass
class QuoteResult:
    quote_id: str = ""
    status: Optional[str] = None
    customer_name: Optional[str] = None
    mode: Optional[str] = None
    incoterm: Optional[str] = None
    cargo_type: Optional[str] = None
    pieces: int = 0
    actual_weight: Decimal = ZERO_DECIMAL
    volumetric_weight: Decimal = ZERO_DECIMAL
    chargeable_weight: Decimal = ZERO_DECIMAL
    dimensions_summary: Optional[str] = None
    line_items: List[QuoteLineItem] = field(default_factory=list)
    sell_total: Decimal = ZERO_DECIMAL
    total_cost_pgk: Decimal = ZERO_DECIMAL
    total_sell_pgk: Decimal = ZERO_DECIMAL
    margin_amount: Decimal = ZERO_DECIMAL
    margin_percent: Decimal = ZERO_DECIMAL
    fx_applied: Dict[str, Optional[Decimal] | Optional[str] | Optional[bool] | Optional[date]] | bool = False
    tax_breakdown: Dict[str, Decimal | Dict[str, Decimal] | Optional[str]] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    missing_components: List[str] = field(default_factory=list)
    spot_required: bool = False
    engine_name: Optional[str] = None
    rate_source: str = QuoteRateSource.UNKNOWN
    service_notes: Optional[str] = None
    customer_notes: Optional[str] = None
    internal_notes: Optional[str] = None
    prepared_by: Optional[str] = None
    created_at: Optional[date] = None
    calculated_at: Optional[date] = None
    quote_version: Optional[int] = None
    origin: str = ""
    destination: str = ""
    quote_date: Optional[date] = None
    chargeable_weight_kg: Decimal = ZERO_DECIMAL
    direction: str = ""
    payment_term: str = ""
    service_scope: str = ""
    quote_currency: str = "PGK"
    currency: str = "PGK"
    total_margin: Decimal = ZERO_DECIMAL
    total_gst: Decimal = ZERO_DECIMAL
    total_sell_incl_gst: Decimal = ZERO_DECIMAL
    fx_rate_used: Optional[Decimal] = None
    effective_fx_rate: Optional[Decimal] = None
    caf_rate: Optional[Decimal] = None

    @property
    def lines(self) -> List[QuoteLineItem]:
        return self.line_items

    @property
    def origin_lines(self) -> List[QuoteLineItem]:
        return [line for line in self.line_items if str(line.leg).upper() == "ORIGIN"]

    @property
    def freight_lines(self) -> List[QuoteLineItem]:
        return [line for line in self.line_items if str(line.leg).upper() in {"FREIGHT", "MAIN"}]

    @property
    def destination_lines(self) -> List[QuoteLineItem]:
        return [line for line in self.line_items if str(line.leg).upper() == "DESTINATION"]

    @property
    def cogs_breakdown(self) -> List[LegacyBreakdownCharge]:
        return [
            LegacyBreakdownCharge(
                description=f"{line.description} (Cost)",
                amount=line.cost_amount,
                product_code=line.product_code,
                agent_name=line.agent_name,
            )
            for line in self.line_items
            if line.cost_amount > 0
        ]

    @property
    def sell_breakdown(self) -> List[LegacyBreakdownCharge]:
        return [
            LegacyBreakdownCharge(
                description=line.description,
                amount=line.sell_amount,
                product_code=line.product_code,
                agent_name=line.agent_name,
            )
            for line in self.line_items
            if line.sell_amount > 0 or line.is_rate_missing
        ]

    @property
    def total_cost(self) -> Decimal:
        return self.total_cost_pgk

    @property
    def total_sell(self) -> Decimal:
        return self.total_sell_pgk


def build_tax_breakdown(
    line_items: List[QuoteLineItem],
    *,
    converter=None,
    default_labels: Optional[Iterable[str]] = None,
) -> Dict[str, Decimal]:
    breakdown: Dict[str, Decimal] = {
        label: ZERO_DECIMAL for label in (default_labels or [])
    }

    for line in line_items:
        amount = line.tax_amount or line.gst_amount
        if not amount:
            continue

        label = line.tax_code or line.gst_category or "GST"
        if converter is not None:
            amount = converter(amount, line.sell_currency)
        breakdown[label] = breakdown.get(label, ZERO_DECIMAL) + amount

    return breakdown
