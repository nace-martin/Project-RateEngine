from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Iterable

from django.db import models

from pricing_v4.category_rules import (
    is_import_destination_local_code,
    is_import_origin_local_code,
)
from pricing_v4.models import (
    DomesticCOGS,
    ExportCOGS,
    ImportCOGS,
    LocalCOGSRate,
    ProductCode,
)
from pricing_v4.services.rate_selector import serialize_rate_candidate
from quotes.completeness import (
    COMPONENT_DESTINATION_LOCAL,
    COMPONENT_FREIGHT,
    COMPONENT_ORIGIN_LOCAL,
    required_components,
)


@dataclass(frozen=True)
class RateResolutionContext:
    customer_id: Any
    shipment_type: str
    service_scope: str
    payment_term: str
    origin_airport: str
    destination_airport: str
    quote_date: date
    override_buy_currency: str | None = None
    override_agent_id: int | None = None
    override_carrier_id: int | None = None

    def normalized(self) -> "RateResolutionContext":
        return RateResolutionContext(
            customer_id=self.customer_id,
            shipment_type=_normalize_text(self.shipment_type) or "",
            service_scope=_normalize_scope(self.service_scope),
            payment_term=_normalize_text(self.payment_term) or "",
            origin_airport=_normalize_text(self.origin_airport) or "",
            destination_airport=_normalize_text(self.destination_airport) or "",
            quote_date=self.quote_date,
            override_buy_currency=_normalize_text(self.override_buy_currency),
            override_agent_id=self.override_agent_id,
            override_carrier_id=self.override_carrier_id,
        )


@dataclass(frozen=True)
class ResolvedRateDimensions:
    buy_currency: str | None
    agent_id: int | None
    carrier_id: int | None
    resolution_basis: str
    required_components: tuple[str, ...]
    buy_side_components: tuple[str, ...]
    candidate_path_count: int = 0
    trace: dict[str, Any] = field(default_factory=dict)


@dataclass
class CandidatePath:
    buy_currency: str
    counterparty_kind: str
    counterparty_id: int
    components: set[str] = field(default_factory=set)
    rows: list[models.Model] = field(default_factory=list)

    def add_row(self, component: str, row: models.Model) -> None:
        self.components.add(component)
        self.rows.append(row)


class RateResolutionError(Exception):
    error_code = "RATE_RESOLUTION_ERROR"
    status_code = 400
    resolution_reason = "UNKNOWN"

    def __init__(
        self,
        detail: str,
        *,
        context: RateResolutionContext,
        suggested_remediation: str,
        candidate_paths: list[CandidatePath] | None = None,
        missing_components: list[str] | None = None,
        ambiguous_dimensions: list[str] | None = None,
        resolution_basis: str = "pre_pricing_resolution",
    ):
        self.context = context
        self.detail = detail
        self.suggested_remediation = suggested_remediation
        self.candidate_paths = list(candidate_paths or [])
        self.missing_components = list(missing_components or [])
        self.ambiguous_dimensions = list(ambiguous_dimensions or [])
        self.resolution_basis = resolution_basis
        super().__init__(detail)


class RateResolutionAmbiguityError(RateResolutionError):
    error_code = "RATE_RESOLUTION_AMBIGUOUS"
    status_code = 409


class RateResolutionMissingCoverageError(RateResolutionError):
    error_code = "RATE_RESOLUTION_MISSING_COVERAGE"
    status_code = 400


