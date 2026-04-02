from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Iterable, Optional

from core.charge_rules import (
    CALCULATION_FLAT,
    CALCULATION_LOOKUP_RATE,
    CALCULATION_MANUAL_OVERRIDE,
    CALCULATION_MIN_OR_PER_UNIT,
    CALCULATION_PERCENT_OF_BASE,
    CALCULATION_PER_UNIT,
    CALCULATION_TIERED_BREAK,
)
from core.commodity import DEFAULT_COMMODITY_CODE, commodity_label
from quotes.buckets import resolve_quote_line_leg
from quotes.completeness import (
    COMPONENT_DESTINATION_LOCAL,
    COMPONENT_FREIGHT,
    COMPONENT_ORIGIN_LOCAL,
    evaluate_from_lines,
)


ZERO_DECIMAL = Decimal("0.00")
ONE_DECIMAL = Decimal("1.00")
RATE_PRECISION = Decimal("0.000001")


class QuoteRateSource:
    DB_TARIFF = "DB_TARIFF"
    PARTNER_SPOT = "PARTNER_SPOT"
    MANUAL_OVERRIDE = "MANUAL_OVERRIDE"
    FALLBACK_RULE = "FALLBACK_RULE"
    IMPORTED_RATECARD = "IMPORTED_RATECARD"
    LEGACY_STORED_QUOTE = "LEGACY_STORED_QUOTE"
    UNKNOWN = "UNKNOWN"


class QuoteCostSource:
    DB_TARIFF = "DB_TARIFF"
    PARTNER_SPOT = "PARTNER_SPOT"
    MANUAL_OVERRIDE = "MANUAL_OVERRIDE"
    FALLBACK_RULE = "FALLBACK_RULE"
    IMPORTED_RATECARD = "IMPORTED_RATECARD"
    LEGACY_STORED_QUOTE = "LEGACY_STORED_QUOTE"
    UNKNOWN = "UNKNOWN"


class QuoteComponent:
    ORIGIN_LOCAL = COMPONENT_ORIGIN_LOCAL
    FREIGHT = COMPONENT_FREIGHT
    DESTINATION_LOCAL = COMPONENT_DESTINATION_LOCAL
    OTHER = "OTHER"


class QuoteRuleFamily:
    FX_CAF_MARGIN = "FX_CAF_MARGIN"
    PASSTHROUGH = "PASSTHROUGH"
    RATE_OF_BASE = "RATE_OF_BASE"
    STANDARD_RATE = "STANDARD_RATE"
    FLAT = "FLAT"
    CONDITIONAL = "CONDITIONAL"
    UNKNOWN = "UNKNOWN"


UNIT_LABELS = {
    "SHIPMENT": "Per Shipment",
    "KG": "Per KG",
    "WM": "Per W/M",
    "CBM": "Per CBM",
    "TEU": "Per TEU",
    "FEU": "Per FEU",
    "PALLET": "Per Pallet",
    "KM": "Per KM",
    "PAGE": "Per Page",
}

RATE_SOURCE_PRIORITY = [
    QuoteRateSource.MANUAL_OVERRIDE,
    QuoteRateSource.PARTNER_SPOT,
    QuoteRateSource.FALLBACK_RULE,
    QuoteRateSource.IMPORTED_RATECARD,
    QuoteRateSource.DB_TARIFF,
    QuoteRateSource.LEGACY_STORED_QUOTE,
    QuoteRateSource.UNKNOWN,
]

COMPONENT_SORT_ORDER = {
    QuoteComponent.ORIGIN_LOCAL: 1,
    QuoteComponent.FREIGHT: 2,
    QuoteComponent.DESTINATION_LOCAL: 3,
    QuoteComponent.OTHER: 9,
}


def decimal_or_zero(value: Any) -> Decimal:
    try:
        if value is None or value == "":
            return ZERO_DECIMAL
        if isinstance(value, Decimal):
            return value
        return Decimal(str(value))
    except Exception:
        return ZERO_DECIMAL


def decimal_or_none(value: Any) -> Optional[Decimal]:
    if value is None or value == "":
        return None
    try:
        if isinstance(value, Decimal):
            return value
        return Decimal(str(value))
    except Exception:
        return None


