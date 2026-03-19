# backend/quotes/serializers.py

from decimal import Decimal
import re
from rest_framework import serializers
from quotes.branding import get_quote_branding
from .models import Quote, QuoteVersion, QuoteLine, QuoteTotal
from services.models import ServiceComponent, SERVICE_SCOPE_CHOICES
from parties.models import Company, Contact
# --- ADDED IMPORTS ---
from core.commodity import (
    COMMODITY_CODE_DG,
    DEFAULT_COMMODITY_CODE,
    validate_commodity_code,
)
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
    commodity_code = serializers.CharField(max_length=10, required=False, default=DEFAULT_COMMODITY_CODE)
    is_dangerous_goods = serializers.BooleanField(default=False)
    dimensions = V3DimensionInputSerializer(many=True, required=True)
    overrides = V3ManualOverrideSerializer(many=True, required=False)
    spot_rates = serializers.DictField(required=False, allow_null=True)

    def validate_commodity_code(self, value):
        try:
            return validate_commodity_code(value)
        except ValueError as exc:
            raise serializers.ValidationError(str(exc)) from exc

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

        commodity_code = attrs.get('commodity_code', DEFAULT_COMMODITY_CODE)
        is_dangerous_goods = attrs.get('is_dangerous_goods', False)
        if is_dangerous_goods and commodity_code == DEFAULT_COMMODITY_CODE:
            commodity_code = COMMODITY_CODE_DG
        elif commodity_code == COMMODITY_CODE_DG:
            attrs['is_dangerous_goods'] = True
        elif is_dangerous_goods:
            raise serializers.ValidationError({
                'is_dangerous_goods': ["is_dangerous_goods can only be true when commodity_code is DG."]
            })
        attrs['commodity_code'] = commodity_code

        return attrs

# --- V3 RESPONSE SERIALIZERS ---
# These define what the API *returns* to the frontend.

class V3ServiceComponentSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServiceComponent
        fields = ('id', 'code', 'description', 'category', 'unit', 'leg')

class V3QuoteLineSerializer(serializers.ModelSerializer):
    """
    Serializer for QuoteLine with RBAC-based field masking.
    SALES role users cannot see cost/COGS fields.
    """
    service_component = V3ServiceComponentSerializer()
    # Alias for frontend compatibility (some components look for 'component' code)
    component = serializers.CharField(source='service_component.code', read_only=True)
    description = serializers.CharField(source='service_component.description', read_only=True)
    
    class Meta:
        model = QuoteLine
        fields = (
            'id', 'service_component', 'component', 'description', 
            'cost_pgk', 'cost_fcy', 'cost_fcy_currency',
            'sell_pgk', 'sell_pgk_incl_gst', 'sell_fcy', 'sell_fcy_incl_gst',
            'sell_fcy_currency', 'exchange_rate', 'cost_source',
            'cost_source_description', 'is_rate_missing', 'leg', 'bucket',
            'gst_category', 'gst_rate', 'gst_amount'
        )
    
    def to_representation(self, instance):
        """Mask cost fields if user cannot view COGS."""
        data = super().to_representation(instance)
        
        # FRONTEND FIX: The UI expects gst_amount to be in FCY if quote is FCY
        # But it also uses it for PGK. We ensure it's always the applicable GST for display.
        if instance.sell_fcy_currency != 'PGK':
            # For FCY quotes, use the FCY GST amount
            data['gst_amount'] = (instance.sell_fcy_incl_gst - instance.sell_fcy).quantize(Decimal('0.01'))
        
        request = self.context.get('request')
        if request and hasattr(request, 'user') and request.user.is_authenticated:
            if not getattr(request.user, 'can_view_cogs', True):
                # Mask cost/COGS fields for SALES users
                data['cost_pgk'] = None
                data['cost_fcy'] = None
                data['cost_fcy_currency'] = None
        
        return data

