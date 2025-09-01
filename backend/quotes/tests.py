from django.test import TestCase

from rate_engine.engine import calculate_chargeable_weight


class CalculateChargeableWeightTests(TestCase):
    def test_single_piece_volumetric_greater(self):
        # Volumetric = (60*50*40)/6000 = 20 kg, actual = 12 kg -> pick 20
        pieces = [{"weight": 12, "length": 60, "width": 50, "height": 40}]
        self.assertAlmostEqual(calculate_chargeable_weight(pieces), 20.0, places=3)

    def test_single_piece_actual_greater(self):
        # Volumetric = (30*30*30)/6000 = 4.5 kg, actual = 10 kg -> pick 10
        pieces = [{"weight": 10, "length": 30, "width": 30, "height": 30}]
        self.assertAlmostEqual(calculate_chargeable_weight(pieces), 10.0, places=3)

    def test_multiple_pieces_mixed(self):
        # Piece1: vol 20 vs act 12 -> 20
        # Piece2: vol 4.5 vs act 10 -> 10
        # Total = 30
        pieces = [
            {"weight": 12, "length": 60, "width": 50, "height": 40},
            {"weight": 10, "length": 30, "width": 30, "height": 30},
        ]
        self.assertAlmostEqual(calculate_chargeable_weight(pieces), 30.0, places=3)

    def test_missing_dimensions_defaults_to_actual(self):
        # Missing dims -> volumetric 0 -> pick actual only
        pieces = [
            {"weight": 7.2},
            {"weight": 3.3, "length": None, "width": 50, "height": 40},
        ]
        self.assertAlmostEqual(calculate_chargeable_weight(pieces), 10.5, places=3)

    def test_string_inputs_are_handled(self):
        # Values can be strings; ensure parsing works
        pieces = [
            {"weight": "12", "length": "60", "width": "50", "height": "40"},  # 20
            {"weight": "1.5", "length": "10", "width": "10", "height": "10"},  # vol 1.666.. -> 1.666..
        ]
        expected = 20.0 + ((10*10*10)/6000)
        self.assertAlmostEqual(calculate_chargeable_weight(pieces), expected, places=3)
