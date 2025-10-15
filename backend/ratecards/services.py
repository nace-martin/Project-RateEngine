# backend/ratecards/services.py

from decimal import Decimal
from .models import RateCard, RateCardBreak

class RateCardService:
    """
    A service to find the correct rate from a rate card based on weight.
    """
    def get_air_freight_rate(self, chargeable_kg: Decimal, origin_code: str, dest_code: str) -> dict:
        """
        Finds the applicable air freight rate for a given weight and lane.
        
        Returns a dictionary with 'rate_per_kg', 'minimum_charge', and 'rate_break_id'.
        """
        # A simple implementation assuming city codes for now.
        # This could be expanded to use country, etc.
        try:
            rate_card = RateCard.objects.get(
                origin_city_code=origin_code,
                destination_city_code=dest_code,
                is_active=True
            )
        except RateCard.DoesNotExist:
            raise ValueError(f"No active rate card found for lane {origin_code}-{dest_code}")

        # Find the correct weight break. We want the highest band that is LESS than or equal to the chargeable weight.
        rate_break = RateCardBreak.objects.filter(
            rate_card=rate_card,
            weight_break_kg__lte=chargeable_kg
        ).order_by('-weight_break_kg').first()

        if not rate_break:
            # If no specific break is found, we could fall back to a general/minimum rate
            # For now, we'll assume a break always exists.
            raise ValueError(f"No applicable weight break found for {chargeable_kg}kg on rate card {rate_card.id}")

        return {
            "rate_per_kg": rate_break.rate_per_kg,
            "minimum_charge": rate_card.minimum_charge,
            "rate_break_id": rate_break.id
        }
