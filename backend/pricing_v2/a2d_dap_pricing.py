"""
A2D DAP Pricing Module

Handles specialized pricing for Import + A2D + DAP quotes with Pydantic schemas.

Two modes:
- PREPAID: Partner agent quote - passthrough in FCY (no FX, no margin)
- COLLECT: Local customer quote - convert to PGK with FX and margin

This module loads rates from the database (A2DDAPRate model).
"""
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, List, Any, Literal
from pydantic import BaseModel, Field
import logging

logger = logging.getLogger(__name__)


# ============================================================
# PYDANTIC SCHEMAS
# ============================================================

class A2DDAPRateItem(BaseModel):
    """Schema for a single A2D DAP rate from the database."""
    component_code: str
    description: str
    unit_basis: Literal['AWB', 'KG', 'PERCENTAGE']
    rate: Decimal
    min_charge: Optional[Decimal] = None
    max_charge: Optional[Decimal] = None
    percent_of_component: Optional[str] = None
    
    class Config:
        frozen = True


class A2DDAPChargeLine(BaseModel):
    """Schema for a calculated charge line."""
    component: str
    description: str
    unit_basis: str
    rate: Decimal
    min_charge: Optional[Decimal] = None
    max_charge: Optional[Decimal] = None
    percent_of: Optional[str] = None
    
    # Sell values
    sell_amount: Decimal = Field(description="Sell amount in output currency")
    sell_currency: str = Field(description="Currency of sell amount")
    
    # Cost values (for passthrough, cost = sell)
    cost_amount: Decimal = Field(description="Cost amount in rate currency")
    cost_currency: str = Field(description="Currency of cost amount")
    
    # Pricing metadata
    margin_percent: Decimal = Decimal('0')
    exchange_rate: Decimal = Decimal('1')
    leg: str = 'DESTINATION'
    
    class Config:
        frozen = True


class A2DDAPTotals(BaseModel):
    """Schema for quote totals."""
    total_sell: Decimal
    total_sell_currency: str
    total_pgk_internal: Decimal = Field(description="PGK reference for internal use only")
    
    class Config:
        frozen = True


class A2DDAPCalculationResult(BaseModel):
    """Schema for complete A2D DAP calculation result."""
    currency: str = Field(description="Output currency for the quote")
    payment_term: str = Field(description="PREPAID or COLLECT")
    lines: List[A2DDAPChargeLine]
    totals: A2DDAPTotals
    is_passthrough: bool = Field(description="True if no FX/margin applied")
    show_pgk_to_client: bool = Field(default=False, description="Whether to show PGK on client documents")
    
    class Config:
        frozen = True


# ============================================================
# CURRENCY MAPPING
# ============================================================

ORIGIN_CURRENCY_MAPPING = {
    'AU': 'AUD',  # Australia -> AUD
    'SG': 'USD',  # Singapore -> USD
    'CN': 'USD',  # China -> USD
    'NZ': 'USD',  # New Zealand -> USD
    'HK': 'USD',  # Hong Kong -> USD
    'MY': 'USD',  # Malaysia -> USD
    'ID': 'USD',  # Indonesia -> USD
    'TH': 'USD',  # Thailand -> USD
    'JP': 'USD',  # Japan -> USD
    'KR': 'USD',  # South Korea -> USD
}

DEFAULT_CURRENCY = 'USD'


# ============================================================
# PUBLIC FUNCTIONS
# ============================================================

def is_a2d_dap_quote(shipment_type: str, service_scope: str, incoterm: str, payment_term: str) -> bool:
    """
    Determine if a quote qualifies for A2D DAP pricing.
    
    Criteria:
    - Direction: IMPORT
    - Service Scope: A2D (Airport to Door)
    - Incoterm: DAP (Delivered At Place)
    - Payment: PREPAID or COLLECT
    """
    return (
        shipment_type == 'IMPORT' and
        service_scope == 'A2D' and
        incoterm == 'DAP' and
        payment_term in ('PREPAID', 'COLLECT')
    )


def is_a2d_dap_prepaid(shipment_type: str, service_scope: str, incoterm: str, payment_term: str) -> bool:
    """Check if this is specifically an A2D DAP PREPAID quote (partner agent passthrough)."""
    return is_a2d_dap_quote(shipment_type, service_scope, incoterm, payment_term) and payment_term == 'PREPAID'


def is_a2d_dap_collect(shipment_type: str, service_scope: str, incoterm: str, payment_term: str) -> bool:
    """Check if this is specifically an A2D DAP COLLECT quote (local customer in PGK)."""
    return is_a2d_dap_quote(shipment_type, service_scope, incoterm, payment_term) and payment_term == 'COLLECT'


