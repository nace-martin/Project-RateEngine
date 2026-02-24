from typing import Any

from rest_framework import serializers
from .models import (
    ProductCode, DomesticCOGS, ExportCOGS, ImportCOGS,
    ComponentMargin, CustomerDiscount, Surcharge
)
from parties.models import Company


def _is_internal_pricing_field(field_name: str) -> bool:
    """
    Identify internal/commercial-sensitive pricing fields that must not be
    exposed to Sales users (or any non-manager/admin caller).
    """
    key = (field_name or "").lower()
    if not key:
        return False
    if key.startswith("buy_"):
        return True
    if "cogs" in key or "margin" in key:
        return True
    # V4 engine payloads primarily expose COGS via cost_* / total_cost fields.
    if key.startswith("cost") or "_cost" in key:
        return True
    return False


def scrub_pricing_result_payload(payload: Any, include_internal_fields: bool = False) -> Any:
    """
    Recursively remove internal pricing fields (COGS / cost / buy / margin)
    from a V4 pricing response unless explicitly allowed.
    """
    if include_internal_fields:
        return payload

    if isinstance(payload, dict):
        sanitized = {}
        for key, value in payload.items():
            if _is_internal_pricing_field(str(key)):
                continue
            sanitized[key] = scrub_pricing_result_payload(value, include_internal_fields=False)
        return sanitized

    if isinstance(payload, list):
        return [scrub_pricing_result_payload(item, include_internal_fields=False) for item in payload]

    if isinstance(payload, tuple):
        return tuple(scrub_pricing_result_payload(item, include_internal_fields=False) for item in payload)

    return payload

class ProductCodeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductCode
        fields = ['id', 'code', 'description', 'domain', 'category', 'default_unit']

class DomesticCOGSSerializer(serializers.ModelSerializer):
    class Meta:
        model = DomesticCOGS
        fields = '__all__'

class ExportCOGSSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExportCOGS
        fields = '__all__'

class ImportCOGSSerializer(serializers.ModelSerializer):
    class Meta:
        model = ImportCOGS
        fields = '__all__'

class ComponentMarginSerializer(serializers.ModelSerializer):
    class Meta:
        model = ComponentMargin
        fields = '__all__'

