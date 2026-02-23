from decimal import Decimal

from core.charge_rules import evaluate_charge_rule


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
