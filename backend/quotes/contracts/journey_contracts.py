from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Any

from pricing_v4.contracts.charge_context import (
    JourneyDirection,
    JourneyPattern,
    LegRole,
    ProductCodeDomain,
    TransportMode,
)

PHASE_16E_A_RULE_VERSION = "PHASE_16E_A_AIR_JOURNEY_PLANNER_V1"
PNG_COUNTRY_CODE = "PG"
PNG_GATEWAY_CODE = "POM"
SUPPORTED_CUSTOMER_CODES = {"POM", "LAE", "HGU"}


class JourneyStatus(StrEnum):
    PLANNED = "PLANNED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    PRICED = "PRICED"
    FINALIZED = "FINALIZED"
    SUPERSEDED = "SUPERSEDED"


class JourneyPlannerBlockerCode(StrEnum):
    JOURNEY_COUNTRY_MISSING = "JOURNEY_COUNTRY_MISSING"
    JOURNEY_DIRECTION_UNSUPPORTED = "JOURNEY_DIRECTION_UNSUPPORTED"
    JOURNEY_GATEWAY_INVALID = "JOURNEY_GATEWAY_INVALID"
    JOURNEY_PATTERN_UNSUPPORTED = "JOURNEY_PATTERN_UNSUPPORTED"
    JOURNEY_MULTI_STOP_UNSUPPORTED = "JOURNEY_MULTI_STOP_UNSUPPORTED"
    JOURNEY_REQUEST_INVALID = "JOURNEY_REQUEST_INVALID"
    ROUTE_AUTOMATION_DISABLED = "ROUTE_AUTOMATION_DISABLED"
    ROUTE_RATE_GATE_UNMET = "ROUTE_RATE_GATE_UNMET"


@dataclass(frozen=True)
class JourneyRequest:
    origin_country: str
    destination_country: str
    customer_origin_code: str
    customer_destination_code: str
    service_domain: str
    service_scope: str
    quote_date: date
    pieces: int = 0
    actual_weight: Decimal | None = None
    volumetric_weight: Decimal | None = None
    chargeable_weight: Decimal | None = None
    commodity: str = ""
    pickup_requested: bool = False
    delivery_requested: bool = False
    raw_evidence: dict[str, Any] = field(default_factory=dict)

    def normalized(self) -> JourneyRequest:
        return JourneyRequest(
            origin_country=_norm(self.origin_country, 2),
            destination_country=_norm(self.destination_country, 2),
            customer_origin_code=_norm(self.customer_origin_code, 10),
            customer_destination_code=_norm(self.customer_destination_code, 10),
            service_domain=_norm(self.service_domain, 20),
            service_scope=_norm(self.service_scope, 20),
            quote_date=self.quote_date,
            pieces=int(self.pieces or 0),
            actual_weight=_decimal_or_none(self.actual_weight),
            volumetric_weight=_decimal_or_none(self.volumetric_weight),
            chargeable_weight=_decimal_or_none(self.chargeable_weight),
            commodity=_norm(self.commodity, 50),
            pickup_requested=bool(self.pickup_requested),
            delivery_requested=bool(self.delivery_requested),
            raw_evidence=dict(self.raw_evidence or {}),
        )

    def fingerprint_payload(self) -> dict[str, Any]:
        normalized = self.normalized()
        return {
            "origin_country": normalized.origin_country,
            "destination_country": normalized.destination_country,
            "customer_origin_code": normalized.customer_origin_code,
            "customer_destination_code": normalized.customer_destination_code,
            "service_domain": normalized.service_domain,
            "service_scope": normalized.service_scope,
            "quote_date": normalized.quote_date.isoformat(),
            "pieces": normalized.pieces,
            "actual_weight": _decimal_string(normalized.actual_weight),
            "volumetric_weight": _decimal_string(normalized.volumetric_weight),
            "chargeable_weight": _decimal_string(normalized.chargeable_weight),
            "commodity": normalized.commodity,
            "pickup_requested": normalized.pickup_requested,
            "delivery_requested": normalized.delivery_requested,
            "rule_version": PHASE_16E_A_RULE_VERSION,
        }

    def input_fingerprint(self) -> str:
        payload = json.dumps(self.fingerprint_payload(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self.normalized())
        payload["quote_date"] = self.normalized().quote_date.isoformat()
        for field_name in ["actual_weight", "volumetric_weight", "chargeable_weight"]:
            payload[field_name] = _decimal_string(payload[field_name])
        return payload


@dataclass(frozen=True)
class JourneyLeg:
    sequence: int
    leg_key: str
    role: LegRole
    transport_mode: TransportMode
    origin_code: str
    destination_code: str
    product_code_domain: ProductCodeDomain
    required: bool = True
    service_scope: str = ""
    chargeable_weight: Decimal | None = None
    status: JourneyStatus = JourneyStatus.PLANNED
    rate_coverage_status: str = "NOT_CHECKED"
    blockers: list[JourneyPlannerBlockerCode] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        for key in ["role", "transport_mode", "product_code_domain", "status"]:
            payload[key] = payload[key].value
        payload["chargeable_weight"] = _decimal_string(payload["chargeable_weight"])
        payload["blockers"] = [blocker.value for blocker in self.blockers]
        return payload


@dataclass(frozen=True)
class JourneyPlan:
    request: JourneyRequest
    direction: JourneyDirection | None
    pattern: JourneyPattern | None
    gateway_code: str
    route_policy_key: str
    rule_version: str
    input_fingerprint: str
    status: JourneyStatus
    legs: list[JourneyLeg] = field(default_factory=list)
    blockers: list[JourneyPlannerBlockerCode] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "normalized_request": self.request.to_dict(),
            "direction": self.direction.value if self.direction else None,
            "pattern": self.pattern.value if self.pattern else None,
            "gateway_code": self.gateway_code,
            "route_policy_key": self.route_policy_key,
            "rule_version": self.rule_version,
            "input_fingerprint": self.input_fingerprint,
            "status": self.status.value,
            "legs": [leg.to_dict() for leg in self.legs],
            "blockers": [blocker.value for blocker in self.blockers],
        }