class CustomerDiscountSerializer(serializers.ModelSerializer):
    """Full serializer for create/update operations."""
    customer_name = serializers.CharField(source='customer.name', read_only=True)
    product_code_display = serializers.SerializerMethodField()
    notes = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    min_charge = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, allow_null=True)
    max_charge = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, allow_null=True)
    
    class Meta:
        model = CustomerDiscount
        fields = [
            'id', 'customer', 'customer_name', 'product_code', 'product_code_display',
            'discount_type', 'discount_value', 'currency', 'min_charge', 'max_charge',
            'valid_from', 'valid_until', 'notes',
            'created_at', 'updated_at', 'created_by'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by']
    
    def get_product_code_display(self, obj):
        if obj.product_code:
            return f"{obj.product_code.code} - {obj.product_code.description}"
        return None


class CustomerDiscountListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list view with expanded relations."""
    customer_name = serializers.CharField(source='customer.name', read_only=True)
    product_code_code = serializers.CharField(source='product_code.code', read_only=True)
    product_code_description = serializers.CharField(source='product_code.description', read_only=True)
    product_code_domain = serializers.CharField(source='product_code.domain', read_only=True)
    discount_type_display = serializers.CharField(source='get_discount_type_display', read_only=True)
    is_active = serializers.SerializerMethodField()
    
    class Meta:
        model = CustomerDiscount
        fields = [
            'id', 'customer', 'customer_name',
            'product_code', 'product_code_code', 'product_code_description', 'product_code_domain',
            'discount_type', 'discount_type_display', 'discount_value', 'currency',
            'min_charge', 'max_charge',
            'valid_from', 'valid_until', 'is_active', 'notes',
            'created_at'
        ]
    
    def get_is_active(self, obj):
        from datetime import date
        today = date.today()
        if obj.valid_from and today < obj.valid_from:
            return False
        if obj.valid_until and today > obj.valid_until:
            return False
        return True

# =============================================================================
# V4 QUOTE REQUEST SERIALIZER
# =============================================================================

class CargoDetailsSerializer(serializers.Serializer):
    weight_kg = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0.01)
    volume_m3 = serializers.DecimalField(max_digits=10, decimal_places=3, min_value=0.001)
    quantity = serializers.IntegerField(min_value=1, default=1)
    # Optional: dims? For now simple weight/volume is enough for engine
    
class QuoteRequestSerializerV4(serializers.Serializer):
    """
    Strictly typed request payload for V4 Pricing Engine.
    """
    SERVICE_TYPE_CHOICES = [
        ('DOMESTIC', 'Domestic'),
        ('EXPORT', 'Export'),
        ('IMPORT', 'Import'),
    ]
    
    INCOTERMS_CHOICES = [
        ('EXW', 'Ex Works (EXW)'),
        ('FCA', 'Free Carrier (FCA)'),
        ('FOB', 'Free on Board (FOB)'),
        ('CFR', 'Cost and Freight (CFR)'),
        ('CIF', 'Cost, Insurance & Freight (CIF)'),
        ('DAP', 'Delivered at Place (DAP)'),
        ('DPU', 'Delivered at Place Unloaded (DPU)'),
        ('DDP', 'Delivered Duty Paid (DDP)'),
    ]
    
    # Context
    customer_id = serializers.PrimaryKeyRelatedField(
        queryset=Company.objects.filter(company_type='CUSTOMER'),
        source='customer',
        help_text="UUID of the customer company"
    )
    
    # Route
    origin = serializers.CharField(max_length=5, help_text="IATA Airport Code (e.g. POM) or Zone ID")
    destination = serializers.CharField(max_length=5, help_text="IATA Airport Code (e.g. BNE) or Zone ID")
    
    # Service
    service_type = serializers.ChoiceField(choices=SERVICE_TYPE_CHOICES)
    incoterms = serializers.ChoiceField(choices=INCOTERMS_CHOICES, required=False, allow_null=True)
    service_scope = serializers.ChoiceField(
        choices=['A2A', 'A2D', 'D2A', 'D2D', 'P2P'],
        default='A2A',
        help_text="Service Scope (e.g. A2A=Airport-to-Airport)"
    )
    
    # Cargo
    cargo_details = CargoDetailsSerializer()
    
    # Optional overrides
    quote_date = serializers.DateField(required=False, help_text="Defaults to today")
    
    def validate(self, data):
        """
        Cross-field validation.
        """
        service_type = data.get('service_type')
        origin = data.get('origin')
        destination = data.get('destination')
        
        # Validations for specific service types could go here.
        # e.g. If DOMESTIC, ensure origin/dest are within PNG (logic might be in engine though)
        
        return data


# =============================================================================
# V4 SELL RATE SERIALIZERS
# =============================================================================

from .models import ExportSellRate, ImportSellRate, DomesticSellRate


class ExportSellRateSerializer(serializers.ModelSerializer):
    """Serializer for Export Sell Rates."""
    product_code_code = serializers.CharField(source='product_code.code', read_only=True)
    product_code_description = serializers.CharField(source='product_code.description', read_only=True)
    
    class Meta:
        model = ExportSellRate
        fields = [
            'id', 'product_code', 'product_code_code', 'product_code_description',
            'origin_airport', 'destination_airport', 'currency',
            'rate_per_kg', 'rate_per_shipment', 'min_charge', 'max_charge',
            'percent_rate', 'weight_breaks', 'is_additive',
            'valid_from', 'valid_until', 'created_at', 'updated_at'
        ]


class ImportSellRateSerializer(serializers.ModelSerializer):
    """Serializer for Import Sell Rates."""
    product_code_code = serializers.CharField(source='product_code.code', read_only=True)
    product_code_description = serializers.CharField(source='product_code.description', read_only=True)
    
    class Meta:
        model = ImportSellRate
        fields = [
            'id', 'product_code', 'product_code_code', 'product_code_description',
            'origin_airport', 'destination_airport', 'currency',
            'rate_per_kg', 'rate_per_shipment', 'min_charge', 'max_charge',
            'percent_rate', 'weight_breaks', 'is_additive',
            'valid_from', 'valid_until', 'created_at', 'updated_at'
        ]


class DomesticSellRateSerializer(serializers.ModelSerializer):
    """Serializer for Domestic Sell Rates."""
    product_code_code = serializers.CharField(source='product_code.code', read_only=True)
    product_code_description = serializers.CharField(source='product_code.description', read_only=True)
    
    class Meta:
        model = DomesticSellRate
        fields = [
            'id', 'product_code', 'product_code_code', 'product_code_description',
            'origin_zone', 'destination_zone', 'currency',
            'rate_per_kg', 'rate_per_shipment', 'min_charge', 'max_charge',
            'percent_rate', 'weight_breaks', 'is_additive',
            'valid_from', 'valid_until', 'created_at', 'updated_at'
        ]


# =============================================================================
# LOCAL RATE SERIALIZERS (One Commercial Truth)
# =============================================================================

from .models import LocalSellRate, LocalCOGSRate


class LocalSellRateSerializer(serializers.ModelSerializer):
    """Serializer for Local Sell Rates (centralized origin/destination charges)."""
    product_code_code = serializers.CharField(source='product_code.code', read_only=True)
    product_code_description = serializers.CharField(source='product_code.description', read_only=True)
    
    class Meta:
        model = LocalSellRate
        fields = [
            'id', 'product_code', 'product_code_code', 'product_code_description',
            'location', 'direction', 'payment_term', 'currency',
            'rate_type', 'amount', 'is_additive', 'additive_flat_amount',
            'min_charge', 'max_charge', 'weight_breaks',
            'percent_of_product_code',
            'valid_from', 'valid_until', 'created_at', 'updated_at'
        ]


class LocalCOGSRateSerializer(serializers.ModelSerializer):
    """Serializer for Local COGS Rates (centralized origin/destination costs)."""
    product_code_code = serializers.CharField(source='product_code.code', read_only=True)
    product_code_description = serializers.CharField(source='product_code.description', read_only=True)
    agent_name = serializers.CharField(source='agent.name', read_only=True, allow_null=True)
    carrier_name = serializers.CharField(source='carrier.name', read_only=True, allow_null=True)
    
    class Meta:
        model = LocalCOGSRate
        fields = [
            'id', 'product_code', 'product_code_code', 'product_code_description',
            'location', 'direction', 'agent', 'agent_name', 'carrier', 'carrier_name',
            'currency', 'rate_type', 'amount', 'is_additive', 'additive_flat_amount',
            'min_charge', 'max_charge', 'weight_breaks',
            'percent_of_product_code',
            'valid_from', 'valid_until', 'created_at', 'updated_at'
        ]
