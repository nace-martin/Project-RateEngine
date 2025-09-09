from decimal import Decimal

from django.test import TestCase

from .engine import Piece, calculate_chargeable_weight_per_piece, ZERO


class ChargeableWeightTests(TestCase):
    def test_per_piece_chargeable_and_whole_kg_rounding(self):
        # dim factor typical for air freight using m3 -> kg
        dim_factor = Decimal("167")

        # Piece A: actual 10.0 kg, dims give volumetric 10.02 kg -> use 10.02
        a = Piece(weight_kg=Decimal("10.0"), length_cm=Decimal("50"), width_cm=Decimal("40"), height_cm=Decimal("30"))

        # Piece B: actual 5.0 kg, dims give volumetric 16.032 kg -> use 16.032
        b = Piece(weight_kg=Decimal("5.0"), length_cm=Decimal("60"), width_cm=Decimal("40"), height_cm=Decimal("40"))

        total = calculate_chargeable_weight_per_piece([a, b], dim_factor)

        # Sum before rounding = 10.02 + 16.032 = 26.052
        # Rounded up to next whole kg => 27
        self.assertEqual(total, Decimal("27"))

    def test_empty_and_missing_dimensions(self):
        dim_factor = Decimal("167")

        # Empty pieces -> ZERO
        self.assertEqual(calculate_chargeable_weight_per_piece([], dim_factor), ZERO)

        # Missing dimensions -> volumetric 0, so use actual
        p = Piece(weight_kg=Decimal("10"))
        self.assertEqual(calculate_chargeable_weight_per_piece([p], dim_factor), Decimal("10"))

    def test_exact_integer_total_not_rounded_up(self):
        dim_factor = Decimal("167")
        p1 = Piece(weight_kg=Decimal("12"))
        p2 = Piece(weight_kg=Decimal("8"))
        total = calculate_chargeable_weight_per_piece([p1, p2], dim_factor)
        self.assertEqual(total, Decimal("20"))

    def test_slightly_above_integer_rounds_up(self):
        dim_factor = Decimal("167")
        p1 = Piece(weight_kg=Decimal("12"))
        p2 = Piece(weight_kg=Decimal("8"))
        p3 = Piece(weight_kg=Decimal("0.001"))
        total = calculate_chargeable_weight_per_piece([p1, p2, p3], dim_factor)
        self.assertEqual(total, Decimal("21"))
