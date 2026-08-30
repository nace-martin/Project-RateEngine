from __future__ import annotations

import hashlib
import json
import logging
from decimal import Decimal, InvalidOperation
from typing import Any

from core.business_rules import classify_png_shipment
from quotes.completeness import ALL_COMPONENTS, evaluate_from_availability
from quotes.quote_result_contract import shipment_metrics_from_quote


logger = logging.getLogger(__name__)


class SpotQuoteContextError(ValueError):
    def __init__(self, code: str, message: str, *, details: dict | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


def build_trusted_quote_context(quote) -> tuple[dict, list[str]]:
    origin = quote.origin_location
    destination = quote.destination_location
    origin_country = getattr(getattr(origin, "country", None), "code", None)
    destination_country = getattr(getattr(destination, "country", None), "code", None)
    try:
        direction = classify_png_shipment(origin_country, destination_country)
    except ValueError as exc:
        raise SpotQuoteContextError(
            "SPOT_QUOTE_DIRECTION_CONFLICT",
            str(exc),
            details={
                "origin_country": origin_country,
                "destination_country": destination_country,
                "quote_shipment_type": quote.shipment_type,
            },
        ) from exc
    if direction != str(quote.shipment_type or "").upper():
        raise SpotQuoteContextError(
            "SPOT_QUOTE_DIRECTION_CONFLICT",
            "Persisted Quote shipment type conflicts with its origin and destination.",
            details={
                "origin_country": origin_country,
                "destination_country": destination_country,
                "quote_shipment_type": quote.shipment_type,
                "derived_shipment_type": direction,
            },
        )

    request_payload = quote.request_details_json if isinstance(quote.request_details_json, dict) else {}
    dimensions = request_payload.get("dimensions")
    dimensions = dimensions if isinstance(dimensions, list) else []
    required = {
        "customer": quote.customer_id,
        "contact": quote.contact_id,
        "origin_location": origin,
        "destination_location": destination,
        "origin_country": origin_country,
        "destination_country": destination_country,
        "shipment_type": quote.shipment_type,
        "mode": quote.mode,
        "service_scope": quote.service_scope,
        "payment_term": quote.payment_term,
        "commodity": quote.commodity_code,
        "output_currency": quote.output_currency,
        "dimensions": dimensions,
    }
    if direction != "DOMESTIC" and not quote.incoterm:
        required["incoterm"] = quote.incoterm
    missing = [field for field, value in required.items() if value in (None, "", [])]
    if missing:
        return {}, missing

    metrics = shipment_metrics_from_quote(quote, None)
    if metrics["pieces"] <= 0 or metrics["chargeable_weight"] <= 0:
        return {}, ["dimensions"]

    context = {
        "quote_id": str(quote.id),
        "customer_id": str(quote.customer_id),
        "customer_name": quote.customer.name,
        "contact_id": str(quote.contact_id),
        "origin_location_id": str(quote.origin_location_id),
        "destination_location_id": str(quote.destination_location_id),
        "origin_country": str(origin_country).upper(),
        "destination_country": str(destination_country).upper(),
        "origin_code": str(origin.code).upper(),
        "destination_code": str(destination.code).upper(),
        "direction": direction,
        "shipment_type": direction,
        "mode": str(quote.mode).upper(),
        "service_domain": str(quote.mode).upper(),
        "service_scope": str(quote.service_scope).upper(),
        "quote_date": quote.created_at.date().isoformat(),
        "incoterm": quote.incoterm,
        "payment_term": str(quote.payment_term).upper(),
        "commodity": quote.commodity_code,
        "is_dangerous_goods": bool(quote.is_dangerous_goods),
        "dimensions": dimensions,
        "pieces": metrics["pieces"],
        "actual_weight_kg": float(metrics["actual_weight"]),
        "volumetric_weight_kg": float(metrics["volumetric_weight"]),
        "chargeable_weight_kg": float(metrics["chargeable_weight"]),
        "total_weight_kg": float(metrics["chargeable_weight"]),
        "pickup_requested": str(quote.service_scope).upper() in {"D2A", "D2D"},
        "delivery_requested": str(quote.service_scope).upper() in {"A2D", "D2D"},
        "output_currency": quote.output_currency,
        "source_currency": request_payload.get("buy_currency"),
        "owner_id": str(quote.owner_id) if quote.owner_id else None,
        "organization_id": str(quote.organization_id) if quote.organization_id else None,
        "branch_id": str(quote.branch_id) if quote.branch_id else None,
        "department_id": str(quote.department_id) if quote.department_id else None,
    }
    return context, []


def derive_missing_components(context: dict) -> list[str] | None:
    try:
        from quotes.spot_services import RateAvailabilityService

        outcomes = RateAvailabilityService.get_component_outcomes(
            origin_airport=context["origin_code"],
            destination_airport=context["destination_code"],
            direction=context["direction"],
            service_scope=context["service_scope"],
            payment_term=context["payment_term"],
        )
        coverage = evaluate_from_availability(
            component_availability={
                component: outcome.get("status") in {"covered_exact", "covered_fallback"}
                for component, outcome in outcomes.items()
            },
            shipment_type=context["direction"],
            service_scope=context["service_scope"],
        )
        return sorted(coverage.missing_required)
    except Exception:
        logger.warning(
            "Trusted Quote rate-coverage evaluation failed.",
            exc_info=False,
        )
        return None


def trusted_context_hash(context: dict) -> str:
    return hashlib.sha256(json.dumps(context, sort_keys=True).encode()).hexdigest()


def validate_client_context(client_context: dict, trusted_context: dict) -> list[dict]:
    def text(value: Any) -> str:
        return str(value).strip()

    def upper(value: Any) -> str:
        return text(value).upper()

    def lower(value: Any) -> str:
        return text(value).lower()

    def decimal(value: Any) -> str:
        try:
            return str(Decimal(str(value)).normalize())
        except (InvalidOperation, TypeError, ValueError):
            return text(value)

    def integer(value: Any) -> int | str:
        try:
            return int(value)
        except (TypeError, ValueError):
            return text(value)

    def boolean(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        return lower(value) in {"1", "true", "yes"}

    def dimensions(value: Any):
        if not isinstance(value, list):
            return value
        normalized = []
        for item in value:
            if not isinstance(item, dict):
                normalized.append(item)
                continue
            normalized.append(tuple(sorted(
                (
                    key,
                    integer(item[key]) if key == "pieces"
                    else decimal(item[key]) if key in {
                        "length_cm", "width_cm", "height_cm", "gross_weight_kg"
                    }
                    else text(item[key]),
                )
                for key in item
            )))
        return tuple(normalized)

    normalizers = {
        "quote_id": text,
        "customer_id": text,
        "customer_name": text,
        "contact_id": text,
        "origin_location_id": text,
        "destination_location_id": text,
        "origin_country": upper,
        "destination_country": upper,
        "origin_code": upper,
        "destination_code": upper,
        "direction": upper,
        "shipment_type": upper,
        "mode": upper,
        "service_scope": lower,
        "incoterm": upper,
        "payment_term": lower,
        "commodity": upper,
        "is_dangerous_goods": boolean,
        "dangerous_goods": boolean,
        "dimensions": dimensions,
        "pieces": integer,
        "actual_weight_kg": decimal,
        "volumetric_weight_kg": decimal,
        "total_weight_kg": decimal,
        "chargeable_weight_kg": decimal,
        "chargeable_weight": decimal,
        "output_currency": upper,
        "source_currency": upper,
        "owner_id": text,
        "organization_id": text,
        "operating_entity_id": text,
        "branch_id": text,
        "department_id": text,
    }
    aliases = {
        "dangerous_goods": "is_dangerous_goods",
        "chargeable_weight_kg": "total_weight_kg",
        "chargeable_weight": "total_weight_kg",
    }
    conflicts = []
    for field, normalize in normalizers.items():
        if field not in client_context or client_context[field] in (None, ""):
            continue
        trusted_field = aliases.get(field, field)
        client_value = normalize(client_context[field])
        trusted_value = normalize(trusted_context.get(trusted_field))
        if client_value != trusted_value:
            conflicts.append({
                "field": field,
                "client_value": client_value,
                "trusted_value": trusted_value,
            })

    if "missing_components" in client_context:
        raw = client_context["missing_components"]
        supplied = [upper(item) for item in raw] if isinstance(raw, list) else []
        invalid = sorted(set(supplied) - ALL_COMPONENTS)
        trusted = [upper(item) for item in trusted_context.get("missing_components") or []]
        if invalid or set(supplied) != set(trusted):
            conflicts.append({
                "field": "missing_components",
                "client_value": supplied,
                "trusted_value": trusted,
                "invalid_values": invalid,
            })
    return conflicts