def resolve_quote_rate_dimensions(context: RateResolutionContext) -> ResolvedRateDimensions:
    normalized = context.normalized()
    required = tuple(sorted(required_components(normalized.shipment_type, normalized.service_scope)))
    component_rows = _buy_side_component_rows(normalized, required)
    buy_side_components = tuple(
        component for component in required
        if component_rows.get(component)
    )

    if not buy_side_components:
        return ResolvedRateDimensions(
            buy_currency=None,
            agent_id=None,
            carrier_id=None,
            resolution_basis="no_buy_side_resolution_required",
            required_components=required,
            buy_side_components=buy_side_components,
            trace={
                "resolution_reason": "NO_BUY_SIDE_COMPONENTS",
                "component_rows": {component: 0 for component in required},
            },
        )

    component_rows = _apply_row_overrides(component_rows, normalized)
    candidate_paths = _build_candidate_paths(component_rows)

    shared_currency = normalized.override_buy_currency or _shared_currency(component_rows, buy_side_components)
    shared_counterparty = _shared_counterparty(component_rows, buy_side_components)

    agent_id = normalized.override_agent_id
    carrier_id = normalized.override_carrier_id
    if agent_id is None and carrier_id is None and shared_counterparty is not None:
        if shared_counterparty[0] == "agent":
            agent_id = shared_counterparty[1]
        elif shared_counterparty[0] == "carrier":
            carrier_id = shared_counterparty[1]

    resolution_basis = "component_level_resolution_only"
    if normalized.override_buy_currency or normalized.override_agent_id or normalized.override_carrier_id:
        resolution_basis = "request_overrides_applied"
    elif shared_currency is not None or shared_counterparty is not None:
        resolution_basis = "derived_shared_dimensions"

    return ResolvedRateDimensions(
        buy_currency=shared_currency,
        agent_id=agent_id,
        carrier_id=carrier_id,
        resolution_basis=resolution_basis,
        required_components=required,
        buy_side_components=buy_side_components,
        candidate_path_count=len(candidate_paths),
        trace={
            "resolution_reason": "SAFE_SHARED_DIMENSIONS_ONLY",
            "component_rows": {component: len(component_rows.get(component, ())) for component in required},
            "component_candidates": {
                component: {
                    "currencies": sorted({_normalize_text(getattr(row, "currency", None)) for row in rows if _normalize_text(getattr(row, "currency", None))}),
                    "counterparties": sorted(
                        f"{signature[0]}:{signature[1]}"
                        for signature in (_counterparty_signature(row) for row in rows)
                        if signature is not None
                    ),
                }
                for component, rows in component_rows.items()
                if rows
            },
            "resolved_shared_currency": shared_currency,
            "resolved_shared_counterparty": (
                None
                if shared_counterparty is None
                else {
                    "kind": shared_counterparty[0],
                    "id": shared_counterparty[1],
                }
            ),
            "candidate_paths": [_serialize_candidate_path(path) for path in candidate_paths[:10]],
        },
    )


def build_rate_resolution_error_payload(error: RateResolutionError) -> dict[str, Any]:
    return {
        "detail": error.detail,
        "error_code": error.error_code,
        "resolution_reason": getattr(error, "resolution_reason", error.resolution_reason),
        "resolution_basis": error.resolution_basis,
        "resolution_context": serialize_rate_resolution_context(error.context),
        "missing_components": error.missing_components,
        "ambiguous_dimensions": error.ambiguous_dimensions,
        "conflicting_rows": _serialize_conflicting_rows(error.candidate_paths),
        "candidate_paths": [_serialize_candidate_path(path) for path in error.candidate_paths[:10]],
        "suggested_remediation": error.suggested_remediation,
    }


def serialize_rate_resolution_context(context: RateResolutionContext) -> dict[str, Any]:
    normalized = context.normalized()
    payload = {
        "customer_id": str(normalized.customer_id),
        "shipment_type": normalized.shipment_type,
        "service_scope": normalized.service_scope,
        "payment_term": normalized.payment_term,
        "origin_airport": normalized.origin_airport,
        "destination_airport": normalized.destination_airport,
        "quote_date": normalized.quote_date.isoformat(),
        "override_buy_currency": normalized.override_buy_currency,
        "override_agent_id": normalized.override_agent_id,
        "override_carrier_id": normalized.override_carrier_id,
    }
    return {key: value for key, value in payload.items() if value not in (None, "", [], {})}


