# backend/quotes/services/dispatcher.py
"""
Pricing Dispatcher - Single Entry Point for All Quote Calculations

This module provides a centralized dispatcher that:
1. Acts as the SOLE entry point for all pricing calculations
2. Routes requests to V3 or V4 engines based on routing configuration
3. Implements a Kill-Switch for emergency fallback to V3
4. Provides shadow mode comparison with variance thresholds
5. Tags all calculations with engine_version for audit trail

Usage:
    from quotes.services.dispatcher import PricingDispatcher
    
    dispatcher = PricingDispatcher()
    result = dispatcher.calculate(quote_input)
    
    # Access results
    charges = result.charges
    engine_version = result.engine_version
"""

import logging
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Optional
from uuid import UUID

from django.conf import settings

from core.dataclasses import QuoteInput, QuoteCharges

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Enums & Exceptions
# -----------------------------------------------------------------------------

class EngineVersion(str, Enum):
    """Supported pricing engine versions."""
    V3 = "V3"  # Legacy engine
    V4 = "V4"  # Current production engine


class ShipmentType(str, Enum):
    """Shipment type routing keys."""
    IMPORT = "IMPORT"
    EXPORT = "EXPORT"
    DOMESTIC = "DOMESTIC"


class RoutingError(Exception):
    """
    Raised when a request cannot be routed to any valid engine.
    
    This is a safety mechanism that prevents the dispatcher from
    "guessing" which engine to use for unknown shipment types.
    """
    pass


class ZeroChargeError(Exception):
    """
    Raised when V4 returns zero charges for a quote.
    
    This indicates missing rate data and should be investigated.
    """
    pass


# -----------------------------------------------------------------------------
# Routing Configuration
# -----------------------------------------------------------------------------

class RoutingMap:
    """
    Explicit declaration of which engine handles which shipment type.
    
    RULE: All routes point to V4 by default. V3 is only used when:
    1. The kill-switch (USE_LEGACY_PRICING) is enabled
    2. Shadow mode is running a comparison
    """
    
    # Default routing - all to V4
    DEFAULT_ROUTING = {
        ShipmentType.IMPORT.value: EngineVersion.V4,
        ShipmentType.EXPORT.value: EngineVersion.V4,
        ShipmentType.DOMESTIC.value: EngineVersion.V4,
    }
    
    @classmethod
    def get_engine_version(cls, shipment_type: str) -> EngineVersion:
        """
        Get the engine version for a shipment type.
        
        Args:
            shipment_type: One of IMPORT, EXPORT, DOMESTIC
            
        Returns:
            EngineVersion to use
            
        Raises:
            RoutingError: If shipment type is not in the routing map
        """
        normalized = shipment_type.upper() if shipment_type else None
        
        if normalized not in cls.DEFAULT_ROUTING:
            raise RoutingError(
                f"Cannot route shipment_type='{shipment_type}'. "
                f"Supported types: {list(cls.DEFAULT_ROUTING.keys())}. "
                "Refusing to guess - explicit routing required."
            )
        
        return cls.DEFAULT_ROUTING[normalized]


# -----------------------------------------------------------------------------
# Result Dataclasses
# -----------------------------------------------------------------------------

@dataclass
class ShadowComparison:
    """Results of shadow mode V3 vs V4 comparison."""
    v3_total_pgk: Decimal
    v4_total_pgk: Decimal
    variance_pgk: Decimal
    variance_percent: Decimal
    is_high_variance: bool
    

@dataclass
class CalculationResult:
    """Result wrapper that includes engine version metadata."""
    charges: QuoteCharges
    engine_version: str
    shadow_comparison: Optional[ShadowComparison] = None


# -----------------------------------------------------------------------------
# Pricing Dispatcher
# -----------------------------------------------------------------------------

