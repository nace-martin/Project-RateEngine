# backend/pricing_v4/dispatcher.py
"""
Pricing V4 Dispatcher

V4-only dispatcher facade used by callers that want an explicit pricing_v4
entrypoint. Legacy V3 shadow comparison and fallback logic has been removed.
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional
from uuid import UUID

from core.dataclasses import QuoteCharges, QuoteInput
from pricing_v4.adapter import PricingServiceV4Adapter
from pricing_v4.engine.domestic_engine import DomesticPricingEngine
from pricing_v4.engine.export_engine import ExportPricingEngine
from pricing_v4.engine.import_engine import ImportPricingEngine

logger = logging.getLogger(__name__)


class EngineVersion(str, Enum):
    """Supported pricing engine versions."""

    V4 = "V4"


class ShipmentType(str, Enum):
    """Shipment type routing keys."""

    IMPORT = "IMPORT"
    EXPORT = "EXPORT"
    DOMESTIC = "DOMESTIC"


@dataclass
class RoutingMap:
    """Explicit declaration of supported V4 shipment routes."""

    @staticmethod
    def get_engine_class(shipment_type: str):
        routing = {
            ShipmentType.IMPORT.value: ImportPricingEngine,
            ShipmentType.EXPORT.value: ExportPricingEngine,
            ShipmentType.DOMESTIC.value: DomesticPricingEngine,
        }
        if not shipment_type:
            raise ValueError("Unsupported shipment type: None. Supported types: IMPORT, EXPORT, DOMESTIC")
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
    """Single entry point for V4 quote calculations."""

    def __init__(self, spot_envelope_id: Optional[UUID] = None):
        self.spot_envelope_id = spot_envelope_id

    def calculate(self, quote_input: QuoteInput) -> CalculationResult:
        shipment_type = self._extract_shipment_type(quote_input)

        logger.info(
            "pricing_v4 dispatcher routing: shipment_type=%s, engine=V4, customer_id=%s",
            shipment_type,
            quote_input.customer_id,
        )

        # Validate supported shipment type explicitly.
        RoutingMap.get_engine_class(shipment_type)

        charges = self._calculate_v4(quote_input)
        return CalculationResult(charges=charges, engine_version=EngineVersion.V4.value)

    def _extract_shipment_type(self, quote_input: QuoteInput) -> str:
        shipment = quote_input.shipment
        if shipment and hasattr(shipment, "shipment_type") and shipment.shipment_type:
            return shipment.shipment_type
        if shipment and hasattr(shipment, "direction") and shipment.direction:
            return shipment.direction
        raise ValueError("Cannot determine shipment type from quote input")

    def _calculate_v4(self, quote_input: QuoteInput) -> QuoteCharges:
        adapter = PricingServiceV4Adapter(
            quote_input,
            spot_envelope_id=self.spot_envelope_id,
        )
        return adapter.calculate_charges()

    def get_engine_version(self) -> str:
        return EngineVersion.V4.value


def calculate_quote(
    quote_input: QuoteInput,
    spot_envelope_id: Optional[UUID] = None,
) -> CalculationResult:
    """Convenience V4-only calculation entrypoint."""

    dispatcher = PricingDispatcher(spot_envelope_id=spot_envelope_id)
    return dispatcher.calculate(quote_input)
