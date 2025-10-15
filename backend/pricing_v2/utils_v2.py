import math
from decimal import Decimal
from typing import List, Dict, Any

# Standard IATA volumetric factor (cubic meters to kg)
VOLUMETRIC_FACTOR = Decimal('167')
# Alternative factor for dimensions in cm (L*W*H / 6000)
# 1,000,000 cm^3/m^3 / 6000 = 166.666...
# We will use the 6000 divisor for direct cm calculation.
VOLUMETRIC_DIVISOR_CM = Decimal('6000')

def calculate_chargeable_weight(pieces: List[Dict[str, Any]]) -> Decimal:
    """
    Calculates the chargeable weight for a shipment based on its pieces.

    The chargeable weight is the greater of the total actual weight and the
    total volumetric weight.

    Args:
        pieces: A list of dictionaries, where each dictionary represents a piece
                and must contain 'weight_kg', 'length_cm', 'width_cm',
                and 'height_cm'.

    Returns:
        The calculated chargeable weight, rounded up to the nearest whole number.
    """
    if not pieces:
        return Decimal('0')

    total_actual_weight = Decimal('0')
    total_volumetric_weight = Decimal('0')

    for piece in pieces:
        # Ensure all required keys are present, defaulting to 0 if not
        actual_weight = Decimal(piece.get('weight_kg', 0))
        length = Decimal(piece.get('length_cm', 0))
        width = Decimal(piece.get('width_cm', 0))
        height = Decimal(piece.get('height_cm', 0))

        # Accumulate total actual weight
        total_actual_weight += actual_weight

        # Calculate volumetric weight for the piece and accumulate
        # Formula: (L x W x H in cm) / 6000
        piece_volume = length * width * height
        piece_volumetric_weight = piece_volume / VOLUMETRIC_DIVISOR_CM
        total_volumetric_weight += piece_volumetric_weight

    # The chargeable weight is the greater of the two totals
    chargeable_weight = max(total_actual_weight, total_volumetric_weight)

    # Per freight rules, always round up to the nearest whole kilogram
    return Decimal(math.ceil(chargeable_weight))