# backend/quotes/serializers_v2.py

from rest_framework import serializers
from .models import Quote, QuoteLine, QuoteTotal
from parties.models import Company

class QuoteCreateSerializerV2(serializers.Serializer):
    """
    Validates the incoming payload for a new quote request.
    This matches the structure defined in our "Backend & Data Design Spec".
    """
    # scenario = serializers.ChoiceField(choices=Quote.Scenario.choices)
    chargeable_kg = serializers.DecimalField(max_digits=10, decimal_places=2)
    
    # We expect UUIDs for the party IDs
    bill_to_id = serializers.UUIDField()
    shipper_id = serializers.UUIDField()
    consignee_id = serializers.UUIDField()

    # Optional fields
    policy_id = serializers.CharField(required=False, default="current")
    fx_asof = serializers.DateField(required=False)
    buy_lines = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        default=[]
    )
    
    def validate_bill_to_id(self, value):
        if not Company.objects.filter(id=value).exists():
            raise serializers.ValidationError("Company with the provided bill_to_id does not exist.")
        return value

    def validate_shipper_id(self, value):
        if not Company.objects.filter(id=value).exists():
            raise serializers.ValidationError("Company with the provided shipper_id does not exist.")
        return value

    def validate_consignee_id(self, value):
        if not Company.objects.filter(id=value).exists():
            raise serializers.ValidationError("Company with the provided consignee_id does not exist.")
        return value


class QuoteLineSerializerV2(serializers.ModelSerializer):
    class Meta:
        model = QuoteLine
        fields = [
            'section', 'charge_code', 'description', 'sell_amount_pgk', 'gst_amount_pgk'
        ]

class QuoteTotalSerializerV2(serializers.ModelSerializer):
    class Meta:
        model = QuoteTotal
        fields = [
            'subtotal_pgk', 'gst_total_pgk', 'grand_total_pgk', 
            'output_currency', 'grand_total_output_currency'
        ]

class QuoteResponseSerializerV2(serializers.ModelSerializer):
    """
    Formats the final quote object for the API response.
    """
    lines = QuoteLineSerializerV2(many=True)
    totals = QuoteTotalSerializerV2()
    
    # We can add an audit block here later as specified in the spec
    # audit = serializers.SerializerMethodField()

    class Meta:
        model = Quote
        fields = [
            'id', 'quote_number', 'status', 'lines', 'totals'
        ]