class V3QuoteTotalSerializer(serializers.ModelSerializer):
    """
    Serializer for QuoteTotal with RBAC-based field masking.
    SALES role users cannot see cost totals.
    """
    # Alias for frontend compatibility
    currency = serializers.CharField(source='total_sell_fcy_currency', read_only=True)
    total_sell_ex_gst = serializers.DecimalField(source='total_sell_fcy', max_digits=12, decimal_places=2, read_only=True)
    # UI looks for 'gst_amount' in totals
    gst_amount = serializers.SerializerMethodField()
    total_quote_amount = serializers.DecimalField(source='total_sell_fcy_incl_gst', max_digits=12, decimal_places=2, read_only=True)
    
    class Meta:
        model = QuoteTotal
        fields = (
            'currency',
            'total_cost_pgk',
            'total_sell_pgk', 'total_sell_pgk_incl_gst',
            'total_sell_fcy', 'total_sell_fcy_incl_gst', 'total_sell_fcy_currency',
            'total_sell_ex_gst', 'gst_amount', 'total_quote_amount',
            'has_missing_rates', 'notes',
        )
    
    def get_gst_amount(self, obj):
        """Derive total GST in FCY from the difference between Inc and Ex totals."""
        return (obj.total_sell_fcy_incl_gst - obj.total_sell_fcy).quantize(Decimal('0.01'))

    def to_representation(self, instance):
        """Mask cost totals if user cannot view COGS."""
        data = super().to_representation(instance)
        
        request = self.context.get('request')
        if request and hasattr(request, 'user') and request.user.is_authenticated:
            if not getattr(request.user, 'can_view_cogs', True):
                # Mask cost totals for SALES users
                data['total_cost_pgk'] = None
        
        return data

class V3QuoteVersionSerializer(serializers.ModelSerializer):
    lines = V3QuoteLineSerializer(many=True)
    totals = V3QuoteTotalSerializer()
    class Meta:
        model = QuoteVersion
        exclude = ('quote',) # Exclude the parent link

# --- SPOT CHARGE LINE SERIALIZERS ---



class V3QuoteVersionSummarySerializer(serializers.ModelSerializer):
    totals = V3QuoteTotalSerializer()
    total_weight_kg = serializers.SerializerMethodField()

    class Meta:
        model = QuoteVersion
        exclude = ('quote', 'payload_json') # Include payload_json for frontend weight calculation fallback

    def get_total_weight_kg(self, obj):
        try:
            if not obj.payload_json or 'dimensions' not in obj.payload_json:
                return 0
            
            dims = obj.payload_json.get('dimensions', [])
            total = sum(float(d.get('gross_weight_kg', 0) or 0) for d in dims)
            return round(total)
        except (ValueError, TypeError, AttributeError):
            return 0


class QuoteBrandingSerializer(serializers.Serializer):
    display_name = serializers.CharField()
    support_email = serializers.CharField(allow_blank=True)
    support_phone = serializers.CharField(allow_blank=True)
    website_url = serializers.CharField(allow_blank=True)
    address_lines = serializers.ListField(child=serializers.CharField(), allow_empty=True)
    public_quote_tagline = serializers.CharField(allow_blank=True)
    primary_color = serializers.CharField(allow_blank=True)
    accent_color = serializers.CharField(allow_blank=True)
    logo_url = serializers.CharField(allow_null=True, allow_blank=True)

class QuoteModelSerializerV3(serializers.ModelSerializer):
    """
    The main serializer for the Quote model, used for GET requests
    and as the response for the compute endpoint.
    """
    latest_version = V3QuoteVersionSerializer(read_only=True)
    
    # --- UPDATED FIELDS ---
    customer = CustomerV3Serializer(read_only=True)
    contact = ContactV3Serializer(read_only=True)
    
    origin_location = serializers.StringRelatedField()
    destination_location = serializers.StringRelatedField()
    
    # Expose the creator as the "Agent"
    created_by = serializers.SerializerMethodField()
    rate_provider = serializers.SerializerMethodField()
    spot_negotiation = serializers.SerializerMethodField()
    branding = serializers.SerializerMethodField()
    
    def get_created_by(self, obj):
        if not obj.created_by:
            return None
        user = obj.created_by
        full_name = f"{user.first_name} {user.last_name}".strip()
        return full_name if full_name else user.username

    def get_rate_provider(self, obj):
        """
        Aggregate unique rate providers (Agents) from line items.
        """
        if not hasattr(obj, 'latest_version') or not obj.latest_version:
            return None
            
        # Optimization: This relies on lines being prefetched in the viewset query
        lines = obj.latest_version.lines.all()
        providers = set()
        ignored_exact = {
            'V4 ENGINE',
            'SPOT ENVELOPE',
            'N/A (SELL ONLY)',
            'COGS',
            'N/A',
            'BASE_COST',
            'DEFAULT',
            'AGENT REPLY (AI)',
            'SYSTEM',
            '',
        }
        
        for line in lines:
            source = str(line.cost_source or '').strip()
            if not source:
                continue

            source_upper = source.upper()
            # Internal/system markers should never be shown as "Rate Provider".
            if source_upper in ignored_exact:
                continue
            if source_upper.startswith('DEFAULT '):
                continue
            if re.search(r'\b\d+(?:\.\d+)?%\s+OF\s+COGS\b', source_upper):
                continue

            providers.add(source)
        
        if not providers:
            return "Internal"
            
        return ", ".join(sorted(providers))

    def get_spot_negotiation(self, obj):
        spe = getattr(obj, 'spot_envelopes', None)
        if not spe:
            return None
        latest = spe.order_by('-created_at', '-id').first()
        if not latest:
            return None
        return {'id': str(latest.id)}

    def get_branding(self, obj):
        branding = get_quote_branding(obj)
        return QuoteBrandingSerializer(branding).data

    class Meta:
        model = Quote
        fields = (
            'id', 'quote_number', 'customer', 'contact', 'mode', 
            'shipment_type', 'incoterm', 'payment_term', 'service_scope', 'commodity_code', 'output_currency', 
            'origin_location', 'destination_location',
            'status', 'valid_until', 'created_at',
            'latest_version', 'request_details_json', 'spot_negotiation',
            'created_by', 'rate_provider', 'branding'
        )

