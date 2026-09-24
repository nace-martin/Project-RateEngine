# backend/core/fx_serializers.py
"""
Serializers for FX Rate Management API.
"""

from decimal import Decimal
import re
from rest_framework import serializers


class CurrencyRateInputSerializer(serializers.Serializer):
    """Validates TT Buy/Sell rates for a single currency."""
    tt_buy = serializers.DecimalField(
        max_digits=18, 
        decimal_places=8, 
        min_value=Decimal('0.0001'),
        help_text="TT Buy rate (PGK per FCY)"
    )
    tt_sell = serializers.DecimalField(
        max_digits=18, 
        decimal_places=8, 
        min_value=Decimal('0.0001'),
        help_text="TT Sell rate (PGK per FCY)"
    )

    def validate(self, data):
        """
        Manual input is always FCY/PGK, regardless of rate magnitude.
        """
        tt_buy = data.get('tt_buy')
        tt_sell = data.get('tt_sell')
        
        if tt_buy is not None and tt_sell is not None and tt_sell < tt_buy:
            raise serializers.ValidationError("TT SELL must be >= TT BUY for FCY/PGK")
                
        return data


class ManualFxUpdateSerializer(serializers.Serializer):
    """
    Validates manual FX rate update requests.
    
    Expected format:
    {
        "rates": {
            "AUD": {"tt_buy": 2.77, "tt_sell": 2.85},
            "USD": {"tt_buy": 3.85, "tt_sell": 3.95}
        },
        "note": "Optional reason for manual update"
    }
    """
    rates = serializers.DictField(
        child=CurrencyRateInputSerializer(),
        help_text="Currency rates to update. Keys are currency codes (e.g., 'AUD', 'USD')."
    )
    note = serializers.CharField(
        max_length=500, 
        required=False, 
        allow_blank=True,
        help_text="Optional note explaining reason for manual update"
    )

    def validate_rates(self, value):
        """Validate currency codes are valid 3-letter codes."""
        if not value:
            raise serializers.ValidationError("At least one currency rate is required")
        
        normalized_codes = set()
        for currency_code in value:
            normalized = currency_code.upper()
            if not re.fullmatch(r"[A-Z]{3}", normalized) or normalized == "PGK":
                raise serializers.ValidationError(
                    f"Invalid foreign currency code '{currency_code}'. Must be three ASCII letters other than PGK."
                )
            if normalized in normalized_codes:
                raise serializers.ValidationError(f"Duplicate currency code '{normalized}'.")
            normalized_codes.add(normalized)
        return value
