# backend/quotes/services/dispatcher.py
"""
Pricing Dispatcher - Single Entry Point for Quote Calculations (V4-only)

This dispatcher is intentionally hard-wired to Pricing V4. Legacy V2/V3 routing,
kill-switches, and shadow-mode comparisons were removed during decommissioning.
"""

import logging
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Optional
from uuid import UUID

from core.dataclasses import QuoteCharges, QuoteInput

logger = logging.getLogger(__name__)


class EngineVersion(str, Enum):
    """Supported pricing engine versions."""

    V4 = "V4"


class ShipmentType(str, Enum):
    """Shipment type routing keys."""

    IMPORT = "IMPORT"
    EXPORT = "EXPORT"
    DOMESTIC = "DOMESTIC"


class RoutingError(Exception):
    """Raised when a request cannot be routed to a valid shipment type."""


class ZeroChargeError(Exception):
    """Reserved for optional hard-fail pre-flight enforcement."""


class RoutingMap:
    """
    Explicit declaration of supported shipment types.

    All supported shipment types are routed to Pricing V4.
    """

    DEFAULT_ROUTING = {
        ShipmentType.IMPORT.value: EngineVersion.V4,
        ShipmentType.EXPORT.value: EngineVersion.V4,
        ShipmentType.DOMESTIC.value: EngineVersion.V4,
    }

    @classmethod
    def get_engine_version(cls, shipment_type: str) -> EngineVersion:
        normalized = shipment_type.upper() if shipment_type else None
        if normalized not in cls.DEFAULT_ROUTING:
            raise RoutingError(
                f"Cannot route shipment_type='{shipment_type}'. "
                f"Supported types: {list(cls.DEFAULT_ROUTING.keys())}. "
                "Refusing to guess - explicit routing required."
            )
        return cls.DEFAULT_ROUTING[normalized]


@dataclass
class CalculationResult:
    """Result wrapper that includes engine version metadata."""

    charges: QuoteCharges
    engine_version: str
    shadow_comparison: Optional[dict] = None


class PricingDispatcher:
    """
    Single entry point for all quote calculations.

    This dispatcher validates shipment type routing and executes Pricing V4 only.
    """

    def __init__(self, spot_envelope_id: Optional[UUID] = None):
        self.spot_envelope_id = spot_envelope_id

    def calculate(self, quote_input: QuoteInput) -> CalculationResult:
        """
        Execute pricing calculation using Pricing V4 only.

        Raises:
            RoutingError: If the request cannot be routed
        """
        shipment_type = self._extract_shipment_type(quote_input)
        engine_version = RoutingMap.get_engine_version(shipment_type)

        logger.info(
            "PricingDispatcher routing: shipment_type=%s, engine=%s, customer_id=%s",
            shipment_type,
            engine_version.value,
            quote_input.customer_id,
        )

        v4_charges = self._calculate_v4(quote_input)
        self._pre_flight_check(v4_charges, shipment_type, quote_input)

        return CalculationResult(
            charges=v4_charges,
            engine_version=EngineVersion.V4.value,
            shadow_comparison=None,
        )

    def _extract_shipment_type(self, quote_input: QuoteInput) -> str:
        shipment = quote_input.shipment
        if shipment and hasattr(shipment, "shipment_type") and shipment.shipment_type:
            return shipment.shipment_type
        if shipment and hasattr(shipment, "direction") and shipment.direction:
            return shipment.direction
        raise RoutingError("Cannot determine shipment type from quote input")

    def _calculate_v4(self, quote_input: QuoteInput) -> QuoteCharges:
        from pricing_v4.adapter import PricingServiceV4Adapter

        adapter = PricingServiceV4Adapter(
            quote_input,
            spot_envelope_id=self.spot_envelope_id,
        )
        return adapter.calculate_charges()

    def _pre_flight_check(
        self,
        charges: QuoteCharges,
        shipment_type: str,
        quote_input: QuoteInput,
    ) -> None:
        """
        Verify V4 returned meaningful charges.

        Logs CRITICAL if V4 returns zero charges, indicating missing rate data.
        """
        total_sell = charges.totals.total_sell_pgk if charges.totals else Decimal("0")

        if total_sell == Decimal("0"):
            logger.critical(
                "PRE-FLIGHT FAILURE: V4 returned zero charges for shipment_type=%s, "
                "customer_id=%s, origin=%s, destination=%s. "
                "This likely indicates missing rate data in V4 ProductCode tables. "
                "Investigate immediately.",
                shipment_type,
                quote_input.customer_id,
                getattr(quote_input.shipment.origin_location, "code", "N/A"),
                getattr(quote_input.shipment.destination_location, "code", "N/A"),
            )

    def get_engine_version(self) -> str:
        """Return the engine version this dispatcher uses."""

        return EngineVersion.V4.value


def calculate_quote(
    quote_input: QuoteInput,
    spot_envelope_id: Optional[UUID] = None,
) -> CalculationResult:
    """
    Convenience entry point for quote calculations (V4-only).
    """

    dispatcher = PricingDispatcher(spot_envelope_id=spot_envelope_id)
    return dispatcher.calculate(quote_input)