class QuoteListSerializerV3(serializers.ModelSerializer):
    """
    Lightweight serializer for listing quotes.
    Uses a summary version without line items.
    """
    latest_version = V3QuoteVersionSummarySerializer(read_only=True)
    customer = CustomerV3Serializer(read_only=True)
    contact = ContactV3Serializer(read_only=True)
    origin_location = serializers.StringRelatedField()
    destination_location = serializers.StringRelatedField()
    created_by = serializers.SerializerMethodField()
    spot_negotiation = serializers.SerializerMethodField()
    branding = serializers.SerializerMethodField()

    def get_created_by(self, obj):
        if not obj.created_by:
            return None
        user = obj.created_by
        full_name = f"{user.first_name} {user.last_name}".strip()
        return full_name if full_name else user.username

    def get_spot_negotiation(self, obj):
        spe = getattr(obj, 'spot_envelopes', None)
        if not spe:
            return None
        latest = spe.order_by('-created_at', '-id').first()
        if not latest:
            return None
        return {'id': str(latest.id)}

    def get_branding(self, obj):
        branding = get_quote_branding(obj)
        return QuoteBrandingSerializer(branding).data

    class Meta:
        model = Quote
        fields = (
            'id', 'quote_number', 'customer', 'contact', 'mode', 
            'shipment_type', 'incoterm', 'payment_term', 'service_scope', 'commodity_code', 'output_currency', 
            'origin_location', 'destination_location',
            'status', 'valid_until', 'created_at',
            'latest_version', 'created_by', 'branding',
            'spot_negotiation'
        )


# =============================================================================
# SPOT PRICING ENVELOPE SERIALIZERS
# =============================================================================

from quotes.spot_models import (
    SpotPricingEnvelopeDB,
    SPESourceBatchDB,
    SPEChargeLineDB,
    SPEAcknowledgementDB,
    SPEManagerApprovalDB,
)

class SPESourceBatchSerializer(serializers.ModelSerializer):
    charge_count = serializers.SerializerMethodField()

    class Meta:
        model = SPESourceBatchDB
        fields = (
            'id', 'source_kind', 'source_type', 'target_bucket', 'label',
            'source_reference', 'file_name', 'file_content_type',
            'analysis_summary_json', 'created_at', 'updated_at', 'charge_count',
        )

    def get_charge_count(self, obj):
        return obj.charge_lines.count()


class SPEChargeLineSerializer(serializers.ModelSerializer):
    source_batch_id = serializers.SerializerMethodField()
    source_batch_label = serializers.SerializerMethodField()
    min_charge = serializers.SerializerMethodField()
    amount = serializers.SerializerMethodField()
    rate = serializers.SerializerMethodField()
    min_amount = serializers.SerializerMethodField()
    max_amount = serializers.SerializerMethodField()
    percent = serializers.SerializerMethodField()
    rule_display = serializers.SerializerMethodField()
    
    class Meta:
        model = SPEChargeLineDB
        fields = (
            'id', 'code', 'description', 'amount', 'currency', 'unit',
            'bucket', 'is_primary_cost', 'conditional', 'min_charge',
            'note', 'exclude_from_totals', 'percentage_basis', 'source_reference',
            'source_batch_id', 'source_batch_label',
            'calculation_type', 'unit_type', 'rate', 'min_amount', 'max_amount',
            'percent', 'percent_basis', 'rule_meta', 'rule_display'
        )

    def get_source_batch_id(self, obj):
        return str(obj.source_batch_id) if obj.source_batch_id else None

    def get_source_batch_label(self, obj):
        return obj.source_batch.label if obj.source_batch_id else None

    def get_amount(self, obj):
        # Return as string to match original serialization
        return str(obj.amount)

    def get_min_charge(self, obj):
        return str(obj.min_charge) if obj.min_charge is not None else None

    def get_rate(self, obj):
        return str(obj.rate) if obj.rate is not None else None

    def get_min_amount(self, obj):
        return str(obj.min_amount) if obj.min_amount is not None else None

    def get_max_amount(self, obj):
        return str(obj.max_amount) if obj.max_amount is not None else None

    def get_percent(self, obj):
        return str(obj.percent) if obj.percent is not None else None

    def get_rule_display(self, obj):
        calc = (obj.calculation_type or "").lower()
        rate = obj.rate if obj.rate is not None else obj.amount
        unit_type = (obj.unit_type or "").lower()
        min_amount = obj.min_amount if obj.min_amount is not None else obj.min_charge

        unit_label_map = {
            "kg": "kg",
            "shipment": "shipment",
            "awb": "awb",
            "trip": "trip",
            "set": "set",
            "line": "line",
            "man": "man",
            "cbm": "cbm",
            "rt": "rt",
        }
        unit_label = unit_label_map.get(unit_type, unit_type or "unit")

        if calc == "min_or_per_unit" and min_amount is not None and rate is not None:
            return f"{min_amount} min or {rate}/{unit_label}"
        if calc == "per_unit" and rate is not None:
            return f"{rate}/{unit_label}"
        if calc == "flat" and rate is not None:
            return f"{rate} flat"
        if calc == "percent_of" and obj.percent is not None:
            basis = obj.percent_basis or obj.percentage_basis or "basis"
            return f"{obj.percent}% of {basis}"
        return None