def coerce_journey_request(value: JourneyRequest | dict[str, Any]) -> JourneyRequest:
    if isinstance(value, JourneyRequest):
        return value.normalized()
    data = dict(value or {})
    validation_blockers: list[str] = []
    quote_date_value = _date_or_sentinel(data.get("quote_date"), validation_blockers)
    pieces = _int_or_zero(data.get("pieces"), validation_blockers)
    actual_weight = _decimal_or_none(data.get("actual_weight") or data.get("actual_weight_kg"), validation_blockers)
    volumetric_weight = _decimal_or_none(data.get("volumetric_weight") or data.get("volumetric_weight_kg"), validation_blockers)
    chargeable_weight = _decimal_or_none(data.get("chargeable_weight") or data.get("chargeable_weight_kg"), validation_blockers)
    pickup_requested = _bool_or_false(data.get("pickup_requested", False), validation_blockers)
    delivery_requested = _bool_or_false(data.get("delivery_requested", False), validation_blockers)
    raw_evidence = dict(data)
    if validation_blockers:
        raw_evidence["_validation_blockers"] = validation_blockers
    return JourneyRequest(
        origin_country=data.get("origin_country") or data.get("originCountry") or "",
        destination_country=data.get("destination_country") or data.get("destinationCountry") or "",
        customer_origin_code=data.get("customer_origin_code") or data.get("customerOriginCode") or data.get("origin_code") or "",
        customer_destination_code=data.get("customer_destination_code") or data.get("customerDestinationCode") or data.get("destination_code") or "",
        service_domain=data.get("service_domain") or data.get("serviceDomain") or "",
        service_scope=data.get("service_scope") or data.get("serviceScope") or "",
        quote_date=quote_date_value,
        pieces=pieces,
        actual_weight=actual_weight,
        volumetric_weight=volumetric_weight,
        chargeable_weight=chargeable_weight,
        commodity=data.get("commodity") or "",
        pickup_requested=pickup_requested,
        delivery_requested=delivery_requested,
        raw_evidence=raw_evidence,
    ).normalized()


def _date_or_sentinel(value: Any, validation_blockers: list[str]) -> date:
    if value in (None, ""):
        validation_blockers.append(JourneyPlannerBlockerCode.JOURNEY_REQUEST_INVALID.value)
        return date(1970, 1, 1)
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        validation_blockers.append(JourneyPlannerBlockerCode.JOURNEY_REQUEST_INVALID.value)
        return date(1970, 1, 1)


def _int_or_zero(value: Any, validation_blockers: list[str]) -> int:
    if value in (None, ""):
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        validation_blockers.append(JourneyPlannerBlockerCode.JOURNEY_REQUEST_INVALID.value)
        return 0


def _bool_or_false(value: Any, validation_blockers: list[str]) -> bool:
    if isinstance(value, bool):
        return value
    if value in (None, ""):
        return False
    if isinstance(value, str) and value.strip().lower() in {"true", "false"}:
        return value.strip().lower() == "true"
    validation_blockers.append(JourneyPlannerBlockerCode.JOURNEY_REQUEST_INVALID.value)
    return False


def _decimal_or_none(value: Any, validation_blockers: list[str] | None = None) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        if validation_blockers is not None:
            validation_blockers.append(JourneyPlannerBlockerCode.JOURNEY_REQUEST_INVALID.value)
        return None


def _norm(value: Any, max_len: int) -> str:
    return str(value or "").strip().upper()[:max_len]


def _decimal_string(value: Any) -> str | None:
    if value is None:
        return None
    return format(Decimal(str(value)), "f")
