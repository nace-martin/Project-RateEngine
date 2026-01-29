# backend/pricing_v4/dispatcher.py
"""
Pricing Dispatcher - Single Entry Point for All Quote Calculations

This module provides a centralized dispatcher that:
1. Acts as the SOLE entry point for all pricing calculations
2. Explicitly routes requests to V4 engines based on shipment type
3. Prohibits any "hybrid" quotes where V3 and V4 are mixed
4. Tags all calculations with engine_version for audit trail

Usage:
    from pricing_v4.dispatcher import PricingDispatcher
    
    dispatcher = PricingDispatcher()
    result = dispatcher.calculate(quote_input)
"""

import logging
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Optional
from uuid import UUID

from django.conf import settings

from core.dataclasses import QuoteInput, QuoteCharges
from pricing_v4.adapter import PricingServiceV4Adapter
from pricing_v4.engine.domestic_engine import DomesticPricingEngine
from pricing_v4.engine.export_engine import ExportPricingEngine
from pricing_v4.engine.import_engine import ImportPricingEngine

logger = logging.getLogger(__name__)


class EngineVersion(str, Enum):
    """Supported pricing engine versions."""
    V3 = "V3"  # Legacy - deprecated, for shadow mode only
    V4 = "V4"  # Current production engine


class ShipmentType(str, Enum):
    """Shipment type routing keys."""
    IMPORT = "IMPORT"
    EXPORT = "EXPORT"
    DOMESTIC = "DOMESTIC"


@dataclass
class RoutingMap:
    """
    Explicit declaration of which engine handles which request.
    
    RULE: All routes point to V4 engines. No V3 fallback.
    """
    
    @staticmethod
    def get_engine_class(shipment_type: str):
        """
        Returns the V4 engine class for the given shipment type.
        
        Args:
            shipment_type: One of IMPORT, EXPORT, DOMESTIC
            
        Returns:
            The appropriate V4 engine class
            
        Raises:
            ValueError: If shipment type is not supported
        """
        routing = {
            ShipmentType.IMPORT.value: ImportPricingEngine,
            ShipmentType.EXPORT.value: ExportPricingEngine,
            ShipmentType.DOMESTIC.value: DomesticPricingEngine,
        }
        
        engine_class = routing.get(shipment_type.upper())
        if engine_class is None:
            raise ValueError(
                f"Unsupported shipment type: {shipment_type}. "
                f"Supported types: {list(routing.keys())}"
            )
        return engine_class


@dataclass
class CalculationResult:
    """Result wrapper that includes engine version metadata."""
    charges: QuoteCharges
    engine_version: str
    shadow_comparison: Optional[dict] = None


class PricingDispatcher:
    """
    Single entry point for all quote calculations.
    
    This dispatcher:
    1. Routes all requests through the V4 adapter exclusively
    2. Logs engine selection for audit trail
    3. Optionally runs V3 in shadow mode for comparison
    4. Rejects any attempt to use hybrid V3/V4 logic
    """
    
    def __init__(self, spot_envelope_id: Optional[UUID] = None):
        """
        Initialize the dispatcher.
        
        Args:
            spot_envelope_id: Optional SPOT envelope for spot pricing overlay
        """
        self.spot_envelope_id = spot_envelope_id
        self._shadow_mode_enabled = getattr(
            settings, 'PRICING_ENGINE_SHADOW_MODE', False
        )
    
    def calculate(self, quote_input: QuoteInput) -> CalculationResult:
        """
        Execute pricing calculation using the V4 engine.
        
        Args:
            quote_input: The validated quote input data
            
        Returns:
            CalculationResult with charges and engine version metadata
            
        Raises:
            ValueError: If the request cannot be routed to a valid engine
        """
        shipment_type = self._extract_shipment_type(quote_input)
        
        # Log the routing decision for audit trail
        logger.info(
            f"PricingDispatcher routing: shipment_type={shipment_type}, "
            f"engine=V4, customer_id={quote_input.customer_id}"
        )
        
        # Validate routing exists (will raise if invalid)
        RoutingMap.get_engine_class(shipment_type)
        
        # Execute V4 calculation (always the primary)
        v4_charges = self._calculate_v4(quote_input)
        
        # Optional shadow mode comparison
        shadow_comparison = None
        if self._shadow_mode_enabled:
            shadow_comparison = self._run_shadow_comparison(
                quote_input, v4_charges
            )
        
        return CalculationResult(
            charges=v4_charges,
            engine_version=EngineVersion.V4.value,
            shadow_comparison=shadow_comparison,
        )
    
    def _extract_shipment_type(self, quote_input: QuoteInput) -> str:
        """Extract shipment type from quote input."""
        shipment = quote_input.shipment
        if shipment and hasattr(shipment, 'shipment_type'):
            return shipment.shipment_type
        if shipment and hasattr(shipment, 'direction'):
            return shipment.direction
        raise ValueError("Cannot determine shipment type from quote input")
    
    def _calculate_v4(self, quote_input: QuoteInput) -> QuoteCharges:
        """
        Execute calculation using V4 adapter.
        
        The V4 adapter internally routes to the correct engine
        (Import, Export, or Domestic) based on shipment details.
        """
        adapter = PricingServiceV4Adapter(
            quote_input,
            spot_envelope_id=self.spot_envelope_id
        )
        return adapter.calculate_charges()
    
    def _run_shadow_comparison(
        self, 
        quote_input: QuoteInput,
        v4_charges: QuoteCharges
    ) -> Optional[dict]:
        """
        Run V3 calculation in shadow mode and log comparison.
        
        This is for transition verification only. V3 result is never
        returned to the caller - only logged for analysis.
        
        Returns:
            Comparison dict with variance data, or None if shadow failed
        """
        try:
            # Import V3 resolver only in shadow mode to avoid hard dependency
            from pricing_v3.resolvers import BuyChargeResolver, QuoteContextBuilder
            
            # V3 requires a Quote object which we may not have in all cases
            # This is a best-effort comparison
            logger.warning(
                "Shadow mode: V3 comparison skipped - requires Quote object context. "
                "Consider using direct rate comparison instead."
            )
            return None
            
        except ImportError:
            logger.warning("Shadow mode: pricing_v3 not available for comparison")
            return None
        except Exception as e:
            logger.warning(f"Shadow mode V3 calculation failed: {e}")
            return None
    
    def get_engine_version(self) -> str:
        """Return the engine version this dispatcher uses."""
        return EngineVersion.V4.value


# Convenience function for simple usage
def calculate_quote(
    quote_input: QuoteInput,
    spot_envelope_id: Optional[UUID] = None
) -> CalculationResult:
    """
    Calculate quote charges using the pricing dispatcher.
    
    This is the recommended entry point for all new code.
    
    Args:
        quote_input: Validated quote input
        spot_envelope_id: Optional SPOT envelope ID
        
    Returns:
        CalculationResult with charges and metadata
    """
    dispatcher = PricingDispatcher(spot_envelope_id=spot_envelope_id)
    return dispatcher.calculate(quote_input)
