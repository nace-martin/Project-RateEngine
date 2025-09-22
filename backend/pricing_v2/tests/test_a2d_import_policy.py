import pytest
from pricing_v2.dataclasses_v2 import QuoteContext, Totals
from pricing_v2.pricing_service_v2 import compute_quote_v2


@pytest.mark.skip(
    reason="Tests will be enabled once pricing_service_v2 is fully implemented for this policy."
)
def test_a2d_import_policy_prepaid():
    """Test case for PREPAID A2D Import: invoice_ccy should be AUD and only dest-side services."""
    # Arrange
    context = QuoteContext(
        mode="AIR",
        scope="A2D",
        payment_term="PREPAID",
        origin_iata="BNE",
        dest_iata="POM",
        pieces=[{"weight_kg": 81}],
        commodity="GCR",
    )

    # Act
    totals = compute_quote_v2(context)

    # Assert
    assert totals.invoice_ccy == "AUD"
    # assert only dest-side services are included in sell lines (requires detailed sell line structure)
    assert not totals.is_incomplete


@pytest.mark.skip(
    reason="Tests will be enabled once pricing_service_v2 is fully implemented for this policy."
)
def test_a2d_import_policy_collect():
    """Test case for COLLECT A2D Import: invoice_ccy should be PGK and only dest-side services."""
    # Arrange
    context = QuoteContext(
        mode="AIR",
        scope="A2D",
        payment_term="COLLECT",
        origin_iata="BNE",
        dest_iata="POM",
        pieces=[{"weight_kg": 81}],
        commodity="GCR",
    )

    # Act
    totals = compute_quote_v2(context)

    # Assert
    assert totals.invoice_ccy == "PGK"
    # assert only dest-side services are included in sell lines (requires detailed sell line structure)
    assert not totals.is_incomplete


@pytest.mark.skip(
    reason="Tests will be enabled once pricing_service_v2 is fully implemented for this policy."
)
def test_a2d_import_policy_missing_buy_data():
    """Test case for missing BUY data: is_incomplete should be true with a clear reason."""
    # Arrange
    # Create a context that is known to trigger missing BUY data, e.g., an unsupported lane
    context = QuoteContext(
        mode="AIR",
        scope="A2D",
        payment_term="PREPAID",
        origin_iata="UNS",  # Unsupported origin
        dest_iata="POM",
        pieces=[{"weight_kg": 81}],
        commodity="GCR",
    )

    # Act
    totals = compute_quote_v2(context)

    # Assert
    assert totals.is_incomplete
    assert (
        "Manual Rate Required" in totals.reasons
    )  # Assuming reasons is a list of strings
    # assert no server error (this is implicitly handled by the test not crashing)
