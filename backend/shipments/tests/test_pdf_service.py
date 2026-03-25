from decimal import Decimal
from types import SimpleNamespace

from shipments.pdf_service import _piece_actual_weight


def test_piece_actual_weight_multiplies_quantity():
    piece = SimpleNamespace(piece_count=2, gross_weight_kg=Decimal("12.00"))

    assert _piece_actual_weight(piece) == Decimal("24.00")
