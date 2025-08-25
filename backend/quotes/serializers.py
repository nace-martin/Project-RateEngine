from rest_framework import serializers
from .models import Client, RateCard, Quote

class ClientSerializer(serializers.ModelSerializer):
    class Meta:
        model = Client
        fields = '__all__' # This will include all fields from the Client model

class RateCardSerializer(serializers.ModelSerializer):
    class Meta:
        model = RateCard
        fields = '__all__'

class QuoteSerializer(serializers.ModelSerializer):
    # This nested serializer provides the client's name in read operations
    client = ClientSerializer(read_only=True)
    # This field is for writing (creating/updating) the client relationship
    client_id = serializers.PrimaryKeyRelatedField(
        queryset=Client.objects.all(), source='client', write_only=True
    )

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
            'base_cost', 'total_sell'
        ]