def _dedupe(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        value = str(item or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def _full_name(user: Any) -> Optional[str]:
    if not user:
        return None
    first = str(getattr(user, "first_name", "") or "").strip()
    last = str(getattr(user, "last_name", "") or "").strip()
    full_name = " ".join(part for part in [first, last] if part)
    if full_name:
        return full_name
    username = getattr(user, "username", None)
    return str(username).strip() if username else None


def _piece_list_from_payload(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []

    flat_dimensions = payload.get("dimensions")
    if isinstance(flat_dimensions, list):
        return [item for item in flat_dimensions if isinstance(item, dict)]

    shipment = payload.get("shipment")
    if isinstance(shipment, dict):
        pieces = shipment.get("pieces")
        if isinstance(pieces, list):
            return [item for item in pieces if isinstance(item, dict)]

    return []


def _payload_value(payload: Any, *keys: str) -> Any:
    current = payload
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _calculate_piece_metrics(payload: Any) -> dict[str, Any]:
    pieces_payload = _piece_list_from_payload(payload)
    total_pieces = 0
    total_actual = ZERO_DECIMAL
    total_volumetric = ZERO_DECIMAL
    summary_parts: list[str] = []

    for item in pieces_payload:
        piece_count = max(int(decimal_or_zero(item.get("pieces")) or 0), 1)
        length = decimal_or_zero(item.get("length_cm"))
        width = decimal_or_zero(item.get("width_cm"))
        height = decimal_or_zero(item.get("height_cm"))
        gross = decimal_or_zero(item.get("gross_weight_kg"))

        total_pieces += piece_count
        total_actual += gross * piece_count
        if length > 0 and width > 0 and height > 0:
            total_volumetric += ((length * width * height) / Decimal("6000")) * piece_count

        package_type = str(item.get("package_type") or "Piece").strip()
        if length > 0 and width > 0 and height > 0:
            dims = f"{length.normalize()} x {width.normalize()} x {height.normalize()} cm"
            summary_parts.append(f"{piece_count} x {package_type} @ {dims}")
        else:
            summary_parts.append(f"{piece_count} x {package_type}")

    actual_weight = total_actual.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    volumetric_weight = total_volumetric.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    chargeable_weight = max(actual_weight, volumetric_weight)

    if chargeable_weight == ZERO_DECIMAL:
        nested_total = decimal_or_zero(_payload_value(payload, "shipment", "total_weight_kg"))
        flat_total = decimal_or_zero(_payload_value(payload, "total_weight_kg"))
        chargeable_weight = nested_total or flat_total or ZERO_DECIMAL
        actual_weight = actual_weight or chargeable_weight

    return {
        "pieces": total_pieces,
        "actual_weight": actual_weight,
        "volumetric_weight": volumetric_weight,
        "chargeable_weight": chargeable_weight,
        "dimensions_summary": "; ".join(summary_parts) if summary_parts else None,
    }


def shipment_metrics_from_quote(quote: Any, version: Any) -> dict[str, Any]:
    payload_candidates = [
        getattr(quote, "request_details_json", None),
        getattr(version, "payload_json", None),
    ]

    metrics = {
        "pieces": 0,
        "actual_weight": ZERO_DECIMAL,
        "volumetric_weight": ZERO_DECIMAL,
        "chargeable_weight": ZERO_DECIMAL,
        "dimensions_summary": None,
    }
    for payload in payload_candidates:
        candidate = _calculate_piece_metrics(payload)
        if candidate["pieces"] or candidate["chargeable_weight"] > 0 or candidate["dimensions_summary"]:
            return candidate
    return metrics


def _component_from_leg(leg: Optional[str]) -> str:
    value = str(leg or "").upper()
    if value == "ORIGIN":
        return QuoteComponent.ORIGIN_LOCAL
    if value in {"MAIN", "FREIGHT"}:
        return QuoteComponent.FREIGHT
    if value == "DESTINATION":
        return QuoteComponent.DESTINATION_LOCAL
    return QuoteComponent.OTHER


def component_from_leg(leg: Optional[str]) -> str:
    return _component_from_leg(leg)


def component_from_quote_line(line: Any) -> str:
    return _component_from_leg(resolve_quote_line_leg(line))


def infer_source_flags(
    raw_source: Any,
    *,
    stored_is_spot_sourced: Optional[bool] = None,
    stored_is_manual_override: Optional[bool] = None,
) -> tuple[bool, bool]:
    source = str(raw_source or "").strip().upper()
    is_spot_sourced = (
        stored_is_spot_sourced
        if stored_is_spot_sourced is not None
        else ("SPOT" in source or "AGENT REPLY" in source or "PARTNER" in source)
    )
    is_manual_override = (
        stored_is_manual_override
        if stored_is_manual_override is not None
        else any(token in source for token in ["MANUAL", "OVERRIDE"])
    )
    return bool(is_spot_sourced), bool(is_manual_override)


def derive_canonical_rate(
    *,
    stored_rate: Any = None,
    rule_family: Optional[str] = None,
    unit_type: Optional[str] = None,
    quantity: Any = None,
    sell_amount: Any = None,
) -> Optional[Decimal]:
    explicit_rate = decimal_or_none(stored_rate)
    if explicit_rate is not None:
        return explicit_rate.quantize(RATE_PRECISION, rounding=ROUND_HALF_UP)

    normalized_rule_family = str(rule_family or "").strip().upper()
    normalized_unit_type = str(unit_type or "").strip().upper()
    normalized_quantity = decimal_or_none(quantity)
    normalized_sell_amount = decimal_or_none(sell_amount)
    if normalized_sell_amount is None:
        return None

    if normalized_rule_family in {CALCULATION_PER_UNIT, CALCULATION_MIN_OR_PER_UNIT}:
        if normalized_quantity and normalized_quantity > ZERO_DECIMAL:
            return (normalized_sell_amount / normalized_quantity).quantize(
                RATE_PRECISION,
                rounding=ROUND_HALF_UP,
            )
        return None

    if normalized_unit_type in {"", "SHIPMENT"} and normalized_rule_family in {
        CALCULATION_FLAT,
        CALCULATION_LOOKUP_RATE,
        CALCULATION_MANUAL_OVERRIDE,
    }:
        return normalized_sell_amount.quantize(RATE_PRECISION, rounding=ROUND_HALF_UP)

    return None


def build_persisted_line_item_metadata(
    *,
    raw_cost_source: Any,
    service_component: Any = None,
    engine_version: Optional[str] = "V4",
    product_code: Optional[str] = None,
    component: Optional[str] = None,
    basis: Optional[str] = None,
    rule_family: Optional[str] = None,
    service_family: Optional[str] = None,
    unit_type: Optional[str] = None,
    quantity: Any = None,
    rate: Any = None,
    sell_amount: Any = None,
    is_rate_missing: bool = False,
    leg: Optional[str] = None,
    calculation_notes: Optional[str] = None,
    stored_is_spot_sourced: Optional[bool] = None,
    stored_is_manual_override: Optional[bool] = None,
    canonical_cost_source: Optional[str] = None,
    rate_source: Optional[str] = None,
) -> dict[str, Any]:
    service_code = getattr(service_component, "service_code", None)
    persisted_unit_type = str(
        unit_type or getattr(service_component, "unit", None) or "SHIPMENT"
    ).strip().upper()
    persisted_component = component or component_from_leg(leg)
    persisted_rule_family = rule_family or infer_stored_rule_family(
        type(
            "_LineLike",
            (),
            {
                "cost_source": raw_cost_source,
                "is_rate_missing": is_rate_missing,
            },
        )(),
        service_component=service_component,
    )
    persisted_service_family = service_family
    if persisted_service_family in {"", None}:
        persisted_service_family = infer_service_family(
            pricing_method=getattr(service_code, "pricing_method", None),
            conditional=False,
        )

    is_spot_sourced, is_manual_override = infer_source_flags(
        raw_cost_source,
        stored_is_spot_sourced=stored_is_spot_sourced,
        stored_is_manual_override=stored_is_manual_override,
    )
    persisted_rate_source = rate_source or normalize_rate_source(
        raw_cost_source,
        engine_version=engine_version,
        is_spot_sourced=is_spot_sourced,
        is_manual_override=is_manual_override,
        is_rate_missing=is_rate_missing,
    )
    persisted_cost_source = canonical_cost_source or normalize_cost_source(
        raw_cost_source,
        engine_version=engine_version,
        is_spot_sourced=is_spot_sourced,
        is_manual_override=is_manual_override,
        is_rate_missing=is_rate_missing,
    )
    persisted_rate = derive_canonical_rate(
        stored_rate=rate,
        rule_family=persisted_rule_family,
        unit_type=persisted_unit_type,
        quantity=quantity,
        sell_amount=sell_amount,
    )

    return {
        "product_code": product_code or getattr(service_component, "code", None) or "",
        "component": persisted_component,
        "basis": basis or basis_for_unit(persisted_unit_type),
        "rule_family": persisted_rule_family,
        "service_family": persisted_service_family,
        "unit_type": persisted_unit_type,
        "rate": persisted_rate,
        "rate_source": persisted_rate_source,
        "canonical_cost_source": persisted_cost_source,
        "is_spot_sourced": is_spot_sourced,
        "is_manual_override": is_manual_override,
        "calculation_notes": calculation_notes,
    }


def build_persisted_quote_total_metadata(totals: Any) -> dict[str, Any]:
    service_notes = getattr(totals, "service_notes", None) or getattr(totals, "notes", None)
    customer_notes = getattr(totals, "customer_notes", None)
    internal_notes = getattr(totals, "internal_notes", None)
    warnings = list(getattr(totals, "warnings", []) or [])
    audit_metadata = getattr(totals, "audit_metadata", {}) or {}
    return {
        "service_notes": str(service_notes) if service_notes else None,
        "customer_notes": str(customer_notes) if customer_notes else None,
        "internal_notes": str(internal_notes) if internal_notes else None,
        "warnings_json": warnings,
        "audit_metadata_json": audit_metadata if isinstance(audit_metadata, dict) else {},
    }


def normalize_rate_source(
    raw_source: Any,
    *,
    engine_version: Optional[str] = None,
    is_spot_sourced: bool = False,
    is_manual_override: bool = False,
    is_rate_missing: bool = False,
) -> str:
    source = str(raw_source or "").strip().upper()

    if is_manual_override or "MANUAL" in source or "OVERRIDE" in source:
        return QuoteRateSource.MANUAL_OVERRIDE
    if is_spot_sourced or "SPOT" in source or "AGENT REPLY" in source or "PARTNER" in source:
        return QuoteRateSource.PARTNER_SPOT
    if "RATECARD" in source:
        return QuoteRateSource.IMPORTED_RATECARD
    if is_rate_missing or "DEFAULT" in source or "FALLBACK" in source or "MISSING" in source:
        return QuoteRateSource.FALLBACK_RULE
    if source in {"BASE_COST", "COGS", "SURCHARGE", "SYSTEM", "V4 ENGINE"}:
        return QuoteRateSource.DB_TARIFF
    if engine_version and str(engine_version).upper() != "V4":
        return QuoteRateSource.LEGACY_STORED_QUOTE
    if source:
        return QuoteRateSource.DB_TARIFF
    if engine_version and str(engine_version).upper() != "V4":
        return QuoteRateSource.LEGACY_STORED_QUOTE
    return QuoteRateSource.UNKNOWN


def normalize_cost_source(
    raw_source: Any,
    *,
    engine_version: Optional[str] = None,
    is_spot_sourced: bool = False,
    is_manual_override: bool = False,
    is_rate_missing: bool = False,
) -> str:
    normalized = normalize_rate_source(
        raw_source,
        engine_version=engine_version,
        is_spot_sourced=is_spot_sourced,
        is_manual_override=is_manual_override,
        is_rate_missing=is_rate_missing,
    )
    mapping = {
        QuoteRateSource.DB_TARIFF: QuoteCostSource.DB_TARIFF,
        QuoteRateSource.PARTNER_SPOT: QuoteCostSource.PARTNER_SPOT,
        QuoteRateSource.MANUAL_OVERRIDE: QuoteCostSource.MANUAL_OVERRIDE,
        QuoteRateSource.FALLBACK_RULE: QuoteCostSource.FALLBACK_RULE,
        QuoteRateSource.IMPORTED_RATECARD: QuoteCostSource.IMPORTED_RATECARD,
        QuoteRateSource.LEGACY_STORED_QUOTE: QuoteCostSource.LEGACY_STORED_QUOTE,
        QuoteRateSource.UNKNOWN: QuoteCostSource.UNKNOWN,
    }
    return mapping[normalized]


def aggregate_rate_source(line_items: Iterable[dict[str, Any]], engine_version: Optional[str] = None) -> str:
    sources = {
        str(item.get("rate_source") or "").strip().upper()
        for item in line_items
        if item.get("rate_source")
    }
    if not sources:
        return QuoteRateSource.LEGACY_STORED_QUOTE if engine_version and str(engine_version).upper() != "V4" else QuoteRateSource.UNKNOWN
    for candidate in RATE_SOURCE_PRIORITY:
        if candidate in sources:
            return candidate
    return QuoteRateSource.UNKNOWN


def infer_service_family(
    *,
    pricing_method: Optional[str] = None,
    conditional: bool = False,
) -> Optional[str]:
    # `rule_family` is reserved for calculation-family values in the canonical
    # contract. Any legacy semantic grouping derived from service-code pricing
    # metadata is surfaced separately as `service_family`.
    method = str(pricing_method or "").strip().upper()
    if conditional:
        return QuoteRuleFamily.CONDITIONAL
    if method in {
        QuoteRuleFamily.FX_CAF_MARGIN,
        QuoteRuleFamily.PASSTHROUGH,
        QuoteRuleFamily.RATE_OF_BASE,
        QuoteRuleFamily.STANDARD_RATE,
    }:
        return method
    return None


def infer_stored_rule_family(
    line: Any,
    *,
    service_component: Any = None,
) -> str:
    raw_source = str(getattr(line, "cost_source", "") or "").upper()
    unit_type = str(getattr(service_component, "unit", None) or "SHIPMENT").strip().upper()

    if "MANUAL" in raw_source or "OVERRIDE" in raw_source:
        return CALCULATION_MANUAL_OVERRIDE
    if getattr(service_component, "percent_of_component_id", None) or getattr(service_component, "percent_value", None):
        return CALCULATION_PERCENT_OF_BASE
    if "% OF " in raw_source:
        return CALCULATION_PERCENT_OF_BASE
    if getattr(service_component, "tiering_json", None):
        return CALCULATION_TIERED_BREAK

    shipment_like_units = {"", "SHIPMENT"}
    per_unit_units = {"KG", "WM", "CBM", "TEU", "FEU", "PALLET", "KM", "PAGE", "AWB", "TRIP", "SET", "LINE", "MAN", "RT"}

    if unit_type in per_unit_units:
        min_charge = decimal_or_zero(getattr(service_component, "min_charge_pgk", None))
        if min_charge > ZERO_DECIMAL:
            return CALCULATION_MIN_OR_PER_UNIT
        return CALCULATION_PER_UNIT

    if bool(getattr(line, "is_rate_missing", False)):
        return CALCULATION_LOOKUP_RATE

    if unit_type in shipment_like_units:
        return CALCULATION_FLAT

    return CALCULATION_LOOKUP_RATE


def quantity_for_unit(unit_type: Optional[str], metrics: dict[str, Any]) -> Decimal:
    normalized = str(unit_type or "").strip().upper()
    if normalized == "KG":
        return decimal_or_zero(metrics.get("chargeable_weight")) or ZERO_DECIMAL
    if normalized == "PALLET":
        return Decimal(metrics.get("pieces") or 0)
    return ONE_DECIMAL


def basis_for_unit(unit_type: Optional[str]) -> str:
    normalized = str(unit_type or "").strip().upper()
    return UNIT_LABELS.get(normalized, "Per Shipment")


def display_tax_amount(line: Any, display_currency: str) -> Decimal:
    if str(display_currency or "").upper() != "PGK":
        return (
            decimal_or_zero(getattr(line, "sell_fcy_incl_gst", None))
            - decimal_or_zero(getattr(line, "sell_fcy", None))
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return (
        decimal_or_zero(getattr(line, "sell_pgk_incl_gst", None))
        - decimal_or_zero(getattr(line, "sell_pgk", None))
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def build_tax_breakdown_payload(lines: Iterable[Any], totals: Any, display_currency: str) -> dict[str, Any]:
    line_list = list(lines or [])
    gst_amount = ZERO_DECIMAL
    gst_percent = ZERO_DECIMAL
    by_code: dict[str, Decimal] = {}

    for line in line_list:
        line_amount = display_tax_amount(line, display_currency)
        label = str(getattr(line, "gst_category", None) or getattr(getattr(line, "service_component", None), "tax_code", None) or "GST")
        by_code[label] = by_code.get(label, ZERO_DECIMAL) + line_amount
        gst_amount += line_amount
        gst_percent = max(gst_percent, decimal_or_zero(getattr(line, "gst_rate", None)) * Decimal("100"))

    if totals and gst_amount == ZERO_DECIMAL:
        if str(display_currency or "").upper() != "PGK":
            gst_amount = (
                decimal_or_zero(getattr(totals, "total_sell_fcy_incl_gst", None))
                - decimal_or_zero(getattr(totals, "total_sell_fcy", None))
            ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        else:
            gst_amount = (
                decimal_or_zero(getattr(totals, "total_sell_pgk_incl_gst", None))
                - decimal_or_zero(getattr(totals, "total_sell_pgk", None))
            ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if gst_amount or not by_code:
            by_code["GST"] = gst_amount

    tax_basis = ", ".join(sorted(key for key in by_code.keys() if key))
    return {
        "gst_percent": gst_percent.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        "gst_amount": gst_amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        "tax_basis": tax_basis or None,
        "by_code": by_code,
    }


def build_fx_applied_payload(version: Any, lines: Iterable[Any], display_currency: str) -> dict[str, Any]:
    line_list = list(lines or [])
    fx_rate = None
    for line in line_list:
        exchange_rate = decimal_or_none(getattr(line, "exchange_rate", None))
        line_currency = str(getattr(line, "sell_fcy_currency", None) or getattr(line, "cost_fcy_currency", None) or "").upper()
        if exchange_rate is not None and line_currency and line_currency != "PGK":
            fx_rate = exchange_rate
            break

    fx_snapshot = getattr(version, "fx_snapshot", None)
    return {
        "applied": fx_rate is not None,
        "rate": fx_rate,
        "source": getattr(fx_snapshot, "source", None),
        "snapshot_date": getattr(fx_snapshot, "as_of_timestamp", None),
        "caf_percent": decimal_or_none(getattr(fx_snapshot, "caf_percent", None)),
        "currency": display_currency,
    }


def line_item_from_quote_line(
    line: Any,
    *,
    metrics: dict[str, Any],
    display_currency: str,
    engine_version: Optional[str],
    sort_order: int,
) -> dict[str, Any]:
    service_component = getattr(line, "service_component", None)
    unit_type = str(
        getattr(line, "unit_type", None) or getattr(service_component, "unit", None) or "SHIPMENT"
    ).upper()
    component = getattr(line, "component", None) or component_from_quote_line(line)
    included_in_total = not any(
        [
            bool(getattr(line, "is_rate_missing", False)),
            bool(getattr(line, "is_informational", False)),
            bool(getattr(line, "conditional", False)),
        ]
    )
    is_spot_sourced, is_manual_override = infer_source_flags(
        getattr(line, "cost_source", None),
        stored_is_spot_sourced=getattr(line, "is_spot_sourced", None),
        stored_is_manual_override=getattr(line, "is_manual_override", None),
    )
    rate_source = getattr(line, "rate_source", None) or normalize_rate_source(
        getattr(line, "cost_source", None),
        engine_version=engine_version,
        is_spot_sourced=is_spot_sourced,
        is_manual_override=is_manual_override,
        is_rate_missing=bool(getattr(line, "is_rate_missing", False)),
    )
    cost_source = getattr(line, "canonical_cost_source", None) or normalize_cost_source(
        getattr(line, "cost_source", None),
        engine_version=engine_version,
        is_spot_sourced=is_spot_sourced,
        is_manual_override=is_manual_override,
        is_rate_missing=bool(getattr(line, "is_rate_missing", False)),
    )

    customer_currency = str(
        getattr(line, "sell_fcy_currency", None) or display_currency or "PGK"
    ).upper()
    if customer_currency == "PGK":
        sell_amount = decimal_or_zero(getattr(line, "sell_pgk", None))
    else:
        sell_amount = decimal_or_zero(getattr(line, "sell_fcy", None))

    tax_amount = display_tax_amount(line, customer_currency)
    notes = _dedupe(
        [
            getattr(line, "cost_source_description", None),
            "Conditional line excluded from totals" if getattr(line, "conditional", False) else "",
            "Informational line excluded from totals" if getattr(line, "is_informational", False) else "",
            "Rate missing upstream" if getattr(line, "is_rate_missing", False) else "",
        ]
    )
    calculation_notes = getattr(line, "calculation_notes", None) or (" | ".join(notes) if notes else None)
    persisted_rule_family = getattr(line, "rule_family", None) or infer_stored_rule_family(
        line,
        service_component=service_component,
    )
    service_family = getattr(line, "service_family", None)
    if service_family == "":
        service_family = None
    quantity = quantity_for_unit(unit_type, metrics)

    return {
        "line_id": str(getattr(line, "id", "") or ""),
        "product_code": getattr(line, "product_code", None) or getattr(service_component, "code", None) or "",
        "description": getattr(service_component, "description", None) or getattr(line, "cost_source_description", None) or "Charge",
        "component": component,
        "basis": getattr(line, "basis", None) or basis_for_unit(unit_type),
        "rule_family": persisted_rule_family,
        "service_family": (
            service_family
            if service_family is not None
            else infer_service_family(
                pricing_method=getattr(getattr(service_component, "service_code", None), "pricing_method", None),
                conditional=bool(getattr(line, "conditional", False)),
            )
        ),
        "unit_type": unit_type,
        "quantity": quantity,
        "currency": customer_currency,
        "cost_currency": "PGK",
        "sell_currency": customer_currency,
        "rate": derive_canonical_rate(
            stored_rate=getattr(line, "rate", None),
            rule_family=persisted_rule_family,
            unit_type=unit_type,
            quantity=quantity,
            sell_amount=sell_amount,
        ),
        "cost_amount": decimal_or_zero(getattr(line, "cost_pgk", None)),
        "sell_amount": sell_amount,
        "tax_code": getattr(line, "gst_category", None) or getattr(service_component, "tax_code", None) or "GST",
        "tax_amount": tax_amount,
        "included_in_total": included_in_total,
        "cost_source": cost_source,
        "rate_source": rate_source,
        "calculation_notes": calculation_notes,
        "is_spot_sourced": is_spot_sourced,
        "is_manual_override": is_manual_override,
        "sort_order": sort_order,
    }


def build_quote_result_from_quote(quote: Any, version: Any = None) -> dict[str, Any]:
    active_version = version or getattr(quote, "latest_version", None)
    if active_version is None and hasattr(quote, "versions"):
        active_version = quote.versions.order_by("-version_number").first()

    lines = list(
        active_version.lines.select_related("service_component__service_code").all()
    ) if active_version else []
    totals = getattr(active_version, "totals", None) if active_version else None
    engine_version = getattr(active_version, "engine_version", None)
    display_currency = str(
        getattr(quote, "output_currency", None)
        or getattr(totals, "total_sell_fcy_currency", None)
        or "PGK"
    ).upper()
    metrics = shipment_metrics_from_quote(quote, active_version)

    line_items = []
    for index, line in enumerate(lines):
        line_item = line_item_from_quote_line(
            line,
            metrics=metrics,
            display_currency=display_currency,
            engine_version=engine_version,
            sort_order=((index + 1) * 10),
        )
        line_item["sort_order"] = (COMPONENT_SORT_ORDER.get(line_item["component"], 9) * 100) + index
        line_items.append(line_item)
    line_items.sort(key=lambda item: item["sort_order"])
    coverage = evaluate_from_lines(lines, getattr(quote, "shipment_type", None), getattr(quote, "service_scope", None))

    warnings: list[str] = []
    warnings.extend(list(getattr(totals, "warnings_json", []) or []))
    if totals and getattr(totals, "notes", None):
        warnings.append(str(totals.notes))
    if coverage.notes:
        warnings.append(str(coverage.notes))
    for line in lines:
        if getattr(line, "is_rate_missing", False):
            description = getattr(getattr(line, "service_component", None), "description", None) or "Charge"
            warnings.append(f"Rate missing for {description}")
    line_rate_source = aggregate_rate_source(line_items, engine_version)
    spot_required = bool(coverage.is_spot_required or line_rate_source == QuoteRateSource.PARTNER_SPOT)
    if spot_required and line_rate_source == QuoteRateSource.PARTNER_SPOT:
        warnings.append("This quote includes SPOT-assisted pricing input.")

    sell_total = ZERO_DECIMAL
    if totals:
        if display_currency == "PGK":
            sell_total = decimal_or_zero(getattr(totals, "total_sell_pgk_incl_gst", None))
        else:
            sell_total = decimal_or_zero(getattr(totals, "total_sell_fcy_incl_gst", None))

    prepared_by = _full_name(getattr(active_version, "created_by", None)) or _full_name(getattr(quote, "created_by", None))

    return {
        "quote_id": str(getattr(quote, "id", "") or ""),
        "status": getattr(quote, "status", None),
        "customer_name": getattr(getattr(quote, "customer", None), "name", None),
        "service_scope": getattr(quote, "service_scope", None),
        "mode": getattr(quote, "mode", None),
        "origin": str(getattr(quote, "origin_location", "") or ""),
        "destination": str(getattr(quote, "destination_location", "") or ""),
        "incoterm": getattr(quote, "incoterm", None),
        "cargo_type": commodity_label(getattr(quote, "commodity_code", None) or DEFAULT_COMMODITY_CODE),
        "pieces": metrics["pieces"],
        "actual_weight": metrics["actual_weight"],
        "volumetric_weight": metrics["volumetric_weight"],
        "chargeable_weight": metrics["chargeable_weight"],
        "dimensions_summary": metrics["dimensions_summary"],
        "line_items": line_items,
        "currency": display_currency,
        "sell_total": sell_total,
        "total_cost_pgk": decimal_or_zero(getattr(totals, "total_cost_pgk", None)),
        "total_sell_pgk": decimal_or_zero(getattr(totals, "total_sell_pgk", None)),
        "margin_amount": decimal_or_zero(getattr(totals, "gross_profit", None)),
        "margin_percent": decimal_or_zero(getattr(totals, "margin_percent", None)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        "fx_applied": build_fx_applied_payload(active_version, lines, display_currency),
        "tax_breakdown": build_tax_breakdown_payload(lines, totals, display_currency),
        "warnings": _dedupe(warnings),
        "missing_components": coverage.missing_required,
        "spot_required": spot_required,
        "engine_name": f"{engine_version} Pricing Engine" if engine_version else "Stored Quote",
        "rate_source": line_rate_source,
        "service_notes": (
            getattr(totals, "service_notes", None)
            if totals and getattr(totals, "service_notes", None)
            else (getattr(totals, "notes", None) if totals else None)
        ),
        "customer_notes": getattr(totals, "customer_notes", None) if totals else None,
        "internal_notes": getattr(totals, "internal_notes", None) if totals else None,
        "audit_metadata": getattr(totals, "audit_metadata_json", {}) if totals else {},
        "prepared_by": prepared_by,
        "created_at": getattr(quote, "created_at", None),
        "calculated_at": getattr(active_version, "created_at", None) if active_version else getattr(quote, "created_at", None),
        "quote_version": getattr(active_version, "version_number", None) if active_version else None,
        "payment_term": getattr(quote, "payment_term", None),
        "valid_until": getattr(quote, "valid_until", None),
    }
