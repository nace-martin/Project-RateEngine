# backend/pricing_v4/admin.py
"""
Admin configuration for pricing_v4 models.
"""

from django.contrib import admin
from .models import (
    Carrier,
    Agent,
    ProductCode,
    ExportCOGS,
    ExportSellRate,
    ImportCOGS,
    ImportSellRate,
    DomesticCOGS,
    DomesticSellRate,
    CustomerDiscount,
    CommodityChargeRule,
)


@admin.register(Carrier)
class CarrierAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'carrier_type']
    list_filter = ['carrier_type']
    search_fields = ['code', 'name']
    ordering = ['code']


@admin.register(Agent)
class AgentAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'country_code', 'agent_type']
    list_filter = ['country_code', 'agent_type']
    search_fields = ['code', 'name']
    ordering = ['code']


@admin.register(ProductCode)
class ProductCodeAdmin(admin.ModelAdmin):
    list_display = ['id', 'code', 'description', 'domain', 'category', 'default_unit', 'is_gst_applicable', 'gst_treatment']
    list_filter = ['domain', 'category', 'default_unit', 'is_gst_applicable', 'gst_treatment']
    search_fields = ['id', 'code', 'description']
    ordering = ['id']
    
    fieldsets = (
        ('Identity', {
            'fields': ('id', 'code', 'description', 'domain', 'category')
        }),
        ('Tax Configuration', {
            'fields': ('is_gst_applicable', 'gst_rate', 'gst_treatment')
        }),
        ('Accounting', {
            'fields': ('gl_revenue_code', 'gl_cost_code')
        }),
        ('Defaults', {
            'fields': ('default_unit', 'percent_of_product_code')
        }),
    )


@admin.register(ExportCOGS)
class ExportCOGSAdmin(admin.ModelAdmin):
    list_display = ['product_code', 'origin_airport', 'destination_airport', 'currency', 'get_counterparty', 'valid_from', 'valid_until']
    list_filter = ['origin_airport', 'destination_airport', 'currency', 'carrier', 'agent']
    search_fields = ['product_code__code']
    ordering = ['product_code', 'origin_airport', 'destination_airport']
    
    def get_counterparty(self, obj):
        return obj.carrier or obj.agent
    get_counterparty.short_description = 'Counterparty'


@admin.register(ExportSellRate)
class ExportSellRateAdmin(admin.ModelAdmin):
    list_display = ['product_code', 'origin_airport', 'destination_airport', 'currency', 'valid_from', 'valid_until']
    list_filter = ['origin_airport', 'destination_airport', 'currency']
    search_fields = ['product_code__code']
    ordering = ['product_code', 'origin_airport', 'destination_airport']


@admin.register(ImportCOGS)
class ImportCOGSAdmin(admin.ModelAdmin):
    list_display = ['product_code', 'origin_airport', 'destination_airport', 'currency', 'get_counterparty', 'valid_from', 'valid_until']
    list_filter = ['origin_airport', 'destination_airport', 'currency', 'carrier', 'agent']
    search_fields = ['product_code__code']
    ordering = ['product_code', 'origin_airport', 'destination_airport']
    
    def get_counterparty(self, obj):
        return obj.carrier or obj.agent
    get_counterparty.short_description = 'Counterparty'


@admin.register(ImportSellRate)
class ImportSellRateAdmin(admin.ModelAdmin):
    list_display = ['product_code', 'origin_airport', 'destination_airport', 'currency', 'architecture_role', 'valid_from', 'valid_until']
    list_filter = ['origin_airport', 'destination_airport', 'currency']
    search_fields = ['product_code__code']
    ordering = ['product_code', 'origin_airport', 'destination_airport']

    def architecture_role(self, _obj):
        return 'Transitional lane sell only'
    architecture_role.short_description = 'Architecture Role'


@admin.register(DomesticCOGS)
class DomesticCOGSAdmin(admin.ModelAdmin):
    list_display = ['product_code', 'origin_zone', 'destination_zone', 'currency', 'agent', 'valid_from', 'valid_until']
    list_filter = ['origin_zone', 'destination_zone', 'agent']
    search_fields = ['product_code__code']
    ordering = ['product_code', 'origin_zone', 'destination_zone']


@admin.register(DomesticSellRate)
class DomesticSellRateAdmin(admin.ModelAdmin):
    list_display = ['product_code', 'origin_zone', 'destination_zone', 'currency', 'architecture_role', 'valid_from', 'valid_until']
    list_filter = ['origin_zone', 'destination_zone']
    search_fields = ['product_code__code']
    ordering = ['product_code', 'origin_zone', 'destination_zone']

    def architecture_role(self, _obj):
        return 'Primary domestic sell table'
    architecture_role.short_description = 'Architecture Role'


