import pytest
from decimal import Decimal
from pricing_v2.utils_v2 import calculate_chargeable_weight

class TestCalculateChargeableWeight:
    """
    Unit tests for the chargeable weight calculation utility.
    """

    def test_actual_weight_is_greater(self):
        """
        Tests the scenario where the total actual weight is greater than
        the total volumetric weight.
        """
        pieces = [{
            'weight_kg': 25,
            'length_cm': 50,
            'width_cm': 40,
            'height_cm': 30
        }]
        # Volumetric weight = (50*40*30)/6000 = 10kg
        # Actual weight = 25kg. Chargeable should be 25kg.
        assert calculate_chargeable_weight(pieces) == Decimal('25')

    def test_volumetric_weight_is_greater(self):
        """
        Tests the scenario where the total volumetric weight is greater than
        the total actual weight.
        """
        pieces = [{
            'weight_kg': 10,
            'length_cm': 80,
            'width_cm': 50,
            'height_cm': 40
        }]
        # Volumetric weight = (80*50*40)/6000 = 26.66... kg -> rounded up to 27kg
        # Actual weight = 10kg. Chargeable should be 27kg.
        assert calculate_chargeable_weight(pieces) == Decimal('27')

    def test_multiple_pieces_combined(self):
        """
        Tests that weights and volumes from multiple pieces are correctly
        summed before the final comparison.
        """
        pieces = [
            {'weight_kg': 10, 'length_cm': 50, 'width_cm': 40, 'height_cm': 30}, # Volumetric: 10kg
            {'weight_kg': 12, 'length_cm': 60, 'width_cm': 50, 'height_cm': 20}  # Volumetric: 10kg
        ]
        # Total actual weight = 10 + 12 = 22kg
        # Total volumetric weight = 10 + 10 = 20kg
        # Chargeable should be the greater of the two: 22kg.
        assert calculate_chargeable_weight(pieces) == Decimal('22')

    def test_rounding_up(self):
        """
        Tests that the final chargeable weight is always rounded up to the
        nearest whole number.
        """
        pieces = [{
            'weight_kg': 5,
            'length_cm': 40,
            'width_cm': 30,
            'height_cm': 25
        }]
        # Volumetric weight = (40*30*25)/6000 = 5.0 kg
        # Let's try a value that needs rounding: 40.1 * 30 * 25 / 6000 = 5.0125
        pieces[0]['length_cm'] = Decimal('40.1')
        # Chargeable should be 5.0125, which rounds up to 6.
        assert calculate_chargeable_weight(pieces) == Decimal('6')

    def test_empty_pieces_list(self):
        """
        Tests that an empty list of pieces results in a chargeable weight of 0.
        """
        assert calculate_chargeable_weight([]) == Decimal('0')

    def test_missing_keys_in_piece_data(self):
        """
        Tests that missing keys in the piece dictionary are handled gracefully
        and treated as zero.
        """
        pieces = [{'weight_kg': 15}] # Missing dimension keys
        # Volumetric weight will be 0. Chargeable weight will be 15.
        assert calculate_chargeable_weight(pieces) == Decimal('15')