def serialize_resolved_rate_dimensions(resolved: ResolvedRateDimensions) -> dict[str, Any]:
    return {
        "buy_currency": resolved.buy_currency,
        "agent_id": resolved.agent_id,
        "carrier_id": resolved.carrier_id,
        "resolution_basis": resolved.resolution_basis,
        "required_components": list(resolved.required_components),
        "buy_side_components": list(resolved.buy_side_components),
        "candidate_path_count": resolved.candidate_path_count,
        "trace": resolved.trace,
    }


def _normalize_text(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().upper()
    return normalized or None


def _normalize_scope(value: Any) -> str:
    normalized = _normalize_text(value) or "A2A"
    if normalized == "P2P":
        return "A2A"
    return normalized


def _active_queryset(model_cls: type[models.Model], quote_date: date):
    return model_cls.objects.filter(valid_from__lte=quote_date, valid_until__gte=quote_date)


def _buy_side_component_rows(
    context: RateResolutionContext,
    required: Iterable[str],
) -> dict[str, list[models.Model]]:
    required_set = set(required)
    rows_by_component: dict[str, list[models.Model]] = {component: [] for component in required_set}

    if context.shipment_type == "DOMESTIC":
        domestic_rows = (
            _active_queryset(DomesticCOGS, context.quote_date)
            .filter(origin_zone=context.origin_airport, destination_zone=context.destination_airport)
            .select_related("product_code", "agent", "carrier")
        )
        for row in domestic_rows:
            component = _classify_domestic_component(row)
            if component in required_set:
                rows_by_component[component].append(row)
        return rows_by_component

    if context.shipment_type == "EXPORT":
        lane_rows = (
            _active_queryset(ExportCOGS, context.quote_date)
            .filter(origin_airport=context.origin_airport, destination_airport=context.destination_airport)
            .select_related("product_code", "agent", "carrier")
        )
        for row in lane_rows:
            component = _classify_export_lane_component(row)
            if component in required_set:
                rows_by_component[component].append(row)

        local_rows = (
            _active_queryset(LocalCOGSRate, context.quote_date)
            .filter(direction="EXPORT", location__in=[code for code in [context.origin_airport, context.destination_airport] if code])
            .select_related("product_code", "agent", "carrier")
        )
        for row in local_rows:
            component = _classify_export_local_component(row, context.origin_airport, context.destination_airport)
            if component in required_set:
                rows_by_component[component].append(row)
        return rows_by_component

    lane_rows = (
        _active_queryset(ImportCOGS, context.quote_date)
        .filter(origin_airport=context.origin_airport, destination_airport=context.destination_airport)
        .select_related("product_code", "agent", "carrier")
    )
    for row in lane_rows:
        component = _classify_import_lane_component(row)
        if component in required_set:
            rows_by_component[component].append(row)

    local_rows = (
        _active_queryset(LocalCOGSRate, context.quote_date)
        .filter(direction="IMPORT", location=context.destination_airport)
        .select_related("product_code", "agent", "carrier")
    )
    for row in local_rows:
        if COMPONENT_DESTINATION_LOCAL in required_set:
            rows_by_component[COMPONENT_DESTINATION_LOCAL].append(row)
    return rows_by_component


def _classify_export_lane_component(row: models.Model) -> str | None:
    category = _normalize_text(getattr(getattr(row, "product_code", None), "category", None)) or ""
    code = _normalize_text(getattr(getattr(row, "product_code", None), "code", None)) or ""
    if category == ProductCode.CATEGORY_FREIGHT or "FRT" in code or "FREIGHT" in code:
        return COMPONENT_FREIGHT
    return None


def _classify_export_local_component(
    row: models.Model,
    origin_airport: str,
    destination_airport: str,
) -> str | None:
    location = _normalize_text(getattr(row, "location", None))
    if location == origin_airport:
        return COMPONENT_ORIGIN_LOCAL
    if location == destination_airport:
        return COMPONENT_DESTINATION_LOCAL
    return None


def _classify_import_lane_component(row: models.Model) -> str | None:
    category = _normalize_text(getattr(getattr(row, "product_code", None), "category", None)) or ""
    code = _normalize_text(getattr(getattr(row, "product_code", None), "code", None)) or ""
    if category == ProductCode.CATEGORY_FREIGHT or "FRT" in code or "FREIGHT" in code:
        return COMPONENT_FREIGHT
    if is_import_origin_local_code(code):
        return COMPONENT_ORIGIN_LOCAL
    if is_import_destination_local_code(code):
        return COMPONENT_DESTINATION_LOCAL
    if category in {ProductCode.CATEGORY_CARTAGE, ProductCode.CATEGORY_CLEARANCE}:
        return COMPONENT_DESTINATION_LOCAL
    return COMPONENT_ORIGIN_LOCAL


def _classify_domestic_component(row: models.Model) -> str | None:
    category = _normalize_text(getattr(getattr(row, "product_code", None), "category", None)) or ""
    code = _normalize_text(getattr(getattr(row, "product_code", None), "code", None)) or ""
    if category == ProductCode.CATEGORY_FREIGHT or "FRT" in code or "FREIGHT" in code:
        return COMPONENT_FREIGHT
    return COMPONENT_ORIGIN_LOCAL


def _build_candidate_paths(component_rows: dict[str, list[models.Model]]) -> list[CandidatePath]:
    path_index: dict[tuple[str, str, int], CandidatePath] = {}
    for component, rows in component_rows.items():
        for row in rows:
            counterparty = _counterparty_signature(row)
            if counterparty is None:
                continue
            signature = (row.currency, counterparty[0], counterparty[1])
            path = path_index.setdefault(
                signature,
                CandidatePath(
                    buy_currency=row.currency,
                    counterparty_kind=counterparty[0],
                    counterparty_id=counterparty[1],
                ),
            )
            path.add_row(component, row)
    return list(path_index.values())


def _apply_row_overrides(
    component_rows: dict[str, list[models.Model]],
    context: RateResolutionContext,
) -> dict[str, list[models.Model]]:
    filtered_rows: dict[str, list[models.Model]] = {}
    for component, rows in component_rows.items():
        filtered = list(rows)
        if context.override_buy_currency:
            filtered = [row for row in filtered if _normalize_text(getattr(row, "currency", None)) == context.override_buy_currency]
        if context.override_agent_id is not None:
            filtered = [row for row in filtered if getattr(row, "agent_id", None) == context.override_agent_id]
        if context.override_carrier_id is not None:
            filtered = [row for row in filtered if getattr(row, "carrier_id", None) == context.override_carrier_id]
        filtered_rows[component] = filtered
    return filtered_rows


def _shared_currency(
    component_rows: dict[str, list[models.Model]],
    buy_side_components: tuple[str, ...],
) -> str | None:
    currency_sets: list[set[str]] = []
    for component in buy_side_components:
        currencies = {
            _normalize_text(getattr(row, "currency", None))
            for row in component_rows.get(component, [])
            if _normalize_text(getattr(row, "currency", None))
        }
        if currencies:
            currency_sets.append(currencies)
    if not currency_sets:
        return None
    shared = set.intersection(*currency_sets)
    if len(shared) == 1:
        return next(iter(shared))
    return None


def _shared_counterparty(
    component_rows: dict[str, list[models.Model]],
    buy_side_components: tuple[str, ...],
) -> tuple[str, int] | None:
    signature_sets: list[set[tuple[str, int]]] = []
    for component in buy_side_components:
        signatures = {
            signature
            for signature in (_counterparty_signature(row) for row in component_rows.get(component, []))
            if signature is not None
        }
        if signatures:
            signature_sets.append(signatures)
    if not signature_sets:
        return None
    shared = set.intersection(*signature_sets)
    if len(shared) == 1:
        return next(iter(shared))
    return None


def _counterparty_signature(row: models.Model) -> tuple[str, int] | None:
    agent_id = getattr(row, "agent_id", None)
    carrier_id = getattr(row, "carrier_id", None)
    if agent_id is not None:
        return ("agent", agent_id)
    if carrier_id is not None:
        return ("carrier", carrier_id)
    return None


def _serialize_candidate_path(path: CandidatePath) -> dict[str, Any]:
    return {
        "buy_currency": path.buy_currency,
        "counterparty_kind": path.counterparty_kind,
        "agent_id": path.counterparty_id if path.counterparty_kind == "agent" else None,
        "carrier_id": path.counterparty_id if path.counterparty_kind == "carrier" else None,
        "components": sorted(path.components),
        "sample_rows": [serialize_rate_candidate(row) for row in path.rows[:10]],
    }


def _serialize_conflicting_rows(candidate_paths: list[CandidatePath]) -> list[dict[str, Any]]:
    seen_ids: set[int] = set()
    rows: list[dict[str, Any]] = []
    for path in candidate_paths:
        for row in path.rows:
            row_id = getattr(row, "pk", None)
            if row_id in seen_ids:
                continue
            seen_ids.add(row_id)
            rows.append(serialize_rate_candidate(row))
            if len(rows) >= 20:
                return rows
    return rows


def _describe_path_ambiguity(valid_paths: list[CandidatePath]) -> tuple[str, list[str], str]:
    currencies = sorted({path.buy_currency for path in valid_paths})
    agent_ids = sorted({path.counterparty_id for path in valid_paths if path.counterparty_kind == "agent"})
    carrier_ids = sorted({path.counterparty_id for path in valid_paths if path.counterparty_kind == "carrier"})
    kinds = sorted({path.counterparty_kind for path in valid_paths})

    if len(currencies) > 1 and not agent_ids and not carrier_ids:
        return (
            "Multiple active buy currencies exist for the required buy-side path.",
            ["buy_currency"],
            "Retire or revise the conflicting currency rows, or add an explicit business default for buy currency.",
        )
    if len(currencies) > 1 and (len(agent_ids) == 1 or len(carrier_ids) == 1):
        return (
            "Multiple active buy currencies exist for the same valid counterparty path.",
            ["buy_currency"],
            "Retire or revise the conflicting currency rows for this counterparty, or add an explicit business default.",
        )
    if len(agent_ids) > 1 and not carrier_ids:
        return (
            "Multiple active agents exist for this quote context.",
            ["agent_id"],
            "Retire or revise the overlapping agent rows, or add an explicit default agent for this lane.",
        )
    if len(carrier_ids) > 1 and not agent_ids:
        return (
            "Multiple active carriers exist for this quote context.",
            ["carrier_id"],
            "Retire or revise the overlapping carrier rows, or add an explicit default carrier for this lane.",
        )
    if len(kinds) > 1:
        return (
            "Both agent- and carrier-scoped buy-side paths remain active for this quote context.",
            ["agent_id", "carrier_id"],
            "Retire or revise the conflicting paths, or define an explicit business default so one counterparty path wins.",
        )
    return (
        "Multiple valid buy-side paths remain active for this quote context.",
        ["buy_currency", "agent_id", "carrier_id"],
        "Retire or revise the overlapping active rows so one deterministic buy-side path remains.",
    )


def _resolution_reason_code(valid_paths: list[CandidatePath]) -> str:
    currencies = {path.buy_currency for path in valid_paths}
    agent_ids = {path.counterparty_id for path in valid_paths if path.counterparty_kind == "agent"}
    carrier_ids = {path.counterparty_id for path in valid_paths if path.counterparty_kind == "carrier"}
    kinds = {path.counterparty_kind for path in valid_paths}

    if len(currencies) > 1 and (len(agent_ids) == 1 or len(carrier_ids) == 1):
        return "MULTIPLE_BUY_CURRENCIES"
    if len(agent_ids) > 1 and not carrier_ids:
        return "MULTIPLE_ACTIVE_AGENTS"
    if len(carrier_ids) > 1 and not agent_ids:
        return "MULTIPLE_ACTIVE_CARRIERS"
    if len(kinds) > 1:
        return "MULTIPLE_COUNTERPARTY_TYPES"
    return "MULTIPLE_VALID_BUY_PATHS"
