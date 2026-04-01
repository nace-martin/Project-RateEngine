from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Mapping, Optional


CALCULATION_FLAT = "FLAT"
CALCULATION_PER_UNIT = "PER_UNIT"
CALCULATION_MIN_OR_PER_UNIT = "MIN_OR_PER_UNIT"
CALCULATION_MAX_OR_PER_UNIT = "MAX_OR_PER_UNIT"
CALCULATION_TIERED_BREAK = "TIERED_BREAK"
CALCULATION_PERCENT_OF_BASE = "PERCENT_OF_BASE"
CALCULATION_PERCENT_OF = CALCULATION_PERCENT_OF_BASE
CALCULATION_LOOKUP_RATE = "LOOKUP_RATE"
CALCULATION_MANUAL_OVERRIDE = "MANUAL_OVERRIDE"
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


STANDARD_RULE_FAMILIES = (
    CALCULATION_FLAT,
    CALCULATION_PER_UNIT,
    CALCULATION_MIN_OR_PER_UNIT,
    CALCULATION_TIERED_BREAK,
    CALCULATION_PERCENT_OF_BASE,
    CALCULATION_LOOKUP_RATE,
    CALCULATION_MANUAL_OVERRIDE,
)


@dataclass(frozen=True)
class RuleEvaluation:
    rule_family: str
    amount: Decimal


def quantize_money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _apply_limits(amount: Decimal, *, min_amount: Optional[Decimal] = None, max_amount: Optional[Decimal] = None) -> Decimal:
    if min_amount is not None:
        amount = max(min_amount, amount)
    if max_amount is not None:
        amount = min(max_amount, amount)
    return amount


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
            calc_type = CALCULATION_PERCENT_OF_BASE
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
        amount = evaluate_flat_rule(rate, min_amount=min_amount, max_amount=max_amount).amount
    elif calc_type == CALCULATION_PER_UNIT:
        amount = evaluate_per_unit_rule(rate, quantity, min_amount=min_amount, max_amount=max_amount).amount
    elif calc_type == CALCULATION_MIN_OR_PER_UNIT:
        amount = evaluate_min_or_per_unit_rule(rate, quantity, min_amount=min_amount, max_amount=max_amount).amount
    elif calc_type == CALCULATION_MAX_OR_PER_UNIT:
        per_unit_amount = rate * quantity
        floor = max_amount if max_amount is not None else Decimal("0")
        amount = max(floor, per_unit_amount)
    elif calc_type == CALCULATION_PERCENT_OF_BASE:
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
        amount = evaluate_percent_of_base_rule(
            percent or Decimal("0"),
            basis_amount,
            min_amount=min_amount,
            max_amount=max_amount,
        ).amount
    elif calc_type == CALCULATION_PER_LINE_WITH_CAP:
        line_count = _unit_quantity(UNIT_LINE, shipment_context)
        included = _to_decimal(rule_meta.get("max_lines_included"), Decimal("0")) or Decimal("0")
        extra_line_rate = _to_decimal(rule_meta.get("extra_line_rate"), Decimal("0")) or Decimal("0")
        extra_lines = max(line_count - included, Decimal("0"))
        amount = rate + (extra_line_rate * extra_lines)
    elif calc_type == CALCULATION_LOOKUP_RATE:
        amount = evaluate_lookup_rate_rule(rate, min_amount=min_amount, max_amount=max_amount).amount
    elif calc_type == CALCULATION_MANUAL_OVERRIDE:
        amount = evaluate_manual_override_rule(rate).amount
    else:
        amount = rate

    if min_amount is not None and calc_type not in {CALCULATION_MIN_OR_PER_UNIT}:
        amount = max(min_amount, amount)
    if max_amount is not None and calc_type not in {CALCULATION_MAX_OR_PER_UNIT}:
        amount = min(max_amount, amount)

    return amount


def evaluate_flat_rule(
    amount: Decimal,
    *,
    min_amount: Optional[Decimal] = None,
    max_amount: Optional[Decimal] = None,
) -> RuleEvaluation:
    return RuleEvaluation(
        rule_family=CALCULATION_FLAT,
        amount=quantize_money(_apply_limits(amount, min_amount=min_amount, max_amount=max_amount)),
    )


def evaluate_lookup_rate_rule(
    amount: Decimal,
    *,
    min_amount: Optional[Decimal] = None,
    max_amount: Optional[Decimal] = None,
) -> RuleEvaluation:
    return RuleEvaluation(
        rule_family=CALCULATION_LOOKUP_RATE,
        amount=quantize_money(_apply_limits(amount, min_amount=min_amount, max_amount=max_amount)),
    )


def evaluate_per_unit_rule(
    rate: Decimal,
    quantity: Decimal,
    *,
    min_amount: Optional[Decimal] = None,
    max_amount: Optional[Decimal] = None,
) -> RuleEvaluation:
    amount = rate * quantity
    return RuleEvaluation(
        rule_family=CALCULATION_PER_UNIT,
        amount=quantize_money(_apply_limits(amount, min_amount=min_amount, max_amount=max_amount)),
    )


