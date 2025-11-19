from decimal import Decimal
from unittest.mock import MagicMock, patch

from pricing_v2.dataclasses_v3 import QuoteInput, ShipmentDetails, Piece
from pricing_v2.pricing_service_v3 import PricingServiceV3


def make_service(pieces):
    """Helper to create a lightweight service instance with specific pieces."""
    shipment = MagicMock(spec=ShipmentDetails)
    shipment.pieces = pieces

    quote_input = MagicMock(spec=QuoteInput)
    quote_input.shipment = shipment
    quote_input.output_currency = "PGK"
    quote_input.overrides = []

    service = PricingServiceV3.__new__(PricingServiceV3)
    service.shipment = shipment
    service.quote_input = quote_input

    with patch("pricing_v2.pricing_service_v3.Policy.objects"):
        with patch("pricing_v2.pricing_service_v3.FxSnapshot.objects"):
            return service._build_calculation_context()


def test_chargeable_weight_heavy_dense():
    pieces = [
        Piece(
            pieces=1,
            length_cm=Decimal("50"),
            width_cm=Decimal("40"),
            height_cm=Decimal("30"),
            gross_weight_kg=Decimal("100.0"),
        )
    ]

    context = make_service(pieces)
    assert context["chargeable_weight_kg"] == Decimal("100.00")


def test_chargeable_weight_light_bulky():
    pieces = [
        Piece(
            pieces=1,
            length_cm=Decimal("100"),
            width_cm=Decimal("100"),
            height_cm=Decimal("100"),
            gross_weight_kg=Decimal("10.0"),
        )
    ]

    context = make_service(pieces)
    assert context["chargeable_weight_kg"] == Decimal("166.67")


def test_chargeable_weight_mixed_stack():
    pieces = [
        Piece(pieces=1, length_cm=100, width_cm=120, height_cm=100, gross_weight_kg=10),
        Piece(pieces=1, length_cm=10, width_cm=10, height_cm=10, gross_weight_kg=50),
    ]

    context = make_service(pieces)
    assert context["chargeable_weight_kg"] == Decimal("200.17")


def test_chargeable_weight_multiple_pieces_same_line():
    pieces = [
        Piece(
            pieces=10,
            length_cm=Decimal("60"),
            width_cm=Decimal("50"),
            height_cm=Decimal("20"),
            gross_weight_kg=Decimal("50.0"),
        )
    ]

    context = make_service(pieces)
    assert context["chargeable_weight_kg"] == Decimal("100.00")
