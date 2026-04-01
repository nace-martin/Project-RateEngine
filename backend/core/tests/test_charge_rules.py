from decimal import Decimal

from core.charge_rules import (
    CALCULATION_FLAT,
    CALCULATION_LOOKUP_RATE,
    CALCULATION_MANUAL_OVERRIDE,
    CALCULATION_MIN_OR_PER_UNIT,
    CALCULATION_PERCENT_OF_BASE,
    CALCULATION_PER_UNIT,
    CALCULATION_TIERED_BREAK,
    evaluate_charge_rule,
    evaluate_flat_rule,
    evaluate_lookup_rate_rule,
    evaluate_manual_override_rule,
    evaluate_min_or_per_unit_rule,
    evaluate_percent_of_base_rule,
    evaluate_per_unit_rule,
    evaluate_tiered_break_rule,
)


def test_min_or_per_unit_uses_minimum_when_quantity_is_low():
    amount = evaluate_charge_rule(
        {
            "calculation_type": "MIN_OR_PER_UNIT",
            "unit_type": "KG",
            "rate": Decimal("0.25"),
            "min_amount": Decimal("35.00"),
        },
        {"chargeable_weight_kg": Decimal("100")},
    )
    assert amount == Decimal("35.00")


def test_min_or_per_unit_uses_unit_rate_when_quantity_is_high():
    amount = evaluate_charge_rule(
        {
            "calculation_type": "MIN_OR_PER_UNIT",
            "unit_type": "KG",
            "rate": Decimal("0.25"),
            "min_amount": Decimal("35.00"),
        },
        {"chargeable_weight_kg": Decimal("200")},
    )
    assert amount == Decimal("50.00")


def test_min_or_per_unit_supports_non_weight_unit():
    amount = evaluate_charge_rule(
        {
            "calculation_type": "MIN_OR_PER_UNIT",
            "unit_type": "TRIP",
            "rate": Decimal("25.00"),
            "min_amount": Decimal("80.00"),
        },
        {"trip_count": Decimal("2")},
    )
    assert amount == Decimal("80.00")


def test_flat_rule_evaluation():
    evaluation = evaluate_flat_rule(Decimal("25.00"))
    assert evaluation.rule_family == CALCULATION_FLAT
    assert evaluation.amount == Decimal("25.00")


def test_per_unit_rule_evaluation():
    evaluation = evaluate_per_unit_rule(Decimal("2.50"), Decimal("8"))
    assert evaluation.rule_family == CALCULATION_PER_UNIT
    assert evaluation.amount == Decimal("20.00")


def test_tiered_break_rule_evaluation():
    evaluation = evaluate_tiered_break_rule(
        [
            {"min_kg": 0, "rate": "8.00"},
            {"min_kg": 50, "rate": "7.50"},
            {"min_kg": 100, "rate": "7.00"},
        ],
        Decimal("75"),
    )
    assert evaluation.rule_family == CALCULATION_TIERED_BREAK
    assert evaluation.amount == Decimal("562.50")


def test_percent_of_base_rule_evaluation():
    evaluation = evaluate_percent_of_base_rule(Decimal("12.50"), Decimal("400.00"))
    assert evaluation.rule_family == CALCULATION_PERCENT_OF_BASE
    assert evaluation.amount == Decimal("50.00")


def test_lookup_rate_rule_evaluation():
    evaluation = evaluate_lookup_rate_rule(Decimal("135.00"))
    assert evaluation.rule_family == CALCULATION_LOOKUP_RATE
    assert evaluation.amount == Decimal("135.00")


def test_manual_override_rule_evaluation():
    evaluation = evaluate_manual_override_rule(Decimal("99.99"))
    assert evaluation.rule_family == CALCULATION_MANUAL_OVERRIDE
    assert evaluation.amount == Decimal("99.99")


def test_evaluate_charge_rule_aliases_percent_of_base():
    amount = evaluate_charge_rule(
        {
            "calculation_type": "PERCENT_OF_BASE",
            "percent": Decimal("10.00"),
            "percent_basis": "freight",
        },
        {"basis_amounts": {"freight": Decimal("500.00")}},
    )
    assert amount == Decimal("50.00")