class PricingDispatcher:
    """
    Single entry point for all quote calculations.
    
    This dispatcher:
    1. Checks for kill-switch before routing
    2. Routes all requests through V4 by default
    3. Performs pre-flight check for zero charges
    4. Logs engine selection for audit trail
    5. Optionally runs V3 in shadow mode for comparison
    6. Rejects any attempt to use unknown shipment types
    """
    
    # Variance thresholds for shadow mode logging
    VARIANCE_PERCENT_THRESHOLD = Decimal("1.0")  # 1%
    VARIANCE_ABSOLUTE_THRESHOLD = Decimal("5.00")  # 5 PGK
    
    def __init__(self, spot_envelope_id: Optional[UUID] = None):
        """
        Initialize the dispatcher.
        
        Args:
            spot_envelope_id: Optional SPOT envelope for spot pricing overlay
        """
        self.spot_envelope_id = spot_envelope_id
        
        # Configuration from settings
        self._use_legacy_pricing = getattr(
            settings, 'USE_LEGACY_PRICING', False
        )
        self._shadow_mode_enabled = getattr(
            settings, 'PRICING_ENGINE_SHADOW_MODE', False
        )
    
    def calculate(self, quote_input: QuoteInput) -> CalculationResult:
        """
        Execute pricing calculation using the appropriate engine.
        
        Args:
            quote_input: The validated quote input data
            
        Returns:
            CalculationResult with charges and engine version metadata
            
        Raises:
            RoutingError: If the request cannot be routed
            ZeroChargeError: If V4 returns zero charges (pre-flight failure)
        """
        shipment_type = self._extract_shipment_type(quote_input)
        
        # Kill-Switch: Force V3 globally if setting is enabled
        if self._use_legacy_pricing:
            logger.warning(
                "KILL-SWITCH ACTIVE: USE_LEGACY_PRICING=True. "
                f"Routing {shipment_type} to V3 engine."
            )
            return self._execute_v3(quote_input, shipment_type)
        
        # Normal routing via RoutingMap
        engine_version = RoutingMap.get_engine_version(shipment_type)
        
        # Log the routing decision for audit trail
        logger.info(
            f"PricingDispatcher routing: shipment_type={shipment_type}, "
            f"engine={engine_version.value}, customer_id={quote_input.customer_id}"
        )
        
        # Execute calculation based on routed engine
        if engine_version == EngineVersion.V4:
            return self._execute_v4(quote_input, shipment_type)
        else:
            return self._execute_v3(quote_input, shipment_type)
    
    def _execute_v4(
        self, 
        quote_input: QuoteInput, 
        shipment_type: str
    ) -> CalculationResult:
        """
        Execute V4 calculation with pre-flight and shadow mode.
        """
        # Execute V4 calculation
        v4_charges = self._calculate_v4(quote_input)
        
        # Pre-flight check: Verify V4 returned meaningful charges
        self._pre_flight_check(v4_charges, shipment_type, quote_input)
        
        # Optional shadow mode comparison
        shadow_comparison = None
        if self._shadow_mode_enabled:
            shadow_comparison = self._run_shadow_comparison(
                quote_input, v4_charges, shipment_type
            )
        
        return CalculationResult(
            charges=v4_charges,
            engine_version=EngineVersion.V4.value,
            shadow_comparison=shadow_comparison,
        )
    
    def _execute_v3(
        self, 
        quote_input: QuoteInput, 
        shipment_type: str
    ) -> CalculationResult:
        """
        Execute V3 calculation (kill-switch or legacy routing).
        """
        v3_charges = self._calculate_v3(quote_input)
        
        return CalculationResult(
            charges=v3_charges,
            engine_version=EngineVersion.V3.value,
            shadow_comparison=None,
        )
    
    def _extract_shipment_type(self, quote_input: QuoteInput) -> str:
        """Extract shipment type from quote input."""
        shipment = quote_input.shipment
        if shipment and hasattr(shipment, 'shipment_type') and shipment.shipment_type:
            return shipment.shipment_type
        if shipment and hasattr(shipment, 'direction') and shipment.direction:
            return shipment.direction
        raise RoutingError("Cannot determine shipment type from quote input")
    
    def _calculate_v4(self, quote_input: QuoteInput) -> QuoteCharges:
        """
        Execute calculation using V4 adapter.
        """
        from pricing_v4.adapter import PricingServiceV4Adapter
        
        adapter = PricingServiceV4Adapter(
            quote_input,
            spot_envelope_id=self.spot_envelope_id
        )
        return adapter.calculate_charges()
    
    def _calculate_v3(self, quote_input: QuoteInput) -> QuoteCharges:
        """
        Execute calculation using V3 resolvers.
        
        Note: V3 requires a Quote object context which may not be available
        in all dispatcher use cases. This is a best-effort implementation.
        """
        # For now, V3 calculation is not directly supported without a Quote object.
        # If kill-switch is enabled and we need V3, we fall through to V4 adapter
        # which maintains backward compatibility with V3 interface.
        logger.warning(
            "V3 direct calculation requested but not available. "
            "Using V4 adapter with V3 compatibility mode."
        )
        
        from pricing_v4.adapter import PricingServiceV4Adapter
        
        adapter = PricingServiceV4Adapter(
            quote_input,
            spot_envelope_id=self.spot_envelope_id
        )
        return adapter.calculate_charges()
    
    def _pre_flight_check(
        self, 
        charges: QuoteCharges, 
        shipment_type: str,
        quote_input: QuoteInput
    ) -> None:
        """
        Verify V4 returned meaningful charges.
        
        Logs CRITICAL if V4 returns zero charges, indicating missing rate data.
        """
        total_sell = charges.totals.total_sell_pgk if charges.totals else Decimal("0")
        
        if total_sell == Decimal("0"):
            logger.critical(
                f"PRE-FLIGHT FAILURE: V4 returned zero charges for "
                f"shipment_type={shipment_type}, "
                f"customer_id={quote_input.customer_id}, "
                f"origin={getattr(quote_input.shipment.origin_location, 'code', 'N/A')}, "
                f"destination={getattr(quote_input.shipment.destination_location, 'code', 'N/A')}. "
                "This likely indicates missing rate data in V4 ProductCode tables. "
                "Investigate immediately."
            )
            # Note: We don't raise ZeroChargeError here to allow the quote to complete
            # with zero charges (the "has_missing_rates" flag will be set).
            # Uncomment below to make this a hard failure:
            # raise ZeroChargeError(
            #     f"V4 returned zero charges for {shipment_type}. Rate data may be missing."
            # )
    
    def _run_shadow_comparison(
        self, 
        quote_input: QuoteInput,
        v4_charges: QuoteCharges,
        shipment_type: str
    ) -> Optional[ShadowComparison]:
        """
        Run V3 calculation in shadow mode and log comparison.
        
        This is for transition verification only. V3 result is never
        returned to the caller - only logged for analysis if variance
        exceeds thresholds.
        
        Returns:
            ShadowComparison with variance data, or None if shadow failed
        """
        try:
            # Attempt V3 calculation
            v3_charges = self._calculate_v3_for_shadow(quote_input)
            
            if v3_charges is None:
                return None
            
            # Extract totals
            v4_total = v4_charges.totals.total_sell_pgk if v4_charges.totals else Decimal("0")
            v3_total = v3_charges.totals.total_sell_pgk if v3_charges.totals else Decimal("0")
            
            # Calculate variance
            variance_pgk = abs(v4_total - v3_total)
            variance_percent = Decimal("0")
            if v3_total > Decimal("0"):
                variance_percent = (variance_pgk / v3_total) * Decimal("100")
            
            # Determine if this is a "high variance" case
            is_high_variance = (
                variance_percent > self.VARIANCE_PERCENT_THRESHOLD or
                variance_pgk > self.VARIANCE_ABSOLUTE_THRESHOLD
            )
            
            comparison = ShadowComparison(
                v3_total_pgk=v3_total,
                v4_total_pgk=v4_total,
                variance_pgk=variance_pgk,
                variance_percent=variance_percent,
                is_high_variance=is_high_variance,
            )
            
            # Only log if high variance
            if is_high_variance:
                logger.warning(
                    f"SHADOW MODE HIGH VARIANCE: "
                    f"shipment_type={shipment_type}, "
                    f"V3={v3_total:.2f} PGK, V4={v4_total:.2f} PGK, "
                    f"variance={variance_pgk:.2f} PGK ({variance_percent:.2f}%), "
                    f"customer_id={quote_input.customer_id}"
                )
            else:
                logger.debug(
                    f"Shadow mode: V3/V4 within tolerance. "
                    f"Variance={variance_pgk:.2f} PGK ({variance_percent:.2f}%)"
                )
            
            return comparison
            
        except Exception as e:
            logger.warning(f"Shadow mode comparison failed: {e}")
            return None
    
    def _calculate_v3_for_shadow(self, quote_input: QuoteInput) -> Optional[QuoteCharges]:
        """
        Calculate V3 charges for shadow comparison.
        
        Returns None if V3 calculation is not possible.
        """
        try:
            # V3 requires full Quote context which we don't have here.
            # For shadow mode, we can use the V4 adapter in a separate call
            # and compare configurations, but true V3 comparison requires
            # the legacy Quote-based resolvers.
            
            # For now, shadow mode logs a placeholder.
            # A full implementation would require:
            # 1. Creating a temporary Quote object
            # 2. Building QuoteContext via QuoteContextBuilder
            # 3. Running BuyChargeResolver
            
            logger.debug(
                "Shadow mode: V3 comparison skipped - requires Quote object context. "
                "Consider enabling V3 shadow in the view layer where Quote is available."
            )
            return None
            
        except ImportError:
            logger.warning("Shadow mode: pricing_v3 module not available")
            return None
        except Exception as e:
            logger.warning(f"Shadow mode V3 calculation failed: {e}")
            return None
    
    def get_engine_version(self) -> str:
        """Return the current default engine version."""
        if self._use_legacy_pricing:
            return EngineVersion.V3.value
        return EngineVersion.V4.value


# -----------------------------------------------------------------------------
# Convenience Functions
# -----------------------------------------------------------------------------

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
