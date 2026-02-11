# backend/quotes/tests/test_completeness.py

from decimal import Decimal
from uuid import uuid4

import pytest

from core.dataclasses import CalculatedChargeLine
from quotes.completeness import (
    COMPONENT_DESTINATION_LOCAL,
    COMPONENT_FREIGHT,
    COMPONENT_ORIGIN_LOCAL,
    evaluate_from_lines,
)


pytestmark = pytest.mark.django_db


def _line(bucket: str, is_rate_missing: bool = False, is_informational: bool = False):
    return CalculatedChargeLine(
        service_component_id=uuid4(),
        service_component_code="TEST",
        service_component_desc="Test Line",
        leg="MAIN",
        cost_pgk=Decimal("0"),
        sell_pgk=Decimal("0"),
        sell_pgk_incl_gst=Decimal("0"),
        sell_fcy=Decimal("0"),
        sell_fcy_incl_gst=Decimal("0"),
        cost_source="TEST",
        bucket=bucket,
        is_rate_missing=is_rate_missing,
        is_informational=is_informational,
    )


def test_export_d2d_missing_destination_local():
    lines = [
        _line("origin_charges"),
        _line("airfreight"),
    ]
    result = evaluate_from_lines(lines, "EXPORT", "D2D")
    assert result.is_complete is False
    assert result.is_spot_required is True
    assert COMPONENT_DESTINATION_LOCAL in result.missing_required


def test_export_a2a_optional_missing_ok():
    lines = [_line("airfreight")]
    result = evaluate_from_lines(lines, "EXPORT", "A2A")
    assert result.is_complete is True
    assert result.is_spot_required is False


def test_zero_amount_line_counts_as_covered():
    lines = [
        _line("origin_charges"),
        _line("airfreight"),
    ]
    result = evaluate_from_lines(lines, "IMPORT", "D2A")
    assert result.is_complete is True
    assert result.is_spot_required is False


def test_import_d2d_missing_lines_flags_incomplete():
    result = evaluate_from_lines([], "IMPORT", "D2D")
    assert result.is_complete is False
    assert set(result.missing_required) == {
        COMPONENT_ORIGIN_LOCAL,
        COMPONENT_FREIGHT,
        COMPONENT_DESTINATION_LOCAL,
    }


def test_domestic_missing_lines_flags_incomplete():
    result = evaluate_from_lines([], "DOMESTIC", "A2A")
    assert result.is_complete is False
    assert result.missing_required == [COMPONENT_FREIGHT]
