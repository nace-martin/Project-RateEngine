"""
Shared completeness + SPOT coverage evaluation.

Completeness is defined by REQUIRED COMPONENTS per scope, not by charge amounts.
Coverage is satisfied if at least one line for a required component is present
and not marked as missing (is_rate_missing=False), regardless of price value.
"""

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Set

from core.dataclasses import CalculatedChargeLine
from quotes.buckets import normalize_bucket


COMPONENT_ORIGIN_LOCAL = "ORIGIN_LOCAL"
COMPONENT_FREIGHT = "FREIGHT"
COMPONENT_DESTINATION_LOCAL = "DESTINATION_LOCAL"

ALL_COMPONENTS = {
    COMPONENT_ORIGIN_LOCAL,
    COMPONENT_FREIGHT,
    COMPONENT_DESTINATION_LOCAL,
}


def _normalize_scope(scope: Optional[str]) -> str:
    if not scope:
        return "A2A"
    scope = scope.upper()
    if scope == "P2P":
        return "A2A"
    return scope


def required_components(shipment_type: Optional[str], service_scope: Optional[str]) -> Set[str]:
    shipment_type = (shipment_type or "").upper()
    scope = _normalize_scope(service_scope)

    # Domestic: freight only (consistent with existing SPOT rules)
    if shipment_type == "DOMESTIC":
        return {COMPONENT_FREIGHT}

    # Common scope rules for IMPORT/EXPORT
    if scope == "A2A":
        return {COMPONENT_FREIGHT}
    if scope == "D2A":
        return {COMPONENT_ORIGIN_LOCAL, COMPONENT_FREIGHT}
    if scope == "A2D":
        return {COMPONENT_DESTINATION_LOCAL}
    if scope == "D2D":
        return {COMPONENT_ORIGIN_LOCAL, COMPONENT_FREIGHT, COMPONENT_DESTINATION_LOCAL}

    # Default fallback
    return {COMPONENT_FREIGHT}


def component_from_bucket(bucket: Optional[str]) -> Optional[str]:
    leg = normalize_bucket(bucket)
    if leg == "ORIGIN":
        return COMPONENT_ORIGIN_LOCAL
    if leg == "MAIN":
        return COMPONENT_FREIGHT
    if leg == "DESTINATION":
        return COMPONENT_DESTINATION_LOCAL
    return None


def _line_is_covered(line: CalculatedChargeLine) -> bool:
    if getattr(line, "is_rate_missing", False):
        return False
    if getattr(line, "is_informational", False):
        return False
    return True


@dataclass(frozen=True)
class CoverageResult:
    required_components: Set[str]
    component_coverage: Dict[str, bool]
    missing_required: List[str]
    is_complete: bool
    is_spot_required: bool
    notes: Optional[str] = None


def evaluate_from_lines(
    lines: Iterable[CalculatedChargeLine],
    shipment_type: Optional[str],
    service_scope: Optional[str],
) -> CoverageResult:
    coverage: Dict[str, bool] = {comp: False for comp in ALL_COMPONENTS}
    for line in lines:
        component = component_from_bucket(getattr(line, "bucket", None))
        if not component:
            continue
        if _line_is_covered(line):
            coverage[component] = True

    required = required_components(shipment_type, service_scope)
    missing = [comp for comp in required if not coverage.get(comp, False)]
    is_complete = len(missing) == 0
    notes = None
    if missing:
        notes = f"Missing required components: {', '.join(missing)}"

    return CoverageResult(
        required_components=required,
        component_coverage=coverage,
        missing_required=missing,
        is_complete=is_complete,
        is_spot_required=not is_complete,
        notes=notes,
    )


def evaluate_from_availability(
    component_availability: Dict[str, bool],
    shipment_type: Optional[str],
    service_scope: Optional[str],
) -> CoverageResult:
    coverage = {comp: bool(component_availability.get(comp, False)) for comp in ALL_COMPONENTS}
    required = required_components(shipment_type, service_scope)
    missing = [comp for comp in required if not coverage.get(comp, False)]
    is_complete = len(missing) == 0
    notes = None
    if missing:
        notes = f"Missing required components: {', '.join(missing)}"

    return CoverageResult(
        required_components=required,
        component_coverage=coverage,
        missing_required=missing,
        is_complete=is_complete,
        is_spot_required=not is_complete,
        notes=notes,
    )