def get_a2d_dap_currency(origin_country_code: str, payment_term: str) -> str:
    """
    Get the quote currency based on origin country and payment term.
    
    - PREPAID: AU -> AUD, others -> USD (FCY passthrough)
    - COLLECT: Always PGK (local customer)
    """
    if payment_term == 'COLLECT':
        return 'PGK'
    
    return ORIGIN_CURRENCY_MAPPING.get(origin_country_code.upper(), DEFAULT_CURRENCY)


def get_a2d_dap_rates_from_db(currency: str, payment_term: str) -> List[A2DDAPRateItem]:
    """
    Load A2D DAP rates from the database for a given currency and payment term.
    
    Returns list of Pydantic A2DDAPRateItem objects.
    """
    from ratecards.models import A2DDAPRate
    
    rates = A2DDAPRate.objects.filter(
        currency=currency,
        payment_term=payment_term,
        is_active=True
    ).select_related(
        'service_component',
        'percent_of_component'
    ).order_by('display_order')
    
    result = []
    for rate in rates:
        item = A2DDAPRateItem(
            component_code=rate.service_component.code,
            description=rate.service_component.description,
            unit_basis=rate.unit_basis,
            rate=rate.rate,
            min_charge=rate.min_charge,
            max_charge=rate.max_charge,
            percent_of_component=rate.percent_of_component.code if rate.percent_of_component else None,
        )
        result.append(item)
    
    return result


def calculate_a2d_dap_charges(
    origin_country_code: str,
    payment_term: str,
    chargeable_weight_kg: Decimal,
    fx_snapshot: Optional[Any] = None,
    margin_pct: Decimal = Decimal('0.15'),
) -> A2DDAPCalculationResult:
    """
    Calculate all destination charges for an A2D DAP quote.
    
    For PREPAID (partner agent):
    - Load AUD/USD rates based on origin
    - No FX conversion, no margin (passthrough)
    - Output in AUD/USD
    
    For COLLECT (local customer):
    - Load PGK rates directly from database
    - No FX conversion, no margin (passthrough)
    - Output in PGK
    
    Args:
        origin_country_code: Country code of origin (AU, SG, CN, etc.)
        payment_term: PREPAID or COLLECT
        chargeable_weight_kg: Chargeable weight for per-kg calculations
        fx_snapshot: Optional FX snapshot (for internal PGK reference only)
        margin_pct: Not used - both modes are passthrough
        
    Returns:
        A2DDAPCalculationResult with calculated charges and totals
    """
    # Determine rate card currency
    if payment_term == 'COLLECT':
        # COLLECT: Use PGK rates directly
        rate_currency = 'PGK'
        output_currency = 'PGK'
    else:
        # PREPAID: Use FCY rates based on origin
        rate_currency = ORIGIN_CURRENCY_MAPPING.get(origin_country_code.upper(), DEFAULT_CURRENCY)
        output_currency = rate_currency
    
    # Both modes are passthrough (no FX, no margin)
    is_passthrough = True
    
    # Load rates from database
    db_rates = get_a2d_dap_rates_from_db(rate_currency, payment_term)
    
    if not db_rates:
        logger.warning(f"No A2D DAP rates found for {payment_term} {rate_currency}")
        return A2DDAPCalculationResult(
            currency=output_currency,
            payment_term=payment_term,
            lines=[],
            totals=A2DDAPTotals(
                total_sell=Decimal('0'),
                total_sell_currency=output_currency,
                total_pgk_internal=Decimal('0'),
            ),
            is_passthrough=is_passthrough,
            show_pgk_to_client=(payment_term == 'COLLECT'),
        )
    
    calculated_lines = []
    component_values = {}  # For percentage-based references
    
    # First pass: Calculate non-percentage charges (passthrough - no FX/margin)
    for rate in db_rates:
        if rate.unit_basis == 'PERCENTAGE':
            continue  # Handle in second pass
            
        line = _calculate_rate_line(
            rate=rate,
            chargeable_weight_kg=chargeable_weight_kg,
            rate_currency=rate_currency,
            output_currency=output_currency,
            fx_rate=Decimal('1'),  # No FX conversion
            margin_pct=Decimal('0'),  # No margin
        )
        calculated_lines.append(line)
        component_values[rate.component_code] = line.sell_amount
    
    # Second pass: Calculate percentage-based charges
    for rate in db_rates:
        if rate.unit_basis != 'PERCENTAGE':
            continue
            
        base_code = rate.percent_of_component
        base_value = component_values.get(base_code, Decimal('0'))
        line = _calculate_percentage_line(
            rate=rate,
            base_value=base_value,
            output_currency=output_currency,
        )
        calculated_lines.append(line)
        component_values[rate.component_code] = line.sell_amount
    
    # Calculate totals
    total_sell = sum(line.sell_amount for line in calculated_lines)
    
    # Calculate PGK internal reference
    if output_currency == 'PGK':
        total_pgk_internal = total_sell
    else:
        total_pgk_internal = _calculate_pgk_reference(total_sell, output_currency, fx_snapshot)
    
    return A2DDAPCalculationResult(
        currency=output_currency,
        payment_term=payment_term,
        lines=calculated_lines,
        totals=A2DDAPTotals(
            total_sell=total_sell.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
            total_sell_currency=output_currency,
            total_pgk_internal=total_pgk_internal,
        ),
        is_passthrough=is_passthrough,
        show_pgk_to_client=(payment_term == 'COLLECT'),
    )


