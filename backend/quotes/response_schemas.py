# backend/quotes/response_schemas.py
"""
Pydantic Response Schemas for Quote API

These schemas define the EXACT structure of API responses.
Both backend and frontend MUST conform to these schemas.

This is the SINGLE SOURCE OF TRUTH for API response contracts.
"""

from decimal import Decimal
from datetime import datetime
from typing import Optional, List
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict


# ============================================================
# QUOTE TOTALS RESPONSE
# ============================================================

class QuoteTotalsResponse(BaseModel):
    """
    Response schema for quote totals.
    
    IMPORTANT: The `currency` field is the OUTPUT CURRENCY for display.
    This is derived from shipment/payment country rules:
    - EXPORT PREPAID to AU -> AUD
    - EXPORT PREPAID non-AU -> USD
    - EXPORT COLLECT -> PGK
    - IMPORT PREPAID from AU -> AUD
    - IMPORT PREPAID non-AU -> USD
    - IMPORT COLLECT -> PGK
    """
    model_config = ConfigDict(from_attributes=True)
    
    # The OUTPUT currency for the quote (AUD/USD/PGK)
    currency: str = Field(
        ..., 
        description="Output currency for display (e.g., AUD, USD, PGK)"
    )
    
    # Cost totals (Manager/Finance view only)
    total_cost_pgk: Decimal = Field(default=Decimal('0.00'))
    
    # Sell totals in PGK
    total_sell_pgk: Decimal = Field(default=Decimal('0.00'))
    total_sell_pgk_incl_gst: Decimal = Field(default=Decimal('0.00'))
    
    # Sell totals in FCY (foreign currency)
    total_sell_fcy: Decimal = Field(default=Decimal('0.00'))
    total_sell_fcy_incl_gst: Decimal = Field(default=Decimal('0.00'))
    total_sell_fcy_currency: str = Field(default='PGK')
    
    # Status flags
    has_missing_rates: bool = Field(default=False)
    notes: Optional[str] = None


# ============================================================
# SELL LINE RESPONSE
# ============================================================

class SellLineResponse(BaseModel):
    """
    Response schema for individual sell lines.
    Used in QuoteFinancialBreakdown component.
    """
    model_config = ConfigDict(from_attributes=True)
    
    # Line identification
    id: UUID
    line_type: str = Field(default='COMPONENT')
    
    # Component info
    component: str = Field(..., description="Component code (e.g., AGENCY_EXP)")
    description: str = Field(default='')
    
    # Categorization
    leg: str = Field(..., description="ORIGIN, FREIGHT, or DESTINATION")
    
    # Sell amounts in PGK
    sell_pgk: Decimal = Field(default=Decimal('0.00'))
    sell_pgk_incl_gst: Decimal = Field(default=Decimal('0.00'))
    gst_amount: Decimal = Field(default=Decimal('0.00'))
    
    # Sell amounts in FCY
    sell_fcy: Decimal = Field(default=Decimal('0.00'))
    sell_fcy_incl_gst: Decimal = Field(default=Decimal('0.00'))
    sell_currency: str = Field(default='PGK')
    
    # Cost info (Manager/Finance only)
    cost_pgk: Optional[Decimal] = None
    margin_percent: Optional[Decimal] = None
    
    # Rate info
    exchange_rate: Decimal = Field(default=Decimal('1.0'))
    source: str = Field(default='RATE_CARD')
    is_rate_missing: bool = Field(default=False)


# ============================================================
# QUOTE VERSION RESPONSE
# ============================================================

class QuoteVersionResponse(BaseModel):
    """
    Response schema for a quote version with lines and totals.
    """
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    version_number: int
    payload_json: Optional[dict] = None
    created_at: datetime
    
    # Nested responses
    lines: List[SellLineResponse] = Field(default=[])
    totals: QuoteTotalsResponse


# ============================================================
# QUOTE DETAIL RESPONSE
# ============================================================

class CustomerResponse(BaseModel):
    """Minimal customer info for quote response."""
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    company_name: str
    
class ContactResponse(BaseModel):
    """Minimal contact info for quote response."""
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    full_name: str
    email: Optional[str] = None


class QuoteDetailResponse(BaseModel):
    """
    Full quote response for GET /api/v3/quotes/{id}/
    
    This is the main response schema for quote detail pages.
    Frontend MUST use this exact structure.
    """
    model_config = ConfigDict(from_attributes=True)
    
    # Quote identification
    id: UUID
    quote_number: str
    
    # Status
    status: str = Field(..., description="DRAFT, FINALIZED, SENT, INCOMPLETE")
    
    # Parties
    customer: CustomerResponse
    contact: Optional[ContactResponse] = None
    
    # Shipment details
    mode: str = Field(default='AIR')
    shipment_type: str = Field(..., description="IMPORT, EXPORT, DOMESTIC")
    incoterm: Optional[str] = None
    payment_term: str = Field(..., description="PREPAID or COLLECT")
    service_scope: str = Field(..., description="D2D, A2D, D2A")
    
    # Locations
    origin_location: str
    destination_location: str
    
    # Currency
    output_currency: str = Field(
        ..., 
        description="The primary output currency for this quote (AUD/USD/PGK)"
    )
    
    # Dates
    valid_until: Optional[datetime] = None
    created_at: datetime
    
    # Nested version data
    latest_version: Optional[QuoteVersionResponse] = None


# ============================================================
# COMPUTE RESULT RESPONSE (for frontend QuoteFinancialBreakdown)
# ============================================================

class ExchangeRateInfo(BaseModel):
    """Exchange rate pair info."""
    pair: str
    rate: Decimal


class QuoteComputeResultResponse(BaseModel):
    """
    Response schema for quote compute result.
    Used by QuoteFinancialBreakdown component.
    
    Frontend expects this EXACT structure:
    - result.sell_lines
    - result.totals.currency  <-- CRITICAL FIELD
    - result.exchange_rates
    """
    sell_lines: List[SellLineResponse]
    totals: QuoteTotalsResponse
    exchange_rates: dict = Field(default={})
    computation_date: str
    routing: Optional[dict] = None

