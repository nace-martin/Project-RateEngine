from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Optional


CALCULATION_FLAT = "FLAT"
CALCULATION_PER_UNIT = "PER_UNIT"
CALCULATION_MIN_OR_PER_UNIT = "MIN_OR_PER_UNIT"
CALCULATION_MAX_OR_PER_UNIT = "MAX_OR_PER_UNIT"
CALCULATION_PERCENT_OF = "PERCENT_OF"
CALCULATION_PER_LINE_WITH_CAP = "PER_LINE_WITH_CAP"

UNIT_KG = "KG"
UNIT_SHIPMENT = "SHIPMENT"
UNIT_AWB = "AWB"
UNIT_TRIP = "TRIP"
UNIT_SET = "SET"
UNIT_LINE = "LINE"
UNIT_MAN = "MAN"
UNIT_CBM = "CBM"
UNIT_RT = "RT"


LEGACY_UNIT_TO_UNIT_TYPE = {
    "per_kg": UNIT_KG,
    "per_shipment": UNIT_SHIPMENT,
    "flat": UNIT_SHIPMENT,
    "per_awb": UNIT_AWB,
    "per_trip": UNIT_TRIP,
    "per_set": UNIT_SET,
    "per_man": UNIT_MAN,
    "percentage": UNIT_LINE,
}


def _to_decimal(value: Any, default: Optional[Decimal] = None) -> Optional[Decimal]:
    if value is None or value == "":
        return default
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return default


def _unit_quantity(unit_type: str, shipment_context: Mapping[str, Any]) -> Decimal:
    key_map = {
        UNIT_KG: "chargeable_weight_kg",
        UNIT_SHIPMENT: "shipment_count",
        UNIT_AWB: "awb_count",
        UNIT_TRIP: "trip_count",
        UNIT_SET: "set_count",
        UNIT_LINE: "line_count",
        UNIT_MAN: "man_count",
        UNIT_CBM: "cbm",
        UNIT_RT: "rt",
    }
    raw = shipment_context.get(key_map.get(unit_type, ""), None)
    if raw is None and unit_type == UNIT_SHIPMENT:
        raw = 1
    if raw is None and unit_type == UNIT_AWB:
        raw = 1
    return _to_decimal(raw, Decimal("0")) or Decimal("0")


def normalize_charge_rule(charge_rule: Mapping[str, Any]) -> dict[str, Any]:
    """
    Normalize both legacy and new-style rule payloads into one canonical shape.
    """
    raw_calc_type = str(charge_rule.get("calculation_type") or "").strip()
    calc_type = raw_calc_type.upper() if raw_calc_type else ""

    raw_unit_type = str(charge_rule.get("unit_type") or "").strip()
    unit_type = raw_unit_type.upper() if raw_unit_type else ""

    legacy_unit = str(charge_rule.get("unit") or "").strip().lower()
    if not unit_type and legacy_unit:
        unit_type = LEGACY_UNIT_TO_UNIT_TYPE.get(legacy_unit, UNIT_SHIPMENT)

    rate = _to_decimal(charge_rule.get("rate"))
    if rate is None:
        rate = _to_decimal(charge_rule.get("amount"), Decimal("0"))

    min_amount = _to_decimal(charge_rule.get("min_amount"))
    if min_amount is None:
        min_amount = _to_decimal(charge_rule.get("min_charge"))

    max_amount = _to_decimal(charge_rule.get("max_amount"))
    percent = _to_decimal(charge_rule.get("percent"))
    if percent is None and legacy_unit == "percentage":
        percent = _to_decimal(charge_rule.get("amount"), Decimal("0"))
    percent_basis = charge_rule.get("percent_basis") or charge_rule.get("percentage_basis")
    rule_meta = charge_rule.get("rule_meta") or {}

    if not calc_type:
        if legacy_unit == "percentage":
            calc_type = CALCULATION_PERCENT_OF
        elif min_amount is not None and legacy_unit.startswith("per_"):
            calc_type = CALCULATION_MIN_OR_PER_UNIT
        elif legacy_unit == "flat":
            calc_type = CALCULATION_FLAT
        elif legacy_unit.startswith("per_"):
            calc_type = CALCULATION_PER_UNIT
        else:
            calc_type = CALCULATION_FLAT

    if not unit_type:
        unit_type = UNIT_SHIPMENT if calc_type == CALCULATION_FLAT else UNIT_KG

    return {
        "calculation_type": calc_type,
        "unit_type": unit_type,
        "rate": rate or Decimal("0"),
        "min_amount": min_amount,
        "max_amount": max_amount,
        "percent": percent,
        "percent_basis": percent_basis,
        "rule_meta": rule_meta if isinstance(rule_meta, dict) else {},
    }


def evaluate_charge_rule(charge_rule: Mapping[str, Any], shipment_context: Mapping[str, Any]) -> Decimal:
    """
    Canonical evaluator for composite charge rules.
    """
    rule = normalize_charge_rule(charge_rule)
    calc_type = rule["calculation_type"]
    unit_type = rule["unit_type"]
    rate = rule["rate"] or Decimal("0")
    min_amount = rule["min_amount"]
    max_amount = rule["max_amount"]
    percent = rule["percent"]
    percent_basis = rule["percent_basis"]
    rule_meta = rule["rule_meta"]

    quantity = _unit_quantity(unit_type, shipment_context)
    amount = Decimal("0")

    if calc_type == CALCULATION_FLAT:
        amount = rate
    elif calc_type == CALCULATION_PER_UNIT:
        amount = rate * quantity
    elif calc_type == CALCULATION_MIN_OR_PER_UNIT:
        per_unit_amount = rate * quantity
        floor = min_amount if min_amount is not None else Decimal("0")
        amount = max(floor, per_unit_amount)
    elif calc_type == CALCULATION_MAX_OR_PER_UNIT:
        per_unit_amount = rate * quantity
        floor = max_amount if max_amount is not None else Decimal("0")
        amount = max(floor, per_unit_amount)
    elif calc_type == CALCULATION_PERCENT_OF:
        basis_amounts = shipment_context.get("basis_amounts", {}) or {}
        basis_amount = Decimal("0")
        if isinstance(basis_amounts, Mapping) and percent_basis:
            basis_amount = _to_decimal(
                basis_amounts.get(percent_basis)
                or basis_amounts.get(str(percent_basis).upper())
                or basis_amounts.get(str(percent_basis).lower()),
                Decimal("0"),
            ) or Decimal("0")
        if basis_amount == Decimal("0") and percent_basis:
            basis_amount = _to_decimal(shipment_context.get(f"{str(percent_basis).lower()}_amount"), Decimal("0")) or Decimal("0")
        pct = (percent or Decimal("0")) / Decimal("100")
        amount = basis_amount * pct
    elif calc_type == CALCULATION_PER_LINE_WITH_CAP:
        line_count = _unit_quantity(UNIT_LINE, shipment_context)
        included = _to_decimal(rule_meta.get("max_lines_included"), Decimal("0")) or Decimal("0")
        extra_line_rate = _to_decimal(rule_meta.get("extra_line_rate"), Decimal("0")) or Decimal("0")
        extra_lines = max(line_count - included, Decimal("0"))
        amount = rate + (extra_line_rate * extra_lines)
    else:
        amount = rate

    if min_amount is not None and calc_type not in {CALCULATION_MIN_OR_PER_UNIT}:
        amount = max(min_amount, amount)
    if max_amount is not None and calc_type not in {CALCULATION_MAX_OR_PER_UNIT}:
        amount = min(max_amount, amount)

    return amount