# ============================================================
# PRIVATE HELPER FUNCTIONS
# ============================================================

def _get_fx_rate(from_currency: str, fx_snapshot: Any) -> Decimal:
    """Get FX rate from snapshot for FCY -> PGK conversion."""
    try:
        rates = fx_snapshot.rates if hasattr(fx_snapshot, 'rates') else {}
        rate_info = rates.get(from_currency, {})
        tt_buy = rate_info.get('tt_buy')
        
        if tt_buy:
            return Decimal(str(tt_buy))
    except Exception as e:
        logger.warning(f"Could not get FX rate for {from_currency}: {e}")
    
    return Decimal('1')


def _calculate_rate_line(
    rate: A2DDAPRateItem,
    chargeable_weight_kg: Decimal,
    rate_currency: str,
    output_currency: str,
    fx_rate: Decimal,
    margin_pct: Decimal,
) -> A2DDAPChargeLine:
    """Calculate a single rate line based on unit basis."""
    # Calculate base cost in rate currency
    cost_fcy = Decimal('0')
    
    if rate.unit_basis == 'AWB':
        cost_fcy = rate.rate
        
    elif rate.unit_basis == 'KG':
        cost_fcy = rate.rate * chargeable_weight_kg
        
        if rate.min_charge and cost_fcy < rate.min_charge:
            cost_fcy = rate.min_charge
        if rate.max_charge and cost_fcy > rate.max_charge:
            cost_fcy = rate.max_charge
    
    cost_fcy = cost_fcy.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    
    # Convert to output currency and apply margin
    if output_currency == rate_currency:
        # Passthrough - no conversion
        sell_amount = cost_fcy
        exchange_rate = Decimal('1')
    else:
        # Convert FCY -> PGK
        cost_pgk = cost_fcy * fx_rate
        sell_amount = cost_pgk * (Decimal('1') + margin_pct)
        exchange_rate = fx_rate
    
    sell_amount = sell_amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    
    return A2DDAPChargeLine(
        component=rate.component_code,
        description=rate.description,
        unit_basis=rate.unit_basis,
        rate=rate.rate,
        min_charge=rate.min_charge,
        max_charge=rate.max_charge,
        sell_amount=sell_amount,
        sell_currency=output_currency,
        cost_amount=cost_fcy,
        cost_currency=rate_currency,
        margin_percent=margin_pct,
        exchange_rate=exchange_rate,
        leg='DESTINATION',
    )


def _calculate_percentage_line(
    rate: A2DDAPRateItem,
    base_value: Decimal,
    output_currency: str,
) -> A2DDAPChargeLine:
    """Calculate a percentage-based charge (e.g., FSC = 10% of Cartage)."""
    percent = rate.rate / Decimal('100')
    sell_amount = (base_value * percent).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    
    return A2DDAPChargeLine(
        component=rate.component_code,
        description=rate.description,
        unit_basis=rate.unit_basis,
        rate=rate.rate,
        percent_of=rate.percent_of_component,
        sell_amount=sell_amount,
        sell_currency=output_currency,
        cost_amount=sell_amount,  # For percentage, cost = sell
        cost_currency=output_currency,
        margin_percent=Decimal('0'),
        exchange_rate=Decimal('1'),
        leg='DESTINATION',
    )


def _calculate_pgk_reference(total_fcy: Decimal, currency: str, fx_snapshot: Optional[Any]) -> Decimal:
    """
    Calculate PGK equivalent for internal reference/reporting.
    This value is NOT shown to clients for PREPAID quotes.
    """
    if currency == 'PGK':
        return total_fcy
    
    if not fx_snapshot:
        return Decimal('0')
    
    try:
        rates = fx_snapshot.rates if hasattr(fx_snapshot, 'rates') else {}
        rate_info = rates.get(currency, {})
        tt_sell = rate_info.get('tt_sell')
        
        if tt_sell:
            pgk = total_fcy * Decimal(str(tt_sell))
            return pgk.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    except Exception as e:
        logger.warning(f"Could not calculate PGK reference: {e}")
    
    return Decimal('0')
