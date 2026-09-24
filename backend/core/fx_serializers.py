# backend/core/fx_serializers.py
"""Serializers for FX Rate Management API."""

from decimal import Decimal

from rest_framework import serializers


class CurrencyRateInputSerializer(serializers.Serializer):
    """Validate one canonical FCY/PGK market quote.

    Manual rates are always entered as PGK per one unit of foreign currency,
    regardless of whether the numeric value happens to be above or below 1.
    """

    tt_buy = serializers.DecimalField(
        max_digits=18,
        decimal_places=8,
        min_value=Decimal("0.0001"),
        help_text="TT Buy rate (PGK per 1 FCY)",
    )
    tt_sell = serializers.DecimalField(
        max_digits=18,
        decimal_places=8,
        min_value=Decimal("0.0001"),
        help_text="TT Sell rate (PGK per 1 FCY)",
    )

    def validate(self, data):
        tt_buy = data.get("tt_buy")
        tt_sell = data.get("tt_sell")
        if tt_buy is not None and tt_sell is not None and tt_sell < tt_buy:
            raise serializers.ValidationError(
                "For canonical FCY/PGK rates, TT Sell must be greater than or equal to TT Buy."
            )
        return data


class ManualFxUpdateSerializer(serializers.Serializer):
    """Validate manual canonical FX market facts.

    Expected format::

        {
            "rates": {
                "AUD": {"tt_buy": 2.45, "tt_sell": 2.52},
                "USD": {"tt_buy": 3.85, "tt_sell": 3.95}
            },
            "note": "Optional reason for manual update"
        }

    Currency keys are foreign currencies.  PGK is the implicit quote currency.
    """

    rates = serializers.DictField(
        child=CurrencyRateInputSerializer(),
        help_text="FCY/PGK rates keyed by foreign currency code (e.g. AUD, USD).",
    )
    note = serializers.CharField(
        max_length=500,
        required=False,
        allow_blank=True,
        help_text="Optional note explaining reason for manual update",
    )

    def validate_rates(self, value):
        if not value:
            raise serializers.ValidationError("At least one currency rate is required")

        normalized = {}
        for currency_code, rate_info in value.items():
            code = str(currency_code or "").strip().upper()
            if len(code) != 3 or not code.isalpha():
                raise serializers.ValidationError(
                    f"Invalid currency code '{currency_code}'. Must be a 3-letter code."
                )
            if code == "PGK":
                raise serializers.ValidationError(
                    "PGK is the quote currency for manual market rates and cannot be entered as a foreign currency key."
                )
            normalized[code] = rate_info
        return normalized


class CurrencyRateStatusSerializer(serializers.Serializer):
    """Serialize a single currency's rate status."""

    currency = serializers.CharField()
    tt_buy = serializers.DecimalField(max_digits=18, decimal_places=4)
    tt_sell = serializers.DecimalField(max_digits=18, decimal_places=4)


class FxStatusSerializer(serializers.Serializer):
    """Serialize FX status response with staleness information."""

    rates = CurrencyRateStatusSerializer(many=True)
    last_updated = serializers.DateTimeField()
    source = serializers.CharField()
    is_stale = serializers.BooleanField(
        help_text="True if rates are older than the current warning threshold"
    )
    staleness_hours = serializers.FloatField(
        help_text="Hours since last update"
    )
    staleness_warning = serializers.CharField(
        required=False,
        allow_null=True,
        help_text="Warning message if rates are stale",
    )
