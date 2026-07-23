from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from datetime import date
from enum import StrEnum
from typing import Any


PHASE_16D_RULE_VERSION = "PHASE_16D_LEG_AWARE_PRODUCTCODE_V1"


class JourneyDirection(StrEnum):
    IMPORT = "IMPORT"
    EXPORT = "EXPORT"


class JourneyPattern(StrEnum):
    IMP_POM = "IMP_POM"
    IMP_LAE = "IMP_LAE"
    IMP_HGU = "IMP_HGU"
    EXP_POM = "EXP_POM"
    EXP_LAE = "EXP_LAE"
    EXP_HGU = "EXP_HGU"


class LegRole(StrEnum):
    INTERNATIONAL_IMPORT = "INTERNATIONAL_IMPORT"
    INTERNATIONAL_EXPORT = "INTERNATIONAL_EXPORT"
    DOMESTIC_ON_FORWARDING = "DOMESTIC_ON_FORWARDING"
    DOMESTIC_PRE_CARRIAGE = "DOMESTIC_PRE_CARRIAGE"
    FINAL_PICKUP = "FINAL_PICKUP"
    FINAL_DELIVERY = "FINAL_DELIVERY"


class TransportMode(StrEnum):
    INTERNATIONAL_AIR = "INTERNATIONAL_AIR"
    DOMESTIC_AIR = "DOMESTIC_AIR"
    LOCAL_ROAD = "LOCAL_ROAD"


class CommercialPosition(StrEnum):
    ORIGIN = "ORIGIN"
    FREIGHT = "FREIGHT"
    DESTINATION = "DESTINATION"


class ProductCodeDomain(StrEnum):
    IMPORT = "IMPORT"
    EXPORT = "EXPORT"
    DOMESTIC = "DOMESTIC"


class ProductCodeResolutionStatus(StrEnum):
    ASSIGNED = "ASSIGNED"
    NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"
    NOT_FOUND = "NOT_FOUND"
    CONTEXT_INCOMPLETE = "CONTEXT_INCOMPLETE"
    REJECTED = "REJECTED"


class ProductCodeResolverBlockerCode(StrEnum):
    CONTEXT_MISSING_CANONICAL_CHARGE_TYPE = "CONTEXT_MISSING_CANONICAL_CHARGE_TYPE"
    CONTEXT_MISSING_LEG_ROLE = "CONTEXT_MISSING_LEG_ROLE"
    CONTEXT_MISSING_PRODUCT_CODE_DOMAIN = "CONTEXT_MISSING_PRODUCT_CODE_DOMAIN"
    CONTEXT_MISSING_COMMERCIAL_POSITION = "CONTEXT_MISSING_COMMERCIAL_POSITION"
    CONTEXT_MISSING_TRANSPORT_MODE = "CONTEXT_MISSING_TRANSPORT_MODE"
    PRODUCTCODE_CONTEXT_RULE_NOT_FOUND = "PRODUCTCODE_CONTEXT_RULE_NOT_FOUND"
    PRODUCTCODE_CONTEXT_RULE_AMBIGUOUS = "PRODUCTCODE_CONTEXT_RULE_AMBIGUOUS"
    PRODUCTCODE_DOMAIN_MISMATCH = "PRODUCTCODE_DOMAIN_MISMATCH"
    PRODUCTCODE_INACTIVE_OR_RETIRED = "PRODUCTCODE_INACTIVE_OR_RETIRED"
    PRODUCTCODE_RULE_INACTIVE_OR_UNAPPROVED = "PRODUCTCODE_RULE_INACTIVE_OR_UNAPPROVED"


@dataclass(frozen=True)
class ChargeContext:
    """Trusted leg-aware charge context for ProductCode resolution.

    The ProductCode domain is supplied from trusted leg construction. This
    contract intentionally has no raw/client direction field, so request JSON
    direction claims cannot influence ProductCode domain selection.
    """

    journey_direction: JourneyDirection
    journey_pattern: JourneyPattern
    leg_role: LegRole
    leg_sequence: int
    product_code_domain: ProductCodeDomain
    commercial_position: CommercialPosition
    transport_mode: TransportMode
    canonical_charge_type: str
    journey_id: str | None = None
    journey_revision: int | None = None
    leg_id: str | None = None
    leg_key: str | None = None
    operational_location: str | None = None
    charge_family: str | None = None
    calculation_basis: str | None = None
    service_scope: str | None = None
    currency: str | None = None
    tax_treatment: str | None = None
    effective_date: date | None = None
    source_evidence: dict[str, Any] = field(default_factory=dict)
    context_fingerprint: str | None = None

    def normalized_canonical_charge_type(self) -> str:
        return str(self.canonical_charge_type or "").strip().upper()

    def normalized_operational_location(self) -> str:
        return str(self.operational_location or "").strip().upper()

    def normalized_calculation_basis(self) -> str:
        return str(self.calculation_basis or "").strip().upper()

    def normalized_service_scope(self) -> str:
        return str(self.service_scope or "").strip().upper()

    def to_audit_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        for key, value in list(payload.items()):
            if isinstance(value, StrEnum):
                payload[key] = value.value
            elif isinstance(value, date):
                payload[key] = value.isoformat()
        return payload


def coerce_charge_context(value: ChargeContext | dict[str, Any]) -> ChargeContext:
    if isinstance(value, ChargeContext):
        return value
    data = dict(value or {})
    enum_fields = {
        "journey_direction": JourneyDirection,
        "journey_pattern": JourneyPattern,
        "leg_role": LegRole,
        "product_code_domain": ProductCodeDomain,
        "commercial_position": CommercialPosition,
        "transport_mode": TransportMode,
    }
    for field_name, enum_cls in enum_fields.items():
        data[field_name] = enum_cls(str(data.get(field_name) or "").strip().upper())
    if data.get("effective_date") and not isinstance(data["effective_date"], date):
        data["effective_date"] = date.fromisoformat(str(data["effective_date"]))
    allowed_fields = {contract_field.name for contract_field in fields(ChargeContext)}
    return ChargeContext(**{key: value for key, value in data.items() if key in allowed_fields})


@dataclass(frozen=True)
class ProductCodeResolutionResult:
    status: ProductCodeResolutionStatus
    selected_product_code: str | None = None
    selected_product_code_id: int | None = None
    candidate_product_codes: list[dict[str, Any]] = field(default_factory=list)
    resolved_context: dict[str, Any] = field(default_factory=dict)
    clarification_question: str | None = None
    review_reason: str | None = None
    blocker_codes: list[ProductCodeResolverBlockerCode] = field(default_factory=list)
    rule_version: str = PHASE_16D_RULE_VERSION
    audit_evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["status"] = self.status.value
        payload["blocker_codes"] = [code.value for code in self.blocker_codes]
        return payload
