from rest_framework import serializers
from .models import Client, RateCard, Quote


# Minimal inline serializer for client reference (id + name only)
class InlineClientSerializer(serializers.ModelSerializer):
    class Meta:
        model = Client
        fields = ['id', 'name']

class RateCardSerializer(serializers.ModelSerializer):
    class Meta:
        model = RateCard
        fields = '__all__'


class QuoteSerializer(serializers.ModelSerializer):
    # Minimal client info for read operations
    client = InlineClientSerializer(read_only=True)
    # For PATCH/partial updates, client_id is optional
    client_id = serializers.PrimaryKeyRelatedField(
        queryset=Client.objects.none(), source='client', write_only=True, required=False
    )

    def get_fields(self):
        fields = super().get_fields()
        # Scope client_id queryset to the request's tenant/org/permissions
        request = self.context.get('request', None)
        if request:
            # Example: filter by organization, replace with your logic
            # org = getattr(request.user, 'organization', None)
            # fields['client_id'].queryset = Client.objects.filter(organization=org)
            fields['client_id'].queryset = Client.objects.all()  # TODO: restrict as needed
        else:
            fields['client_id'].queryset = Client.objects.none()
        return fields

    class Meta:
        model = Quote
        # List all fields, ensuring calculated ones are handled
        fields = [
            'id', 'client', 'client_id', 'origin', 'destination', 'mode',
            'actual_weight_kg', 'volume_cbm', 'chargeable_weight_kg',
            'rate_used_per_kg', 'base_cost', 'margin_pct', 'total_sell',
            'created_at'
        ]
        # Mark server-calculated fields as read_only
        read_only_fields = [
            'chargeable_weight_kg', 'rate_used_per_kg',
            'base_cost', 'total_sell', 'created_at'
        ]

    # Field validators
    def validate_actual_weight_kg(self, value):
        if value < 0:
            raise serializers.ValidationError("actual_weight_kg must be non-negative.")
        return value

    def validate_volume_cbm(self, value):
        if value < 0:
            raise serializers.ValidationError("volume_cbm must be non-negative.")
        return value

    def validate_margin_pct(self, value):
        # margin_pct is expected in the range 0..100 (percent)
        if not (0 <= value <= 100):
            raise serializers.ValidationError("margin_pct must be between 0 and 100 (percent).")
        return value