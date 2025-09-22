import pytest
from unittest.mock import patch, MagicMock
from pricing_v2.dataclasses_v2 import QuoteContext, Piece
from pricing_v2.pricing_service_v2 import compute_quote_v2

@pytest.mark.django_db
@patch('backend.pricing_v2.pricing_service_v2.FxConverter')
@patch('backend.pricing_v2.pricing_service_v2.M')
def test_air_a2d_prepaid(MockM, MockFxConverter):
    # Mock the database models
    MockM.Lanes.objects.filter.return_value.exists.return_value = True
    mock_lane = MagicMock()
    mock_lane.ratecard.currency = 'AUD'
    MockM.Lanes.objects.filter.return_value = [mock_lane]
    mock_break = MagicMock()
    mock_break.per_kg = 10.0
    mock_break.min_amount = 100.0
    MockM.LaneBreaks.objects.filter.return_value = [mock_break]

    # Mock FxConverter
    mock_fx_converter = MagicMock()
    mock_fx_converter.convert.return_value = 1.0
    MockFxConverter.return_value = mock_fx_converter

    # Create a quote context
    ctx = QuoteContext(
        mode="AIR",
        scope="A2D",
        payment_term="PREPAID",
        origin_iata="BNE",
        dest_iata="POM",
        pieces=[Piece(weight_kg=81)],
        audience="PNG_CUSTOMER_PREPAID",
        invoice_ccy="PGK",
        margins={"FREIGHT": 10},
        policy={},
    )

    # Compute the quote
    result = compute_quote_v2(ctx)

    # Assertions
    assert not result['manual']
    assert len(result['sell_lines']) > 0

    freight_sell_line = next((line for line in result['sell_lines'] if line['sell_code'] == 'FREIGHT'), None)
    assert freight_sell_line is not None
    # assert freight_sell_line['amount'] == (81 * 10.0) * 1.10  # 10% margin

    assert result['totals']['client_ccy'] == 'PGK'
