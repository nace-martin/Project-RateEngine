# backend/quotes/serializers.py

from decimal import Decimal
from rest_framework import serializers
from .models import Quote, QuoteVersion, QuoteLine, QuoteTotal
from services.models import ServiceComponent, SERVICE_SCOPE_CHOICES
from parties.models import Company, Contact
# --- ADDED IMPORTS ---
from core.models import Location
from parties.serializers import CustomerV3Serializer, ContactV3Serializer
# --- END IMPORTS ---

# --- V3 Serializers ---

class V3DimensionInputSerializer(serializers.Serializer):
    """Serializer for the 'dimensions' list in the compute request."""
    pieces = serializers.IntegerField(min_value=1)
    length_cm = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal('0.01'))
    width_cm = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal('0.01'))
    height_cm = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal('0.01'))
    gross_weight_kg = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal('0.01'))

class V3ManualOverrideSerializer(serializers.Serializer):
    """Serializer for the 'overrides' list in the compute request."""
    service_component_id = serializers.UUIDField()
    cost_fcy = serializers.DecimalField(max_digits=12, decimal_places=2)
    currency = serializers.CharField(max_length=3)
    unit = serializers.CharField(max_length=20)
    min_charge_fcy = serializers.DecimalField(max_digits=12, decimal_places=2, required=False)

class QuoteComputeRequestSerializer(serializers.Serializer):
    """
    Validates the V3 compute request from the frontend.
    This is what the user *sends*.
    """
    quote_id = serializers.UUIDField(required=False, allow_null=True)
    customer_id = serializers.UUIDField()
    contact_id = serializers.UUIDField()
    mode = serializers.CharField() # We'll validate choices in the view
    
    service_scope = serializers.ChoiceField(
        choices=SERVICE_SCOPE_CHOICES,
        required=True,
        help_text="Required scope selection for V3 engine."
    )
    origin_location_id = serializers.PrimaryKeyRelatedField(
        queryset=Location.objects.filter(is_active=True),
        source='origin_location',
        help_text="UUID of the origin Location object."
    )
    destination_location_id = serializers.PrimaryKeyRelatedField(
        queryset=Location.objects.filter(is_active=True),
        source='destination_location',
        help_text="UUID of the destination Location object."
    )
    
    incoterm = serializers.CharField(max_length=3)
    payment_term = serializers.ChoiceField(choices=Quote.PaymentTerm.choices)
    is_dangerous_goods = serializers.BooleanField(default=False)
    dimensions = V3DimensionInputSerializer(many=True, required=True)
    overrides = V3ManualOverrideSerializer(many=True, required=False)
    spot_rates = serializers.DictField(required=False, allow_null=True)

    def validate_dimensions(self, value):
        if not value or len(value) == 0:
            raise serializers.ValidationError("At least one dimension line is required.")
        return value

    def validate(self, attrs):
        legacy_errors = {}
        if 'origin_airport_code' in self.initial_data or 'origin_airport' in self.initial_data:
            legacy_errors['origin_location_id'] = ["Use 'origin_location_id' (UUID) instead of legacy airport fields."]
        if 'destination_airport_code' in self.initial_data or 'destination_airport' in self.initial_data:
            legacy_errors['destination_location_id'] = ["Use 'destination_location_id' (UUID) instead of legacy airport fields."]
        if 'shipment_type' in self.initial_data:
            legacy_errors['shipment_type'] = ["Shipment type is derived automatically and should not be provided."]
        if legacy_errors:
            raise serializers.ValidationError(legacy_errors)

        return attrs

# --- V3 RESPONSE SERIALIZERS ---
# These define what the API *returns* to the frontend.

class V3ServiceComponentSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServiceComponent
        fields = ('id', 'code', 'description', 'category', 'unit', 'leg')

class V3QuoteLineSerializer(serializers.ModelSerializer):
    service_component = V3ServiceComponentSerializer()
    class Meta:
        model = QuoteLine
        exclude = ('quote_version',) # Exclude the parent link

class V3QuoteTotalSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuoteTotal
        exclude = ('quote_version',) # Exclude the parent link

class V3QuoteVersionSerializer(serializers.ModelSerializer):
    lines = V3QuoteLineSerializer(many=True)
    totals = V3QuoteTotalSerializer()
    class Meta:
        model = QuoteVersion
        exclude = ('quote',) # Exclude the parent link

# --- V3 RESPONSE SERIALIZERS ---
# These define what the API *returns* to the frontend.

class V3ServiceComponentSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServiceComponent
        fields = ('id', 'code', 'description', 'category', 'unit')

class V3QuoteLineSerializer(serializers.ModelSerializer):
    service_component = V3ServiceComponentSerializer()
    class Meta:
        model = QuoteLine
        exclude = ('quote_version',) # Exclude the parent link

class V3QuoteTotalSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuoteTotal
        exclude = ('quote_version',) # Exclude the parent link

class V3QuoteVersionSerializer(serializers.ModelSerializer):
    lines = V3QuoteLineSerializer(many=True)
    totals = V3QuoteTotalSerializer()
    class Meta:
        model = QuoteVersion
        exclude = ('quote',) # Exclude the parent link

class QuoteModelSerializerV3(serializers.ModelSerializer):
    """
    The main serializer for the Quote model, used for GET requests
    and as the response for the compute endpoint.
    """
    latest_version = V3QuoteVersionSerializer(read_only=True)
    
    # --- UPDATED FIELDS ---
    customer = CustomerV3Serializer(read_only=True)
    contact = ContactV3Serializer(read_only=True)
    
    # Use StringRelatedField to return the IATA code (e.g., "BNE")
    origin_location = serializers.StringRelatedField()
    destination_location = serializers.StringRelatedField()
    class Meta:
        model = Quote
        # --- UPDATED FIELDS ---
        fields = (
            'id', 'quote_number', 'customer', 'contact', 'mode', 
            'shipment_type', 'incoterm', 'payment_term', 'service_scope', 'output_currency', 
            'origin_location', 'destination_location',
            # 'origin_port', 'destination_port', # Add when ready for SEA
            'status', 'valid_until', 'created_at', 'latest_version'
        )
        # --- END UPDATES ---