def evaluate_min_or_per_unit_rule(
    rate: Decimal,
    quantity: Decimal,
    *,
    min_amount: Optional[Decimal] = None,
    max_amount: Optional[Decimal] = None,
) -> RuleEvaluation:
    per_unit_amount = rate * quantity
    floor = min_amount if min_amount is not None else Decimal("0")
    amount = max(floor, per_unit_amount)
    return RuleEvaluation(
        rule_family=CALCULATION_MIN_OR_PER_UNIT,
        amount=quantize_money(_apply_limits(amount, max_amount=max_amount)),
    )


def evaluate_tiered_break_rule(
    breaks: list[dict[str, Any]],
    quantity: Decimal,
    *,
    min_key: str = "min_kg",
    rate_key: str = "rate",
    min_amount: Optional[Decimal] = None,
    max_amount: Optional[Decimal] = None,
) -> RuleEvaluation:
    if not breaks:
        amount = Decimal("0")
    else:
        sorted_breaks = sorted(
            breaks,
            key=lambda item: _to_decimal(item.get(min_key), Decimal("0")) or Decimal("0"),
            reverse=True,
        )
        selected_rate = _to_decimal(sorted_breaks[-1].get(rate_key), Decimal("0")) or Decimal("0")
        for tier in sorted_breaks:
            tier_min = _to_decimal(tier.get(min_key), Decimal("0")) or Decimal("0")
            if quantity >= tier_min:
                selected_rate = _to_decimal(tier.get(rate_key), Decimal("0")) or Decimal("0")
                break
        amount = selected_rate * quantity

    return RuleEvaluation(
        rule_family=CALCULATION_TIERED_BREAK,
        amount=quantize_money(_apply_limits(amount, min_amount=min_amount, max_amount=max_amount)),
    )


def evaluate_percent_of_base_rule(
    percent: Decimal,
    base_amount: Decimal,
    *,
    min_amount: Optional[Decimal] = None,
    max_amount: Optional[Decimal] = None,
) -> RuleEvaluation:
    amount = base_amount * (percent / Decimal("100"))
    return RuleEvaluation(
        rule_family=CALCULATION_PERCENT_OF_BASE,
        amount=quantize_money(_apply_limits(amount, min_amount=min_amount, max_amount=max_amount)),
    )


def evaluate_manual_override_rule(
    amount: Decimal,
    *,
    min_amount: Optional[Decimal] = None,
    max_amount: Optional[Decimal] = None,
) -> RuleEvaluation:
    return RuleEvaluation(
        rule_family=CALCULATION_MANUAL_OVERRIDE,
        amount=quantize_money(_apply_limits(amount, min_amount=min_amount, max_amount=max_amount)),
    )


def evaluate_rate_lookup_rule(
    *,
    rate: Any,
    quantity: Decimal,
    base_amount: Optional[Decimal] = None,
) -> RuleEvaluation:
    rate_type = str(getattr(rate, "rate_type", "") or "").upper()
    percent_rate = _to_decimal(getattr(rate, "percent_rate", None))
    raw_amount = _to_decimal(getattr(rate, "amount", None))
    weight_breaks = getattr(rate, "weight_breaks", None)
    rate_per_kg = _to_decimal(getattr(rate, "rate_per_kg", None))
    rate_per_shipment = _to_decimal(getattr(rate, "rate_per_shipment", None))
    min_charge = _to_decimal(getattr(rate, "min_charge", None))
    max_charge = _to_decimal(getattr(rate, "max_charge", None))

    if percent_rate is None and rate_type == "PERCENT":
        percent_rate = raw_amount
    if rate_per_kg is None and rate_type == "PER_KG":
        rate_per_kg = raw_amount
    if rate_per_shipment is None and rate_type == "FLAT":
        rate_per_shipment = raw_amount

    if percent_rate is not None and base_amount is not None:
        return evaluate_percent_of_base_rule(
            percent_rate,
            base_amount,
            min_amount=min_charge,
            max_amount=max_charge,
        )

    if weight_breaks:
        return evaluate_tiered_break_rule(
            weight_breaks,
            quantity,
            min_amount=min_charge,
            max_amount=max_charge,
        )

    if getattr(rate, "is_additive", False) and rate_per_kg is not None and rate_per_shipment is not None:
        additive_amount = (rate_per_kg * quantity) + rate_per_shipment
        return evaluate_lookup_rate_rule(
            additive_amount,
            min_amount=min_charge,
            max_amount=max_charge,
        )

    if rate_type == "FIXED" and raw_amount is not None:
        return evaluate_lookup_rate_rule(
            raw_amount,
            min_amount=min_charge,
            max_amount=max_charge,
        )

    if rate_per_kg is not None:
        if min_charge is not None:
            return evaluate_min_or_per_unit_rule(
                rate_per_kg,
                quantity,
                min_amount=min_charge,
                max_amount=max_charge,
            )
        return evaluate_per_unit_rule(
            rate_per_kg,
            quantity,
            max_amount=max_charge,
        )

    if rate_per_shipment is not None:
        return evaluate_flat_rule(
            rate_per_shipment,
            min_amount=min_charge,
            max_amount=max_charge,
        )

    amount = raw_amount or Decimal("0")
    if rate_type == "FIXED" or hasattr(rate, "amount"):
        return evaluate_lookup_rate_rule(
            amount,
            min_amount=min_charge,
            max_amount=max_charge,
        )

    return evaluate_lookup_rate_rule(
        amount,
        min_amount=min_charge,
        max_amount=max_charge,
    )
