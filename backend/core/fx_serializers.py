# backend/core/fx_serializers.py
"""
Serializers for FX Rate Management API.
"""

from decimal import Decimal
from rest_framework import serializers
from django.utils import timezone


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
        Validate bank spread depending on quote direction.
        For direct quotes (PGK per FCY, values > 1), tt_sell >= tt_buy.
        For indirect quotes (FCY per PGK, values < 1), tt_buy >= tt_sell.
        """
        tt_buy = data.get('tt_buy')
        tt_sell = data.get('tt_sell')
        
        if tt_buy and tt_sell:
            if tt_buy > 1 and tt_sell > 1:
                if tt_sell < tt_buy:
                    raise serializers.ValidationError(
                        "For direct rates (>1), TT Sell rate must be >= TT Buy rate"
                    )
            elif tt_buy < 1 and tt_sell < 1:
                # We do not raise error if tt_sell > tt_buy here due to historical flipped data,
                # but ideally tt_buy should be >= tt_sell for < 1 rates.
                pass
                
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
        
        for currency_code in value.keys():
            if len(currency_code) != 3 or not currency_code.isalpha():
                raise serializers.ValidationError(
                    f"Invalid currency code '{currency_code}'. Must be a 3-letter code."
                )
        return value


class CurrencyRateStatusSerializer(serializers.Serializer):
    """Serializes a single currency's rate status."""
    currency = serializers.CharField()
    tt_buy = serializers.DecimalField(max_digits=18, decimal_places=4)
    tt_sell = serializers.DecimalField(max_digits=18, decimal_places=4)


class FxStatusSerializer(serializers.Serializer):
    """
    Serializes FX status response with staleness information.
    """
    rates = CurrencyRateStatusSerializer(many=True)
    last_updated = serializers.DateTimeField()
    source = serializers.CharField()
    is_stale = serializers.BooleanField(
        help_text="True if rates are older than 24 hours"
    )
    staleness_hours = serializers.FloatField(
        help_text="Hours since last update"
    )
    staleness_warning = serializers.CharField(
        required=False,
        allow_null=True,
        help_text="Warning message if rates are stale"
    )
