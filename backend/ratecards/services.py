# backend/ratecards/services.py

from decimal import Decimal
# Ensure Airport is imported if needed, adjust model imports
from .models import RateCard, RateCardBreak 
# from core.models import Airport 

class RateCardService:
    def get_air_freight_rate(self, chargeable_kg: Decimal, origin_code: str, dest_code: str) -> dict:
        """
        Finds the applicable air freight rate for a given weight and lane
        using Airport IATA codes.
        """
        try:
            # --- CHANGE THIS QUERY ---
            rate_card = RateCard.objects.get(
                origin_airport_id=origin_code, # Use FK ID lookup
                destination_airport_id=dest_code, # Use FK ID lookup
                is_active=True
            )
            # --- END CHANGE ---
        except RateCard.DoesNotExist:
            raise ValueError(f"No active rate card found for lane {origin_code}-{dest_code}")

        # Find the correct weight break... (rest of the logic remains the same)
        rate_break = RateCardBreak.objects.filter(
            rate_card=rate_card,
            weight_break_kg__lte=chargeable_kg
        ).order_by('-weight_break_kg').first()

        if not rate_break:
            raise ValueError(f"No applicable weight break found for {chargeable_kg}kg on rate card {rate_card.id}")

        return {
            "rate_per_kg": rate_break.rate_per_kg,
            "minimum_charge": rate_card.minimum_charge,
            "rate_break_id": str(rate_break.id) # Ensure ID is string for source_references later
        }
