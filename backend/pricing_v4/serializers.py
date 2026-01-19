from rest_framework import serializers
from .models import (
    ProductCode, DomesticCOGS, ExportCOGS, ImportCOGS,
    ComponentMargin, CustomerDiscount, Surcharge
)
from parties.models import Company

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
