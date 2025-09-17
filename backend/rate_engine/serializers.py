from __future__ import annotations

from rest_framework import serializers

from organizations.models import Organizations


class PieceSerializer(serializers.Serializer):
    weight_kg = serializers.DecimalField(max_digits=12, decimal_places=3)
    length_cm = serializers.DecimalField(max_digits=12, decimal_places=1, required=False)
    width_cm = serializers.DecimalField(max_digits=12, decimal_places=1, required=False)
    height_cm = serializers.DecimalField(max_digits=12, decimal_places=1, required=False)


class ComputeRequestSerializer(serializers.Serializer):
    origin_iata = serializers.CharField()
    dest_iata = serializers.CharField()
    shipment_type = serializers.ChoiceField(choices=("IMPORT", "EXPORT", "DOMESTIC"))
    service_scope = serializers.ChoiceField(
        choices=("DOOR_DOOR", "DOOR_AIRPORT", "AIRPORT_DOOR", "AIRPORT_AIRPORT")
    )
    incoterm = serializers.CharField(required=False, allow_null=True, allow_blank=True, max_length=16)
    org_id = serializers.IntegerField()
    commodity_code = serializers.CharField(required=False, max_length=8, default="GCR")
    is_urgent = serializers.BooleanField(required=False, default=False)
    airline_hint = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    via_hint = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    pieces = PieceSerializer(many=True)
    flags = serializers.JSONField(required=False)
    duties_value_sell_ccy = serializers.DecimalField(max_digits=14, decimal_places=2, required=False)
    pallets = serializers.IntegerField(required=False)
    provider_hint = serializers.IntegerField(required=False)
    caf_pct = serializers.DecimalField(max_digits=6, decimal_places=4, required=False)

    def validate_org_id(self, value: int):
        """Ensure the payer organization exists before processing."""
        if not Organizations.objects.filter(id=value).exists():
            raise serializers.ValidationError("Invalid Payer/Organization ID.")
        return value

    def validate_commodity_code(self, value: str) -> str:
        """Normalize and validate commodity code against allowed set."""
        if value is None:
            return "GCR"
        normalized = (value or "").strip().upper()
        allowed = {"GCR", "DGR", "LAR", "PER"}
        if not normalized:
            return "GCR"
        if len(normalized) > 8:
            raise serializers.ValidationError("commodity_code must be at most 8 characters.")
        if normalized not in allowed:
            raise serializers.ValidationError(
                f"Invalid commodity_code. Allowed: {', '.join(sorted(allowed))}."
            )
        return normalized