class SPEAcknowledgementSerializer(serializers.ModelSerializer):
    acknowledged_by_user_id = serializers.SerializerMethodField()
    
    class Meta:
        model = SPEAcknowledgementDB
        fields = ('acknowledged_by_user_id', 'acknowledged_at', 'statement')
        
    def get_acknowledged_by_user_id(self, obj):
        return str(obj.acknowledged_by_id) if obj.acknowledged_by_id else None


class SPEManagerApprovalSerializer(serializers.ModelSerializer):
    manager_user_id = serializers.SerializerMethodField()
    
    class Meta:
        model = SPEManagerApprovalDB
        fields = ('approved', 'manager_user_id', 'decision_at', 'comment')
        
    def get_manager_user_id(self, obj):
        return str(obj.manager_id) if obj.manager_id else None


class SpotPricingEnvelopeSerializer(serializers.ModelSerializer):
    customer_name = serializers.SerializerMethodField()
    shipment = serializers.JSONField(source='shipment_context_json')
    conditions = serializers.JSONField(source='conditions_json')
    charges = SPEChargeLineSerializer(source='charge_lines', many=True, read_only=True)
    sources = SPESourceBatchSerializer(source='source_batches', many=True, read_only=True)
    acknowledgement = SPEAcknowledgementSerializer(read_only=True)
    manager_approval = SPEManagerApprovalSerializer(read_only=True)
    
    missing_mandatory_fields = serializers.SerializerMethodField()
    can_proceed = serializers.SerializerMethodField()
    has_acknowledgement = serializers.SerializerMethodField()
    context_integrity_valid = serializers.SerializerMethodField()
    
    class Meta:
        model = SpotPricingEnvelopeDB
        fields = (
            'id', 'status', 'customer_name', 'shipment', 'conditions',
            'spot_trigger_reason_code', 'spot_trigger_reason_text',
            'created_at', 'expires_at', 'is_expired',
            'shipment_context_hash', 'context_integrity_valid',
            'has_acknowledgement', 'acknowledgement', 'manager_approval',
            'missing_mandatory_fields', 'can_proceed', 'sources', 'charges'
        )
        read_only_fields = fields

    def get_customer_name(self, obj):
        if obj.quote and obj.quote.customer:
            return obj.quote.customer.name
        shipment_ctx = getattr(obj, "shipment_context_json", None) or {}
        customer_name = shipment_ctx.get("customer_name")
        if customer_name:
            return str(customer_name)
        return None

    def get_has_acknowledgement(self, obj):
        return hasattr(obj, 'acknowledgement') and obj.acknowledgement is not None

    def get_context_integrity_valid(self, obj):
        return obj.verify_context_integrity()

    def get_missing_mandatory_fields(self, obj) -> list:
        missing = []
        charges = obj.charge_lines.all()
        
        # Check if we have at least one rate charge
        has_rate = any(
            cl.amount is not None and float(cl.amount) > 0 
            for cl in charges
        )
        if not has_rate:
            missing.append('rate')
        
        # Check if all charges have currency
        has_currency = all(cl.currency for cl in charges) if charges else False
        if not has_currency:
            missing.append('currency')
        
        return missing

    def get_can_proceed(self, obj) -> bool:
        return len(self.get_missing_mandatory_fields(obj)) == 0

