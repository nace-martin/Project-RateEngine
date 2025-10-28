# In: backend/quotes/serializers_v3.py

from rest_framework import serializers
from decimal import Decimal

# Import our V3 models
from .models import Quote, QuoteVersion, QuoteLine, QuoteTotal
from services.models import ServiceComponent

class ManualCostOverrideSerializer(serializers.Serializer):
    """
    Serializer for the V3QuoteRequest's 'overrides' field.
    Matches the ManualCostOverride dataclass.
    """
    service_component_id = serializers.IntegerField()
    cost_fcy = serializers.DecimalField(max_digits=10, decimal_places=2)
    currency = serializers.CharField(max_length=3)
    unit = serializers.CharField(max_length=20)
    min_charge_fcy = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)


class DimensionLineSerializer(serializers.Serializer):
    """
    Serializer for a single dimension line in the V3QuoteRequest.
    Matches the DimensionLine dataclass.
    """
    pieces = serializers.IntegerField()
    length_cm = serializers.DecimalField(max_digits=10, decimal_places=2)
    width_cm = serializers.DecimalField(max_digits=10, decimal_places=2)
    height_cm = serializers.DecimalField(max_digits=10, decimal_places=2)
    gross_weight_kg = serializers.DecimalField(max_digits=10, decimal_places=2)

    def validate_pieces(self, value):
        if value <= 0:
            raise serializers.ValidationError("Pieces must be positive.")
        return value

    def validate_length_cm(self, value):
        if value <= 0:
            raise serializers.ValidationError("Length must be positive.")
        return value

    def validate_width_cm(self, value):
        if value <= 0:
            raise serializers.ValidationError("Width must be positive.")
        return value

    def validate_height_cm(self, value):
        if value <= 0:
            raise serializers.ValidationError("Height must be positive.")
        return value

    def validate_gross_weight_kg(self, value):
        if value <= 0:
            raise serializers.ValidationError("Gross weight per piece must be positive.")
        return value


class V3QuoteComputeRequestSerializer(serializers.Serializer):
    """
    Validates the incoming payload for the V3 Compute API.
    Matches the V3QuoteRequest dataclass.
    """
    customer_id = serializers.UUIDField()
    contact_id = serializers.UUIDField()
    mode = serializers.CharField(max_length=10)
    shipment_type = serializers.CharField(max_length=10)
    incoterm = serializers.CharField(max_length=3)
    origin_airport_code = serializers.CharField(max_length=3)
    destination_airport_code = serializers.CharField(max_length=3)
    
    dimensions = DimensionLineSerializer(many=True) # New field
    
    payment_term = serializers.CharField(max_length=10, required=False)
    output_currency = serializers.CharField(max_length=3, required=False)
    is_dangerous_goods = serializers.BooleanField(required=False)
    
    overrides = ManualCostOverrideSerializer(many=True, required=False)


# --- Response Serializers ---
# These serialize our database models to return to the frontend

class ServiceComponentSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServiceComponent
        fields = ['id', 'name', 'category', 'unit']

class QuoteLineSerializer(serializers.ModelSerializer):
    service_component = ServiceComponentSerializer(read_only=True)
    
    class Meta:
        model = QuoteLine
        fields = [
            'id',
            'service_component',
            'cost_pgk',
            'cost_fcy',
            'cost_fcy_currency',
            'sell_pgk',
            'sell_pgk_incl_gst',
            'sell_fcy',
            'sell_fcy_incl_gst',
            'sell_fcy_currency',
            'exchange_rate',
            'cost_source',
            'cost_source_description',
            'is_rate_missing',
        ]

class QuoteTotalSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuoteTotal
        fields = [
            'total_sell_fcy',
            'total_sell_fcy_incl_gst',
            'total_sell_fcy_currency',
            'has_missing_rates',
            'notes',
        ]

class QuoteVersionSerializer(serializers.ModelSerializer):
    lines = QuoteLineSerializer(many=True, read_only=True)
    totals = QuoteTotalSerializer(read_only=True)

    class Meta:
        model = QuoteVersion
        fields = [
            'id',
            'version_number',
            'status',
            'created_at',
            'lines',
            'totals',
        ]

class V3QuoteComputeResponseSerializer(serializers.ModelSerializer):
    """
    Serializes the main Quote object, nesting the LATEST version.
    """
    latest_version = QuoteVersionSerializer(read_only=True, source='versions.first')

    class Meta:
        model = Quote
        fields = [
            'id',
            'quote_number',
            'customer',
            'contact',
            'mode',
            'shipment_type',
            'incoterm',
            'payment_term',
            'output_currency',
            'origin_code',
            'destination_code',
            'status',
            'valid_until',
            'created_at',
            'latest_version', # Nest the latest version here
        ]
        # We order versions by '-version_number' in the model Meta,
        # so 'versions.first' will always be the newest one.

class QuoteEnvelopeV3Serializer(serializers.ModelSerializer):
    """
    Serializer for CREATING a V3 Quote (envelope) only.
    Matches the fields from the old V2 test payload.
    """
    customer_id = serializers.UUIDField(source='customer')
    reference = serializers.CharField(source='quote_number', required=False)
    date = serializers.DateField(write_only=True, required=False)
    validity_days = serializers.IntegerField(write_only=True, default=7)
    service_type = serializers.CharField(source='shipment_type')
    terms = serializers.CharField(source='incoterm')
    scope = serializers.CharField(write_only=True, required=False) # This field is ignored
    sell_currency = serializers.CharField(source='output_currency')

    class Meta:
        model = Quote
        fields = (
            'id',
            'customer_id',
            'reference',
            'date',
            'validity_days',
            'service_type',
            'terms',
            'scope',
            'payment_term',
            'sell_currency',
            'created_at',
        )
        read_only_fields = ('id', 'created_at')

    def create(self, validated_data):
        from datetime import timedelta
        from django.utils import timezone
        from parties.models import Company

        customer_uuid = validated_data.pop('customer')
        customer = Company.objects.get(pk=customer_uuid)
        validated_data['customer'] = customer

        validity_days = validated_data.pop('validity_days', 7)
        validated_data.pop('scope', None)
        validated_data.pop('date', None)

        quote = Quote.objects.create(**validated_data)
        quote.valid_until = timezone.now().date() + timedelta(days=validity_days)
        quote.save()
        return quote