@admin.register(CustomerDiscount)
class CustomerDiscountAdmin(admin.ModelAdmin):
    list_display = ['customer', 'product_code', 'discount_type', 'discount_value', 'currency', 'valid_until', 'created_at']
    list_filter = ['discount_type', 'valid_until', 'product_code__domain', 'currency']
    search_fields = ['customer__name', 'product_code__code', 'product_code__description', 'notes']
    autocomplete_fields = ['customer', 'product_code']
    ordering = ['customer', 'product_code']
    
    fieldsets = (
        ('Customer & Product', {
            'fields': ('customer', 'product_code')
        }),
        ('Discount Configuration', {
            'fields': ('discount_type', 'discount_value', 'currency'),
            'description': 'For PERCENTAGE: value is percent (e.g., 5.00 = 5%). '
                          'For FLAT_AMOUNT: value is amount to subtract. '
                          'For RATE_REDUCTION: value is new rate per kg. '
                          'For FIXED_CHARGE: value is total fixed charge.'
        }),
        ('Validity', {
            'fields': ('valid_from', 'valid_until')
        }),
        ('Notes', {
            'fields': ('notes',),
            'classes': ('collapse',)
        }),
        ('Audit', {
            'fields': ('created_at', 'updated_at', 'created_by'),
            'classes': ('collapse',)
        }),
    )
    readonly_fields = ['created_at', 'updated_at']


@admin.register(CommodityChargeRule)
class CommodityChargeRuleAdmin(admin.ModelAdmin):
    list_display = [
        'shipment_type',
        'service_scope',
        'commodity_code',
        'product_code',
        'leg',
        'trigger_mode',
        'origin_code',
        'destination_code',
        'payment_term',
        'is_active',
        'effective_from',
        'effective_to',
    ]
    list_filter = [
        'shipment_type',
        'service_scope',
        'commodity_code',
        'leg',
        'trigger_mode',
        'payment_term',
        'is_active',
    ]
    search_fields = ['product_code__code', 'product_code__description', 'origin_code', 'destination_code', 'notes']
    ordering = ['shipment_type', 'service_scope', 'commodity_code', 'product_code']
    autocomplete_fields = ['product_code']

    fieldsets = (
        ('Applicability', {
            'fields': ('shipment_type', 'service_scope', 'commodity_code', 'leg', 'trigger_mode')
        }),
        ('Product Mapping', {
            'fields': ('product_code',)
        }),
        ('Optional Filters', {
            'fields': ('origin_code', 'destination_code', 'payment_term', 'is_active')
        }),
        ('Validity', {
            'fields': ('effective_from', 'effective_to')
        }),
        ('Notes', {
            'fields': ('notes',),
            'classes': ('collapse',)
        }),
    )

# =============================================================================
# LOCAL RATE ADMINS (One Commercial Truth)
# =============================================================================

from .models import LocalSellRate, LocalCOGSRate


@admin.register(LocalSellRate)
class LocalSellRateAdmin(admin.ModelAdmin):
    list_display = ['product_code', 'location', 'direction', 'payment_term', 'currency', 'architecture_role', 'rate_type', 'amount', 'valid_from', 'valid_until']
    list_filter = ['location', 'direction', 'payment_term', 'currency', 'rate_type']
    search_fields = ['product_code__code', 'location']
    ordering = ['location', 'direction', 'product_code']
    autocomplete_fields = ['product_code', 'percent_of_product_code']
    
    fieldsets = (
        ('Scope', {
            'fields': ('product_code', 'location', 'direction', 'payment_term')
        }),
        ('Rate Configuration', {
            'fields': ('currency', 'rate_type', 'amount', 'is_additive', 'additive_flat_amount', 'min_charge', 'max_charge', 'weight_breaks')
        }),
        ('Percentage (if applicable)', {
            'fields': ('percent_of_product_code',),
            'classes': ('collapse',)
        }),
        ('Validity', {
            'fields': ('valid_from', 'valid_until')
        }),
    )

    def architecture_role(self, obj):
        if obj.direction == 'IMPORT':
            return 'Primary import destination sell'
        if obj.direction == 'EXPORT':
            return 'Primary export local sell'
        return 'Primary local sell'
    architecture_role.short_description = 'Architecture Role'


@admin.register(LocalCOGSRate)
class LocalCOGSRateAdmin(admin.ModelAdmin):
    list_display = ['product_code', 'location', 'direction', 'get_counterparty', 'currency', 'architecture_role', 'rate_type', 'amount', 'valid_from', 'valid_until']
    list_filter = ['location', 'direction', 'currency', 'rate_type', 'agent', 'carrier']
    search_fields = ['product_code__code', 'location']
    ordering = ['location', 'direction', 'product_code']
    autocomplete_fields = ['product_code', 'agent', 'carrier', 'percent_of_product_code']
    
    def get_counterparty(self, obj):
        return obj.carrier or obj.agent
    get_counterparty.short_description = 'Counterparty'
    
    fieldsets = (
        ('Scope', {
            'fields': ('product_code', 'location', 'direction')
        }),
        ('Counterparty', {
            'fields': ('agent', 'carrier'),
            'description': 'Select EITHER agent OR carrier, not both.'
        }),
        ('Rate Configuration', {
            'fields': ('currency', 'rate_type', 'amount', 'is_additive', 'additive_flat_amount', 'min_charge', 'max_charge', 'weight_breaks')
        }),
        ('Percentage (if applicable)', {
            'fields': ('percent_of_product_code',),
            'classes': ('collapse',)
        }),
        ('Validity', {
            'fields': ('valid_from', 'valid_until')
        }),
    )

    def architecture_role(self, obj):
        if obj.direction == 'IMPORT':
            return 'Primary import destination buy'
        if obj.direction == 'EXPORT':
            return 'Primary export local buy'
        return 'Primary local buy'
    architecture_role.short_description = 'Architecture Role'
