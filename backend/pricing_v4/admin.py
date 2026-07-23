# backend/pricing_v4/admin.py
"""
Admin configuration for pricing_v4 models.
"""

from django.contrib import admin
from django.db.models import Q
from .models import (
    Carrier,
    Agent,
    ProductCode,
    ChargeAlias,
    ExportCOGS,
    ExportSellRate,
    ImportCOGS,
    ImportSellRate,
    DomesticCOGS,
    DomesticSellRate,
    CustomerDiscount,
    CommodityChargeRule,
    ProductCodeContextRule,
    ProductCodeCreationRequest,
)
from .services.pricing_rate_scope import LOCAL_CATEGORIES, PricingRateScope
from .services.import_cogs_scope import ImportCOGSScope
from .services.rate_scope_transition import computed_transition_scope, scope_mismatch_label


RATE_SCOPE_LANE_Q = (
    Q(product_code__category='FREIGHT') |
    Q(product_code__code__icontains='FRT') |
    Q(product_code__code__icontains='FREIGHT') |
    Q(product_code__description__icontains='Air Freight') |
    Q(product_code__description__icontains='Linehaul') |
    Q(product_code__description__icontains='Lane Freight')
)
RATE_SCOPE_DESTINATION_Q = (
    Q(product_code__code__icontains='-DEST') |
    Q(product_code__code__icontains='DELIVERY') |
    Q(product_code__code__icontains='CARTAGE') |
    Q(product_code__description__icontains='Destination') |
    Q(product_code__description__icontains='Delivery') |
    Q(product_code__description__icontains='Cartage') |
    Q(product_code__description__icontains='Customs Clearance') |
    Q(product_code__domain='IMPORT', product_code__category__in=LOCAL_CATEGORIES)
)
RATE_SCOPE_ORIGIN_Q = (
    Q(product_code__code__icontains='-ORIGIN') |
    Q(product_code__code__icontains='PICKUP') |
    Q(product_code__description__icontains='Origin') |
    Q(product_code__description__icontains='Pickup') |
    Q(product_code__description__icontains='Pick Up') |
    Q(product_code__description__icontains='Collection') |
    Q(product_code__description__icontains='AWB') |
    Q(product_code__description__icontains='Screen') |
    Q(product_code__description__icontains='X-Ray') |
    Q(product_code__description__icontains='Build Up') |
    Q(product_code__domain='EXPORT', product_code__category__in=LOCAL_CATEGORIES)
)
RATE_SCOPE_LOCAL_Q = Q(product_code__domain='DOMESTIC', product_code__category__in=LOCAL_CATEGORIES)
RATE_SCOPE_KNOWN_Q = (
    RATE_SCOPE_LANE_Q |
    RATE_SCOPE_ORIGIN_Q |
    RATE_SCOPE_DESTINATION_Q |
    RATE_SCOPE_LOCAL_Q
)


class PricingRateScopeFilter(admin.SimpleListFilter):
    title = 'computed scope'
    parameter_name = 'computed_scope'

    def lookups(self, request, model_admin):
        return tuple((scope.value, scope.value) for scope in PricingRateScope)

    def queryset(self, request, queryset):
        value = self.value()
        if value == PricingRateScope.LANE:
            return queryset.filter(RATE_SCOPE_LANE_Q)
        if value == PricingRateScope.ORIGIN:
            return queryset.filter(RATE_SCOPE_ORIGIN_Q)
        if value == PricingRateScope.DESTINATION:
            return queryset.filter(RATE_SCOPE_DESTINATION_Q)
        if value == PricingRateScope.LOCAL:
            return queryset.filter(RATE_SCOPE_LOCAL_Q)
        if value == PricingRateScope.UNKNOWN:
            return queryset.exclude(RATE_SCOPE_KNOWN_Q)
        return queryset


def computed_rate_scope(obj):
    return computed_transition_scope(obj)


computed_rate_scope.short_description = 'Computed Scope'


def scope_warning(obj):
    return scope_mismatch_label(obj)


scope_warning.short_description = 'Scope Warning'


IMPORT_COGS_ORIGIN_SCOPE_Q = (
    Q(product_code__code__icontains='-ORIGIN') |
    Q(product_code__code__icontains='IMP-PICKUP') |
    Q(product_code__code__icontains='IMP-FSC-PICKUP') |
    Q(product_code__description__icontains='Origin') |
    Q(product_code__description__icontains='Pickup') |
    Q(product_code__description__icontains='AWB') |
    Q(product_code__description__icontains='X-Ray') |
    Q(product_code__description__icontains='Screen')
)
IMPORT_COGS_DESTINATION_SCOPE_Q = (
    Q(product_code__code__icontains='-DEST') |
    Q(product_code__code__icontains='IMP-CLEAR') |
    Q(product_code__code__icontains='IMP-CARTAGE') |
    Q(product_code__code__icontains='IMP-FSC-CARTAGE') |
    Q(product_code__description__icontains='Destination') |
    Q(product_code__description__icontains='Customs Clearance') |
    Q(product_code__description__icontains='Cartage') |
    Q(product_code__description__icontains='Delivery') |
    Q(product_code__description__icontains='Handling') |
    Q(product_code__description__icontains='Terminal')
)
IMPORT_COGS_LANE_SCOPE_Q = (
    Q(product_code__category='FREIGHT') |
    Q(product_code__code__icontains='IMP-FRT') |
    Q(product_code__code__icontains='FRT-AIR') |
    Q(product_code__description__icontains='Import Air Freight') |
    Q(product_code__description__icontains='Linehaul') |
    Q(product_code__description__icontains='Lane Freight')
)
IMPORT_COGS_KNOWN_SCOPE_Q = (
    IMPORT_COGS_ORIGIN_SCOPE_Q |
    IMPORT_COGS_DESTINATION_SCOPE_Q |
    IMPORT_COGS_LANE_SCOPE_Q
)


class ImportCOGSScopeFilter(admin.SimpleListFilter):
    title = 'computed scope'
    parameter_name = 'computed_scope'

    def lookups(self, request, model_admin):
        return tuple((scope.value, scope.value) for scope in ImportCOGSScope)

    def queryset(self, request, queryset):
        value = self.value()
        if value == ImportCOGSScope.ORIGIN:
            return queryset.filter(IMPORT_COGS_ORIGIN_SCOPE_Q)
        if value == ImportCOGSScope.DESTINATION:
            return queryset.filter(IMPORT_COGS_DESTINATION_SCOPE_Q)
        if value == ImportCOGSScope.LANE:
            return queryset.filter(IMPORT_COGS_LANE_SCOPE_Q)
        if value == ImportCOGSScope.UNKNOWN:
            return queryset.exclude(IMPORT_COGS_KNOWN_SCOPE_Q)
        return queryset


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
    list_display = ['id', 'code', 'description', 'domain', 'category', 'default_unit', 'is_active', 'retired_at', 'is_gst_applicable', 'gst_treatment']
    list_filter = ['domain', 'category', 'default_unit', 'is_active', 'retired_at', 'is_gst_applicable', 'gst_treatment']
    search_fields = ['id', 'code', 'description']
    ordering = ['id']
    
    fieldsets = (
        ('Identity', {
            'fields': ('id', 'code', 'description', 'domain', 'category')
        }),
        ('Lifecycle', {
            'fields': ('is_active', 'retired_at', 'replacement_product_code')
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


@admin.register(ProductCodeContextRule)
class ProductCodeContextRuleAdmin(admin.ModelAdmin):
    list_display = [
        'canonical_charge_type',
        'product_code',
        'product_code_domain',
        'leg_role',
        'commercial_position',
        'transport_mode',
        'operational_location',
        'calculation_basis',
        'service_scope',
        'priority',
        'is_active',
        'review_status',
        'source',
        'updated_at',
    ]
    list_filter = [
        'product_code_domain',
        'leg_role',
        'commercial_position',
        'transport_mode',
        'is_active',
        'review_status',
        'source',
    ]
    search_fields = [
        'canonical_charge_type__code',
        'canonical_charge_type__name',
        'product_code__code',
        'product_code__description',
        'notes',
    ]
    list_select_related = ['canonical_charge_type', 'product_code']
    autocomplete_fields = ['product_code']
    ordering = ['priority', 'canonical_charge_type__code', 'id']
    readonly_fields = ['created_at', 'updated_at']

    fieldsets = (
        ('Rule Identity', {
            'fields': ('canonical_charge_type', 'product_code', 'product_code_domain')
        }),
        ('Trusted Leg Context', {
            'fields': ('leg_role', 'commercial_position', 'transport_mode')
        }),
        ('Optional Match Dimensions', {
            'fields': ('operational_location', 'calculation_basis', 'service_scope')
        }),
        ('Lifecycle and Review', {
            'fields': ('priority', 'is_active', 'review_status', 'source')
        }),
        ('Notes and Audit', {
            'fields': ('notes', 'created_by', 'updated_by', 'created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )


@admin.register(ChargeAlias)
class ChargeAliasAdmin(admin.ModelAdmin):
    list_display = [
        'alias_text',
        'normalized_alias_text',
        'match_type',
        'mode_scope',
        'direction_scope',
        'product_code',
        'priority',
        'is_active',
        'review_status',
        'alias_source',
    ]
    list_filter = [
        'is_active',
        'match_type',
        'mode_scope',
        'direction_scope',
        'product_code',
        'review_status',
        'alias_source',
    ]
    search_fields = [
        'alias_text',
        'normalized_alias_text',
        'product_code__code',
        'product_code__description',
        'notes',
    ]
    ordering = ['priority', 'normalized_alias_text', 'id']
    autocomplete_fields = ['product_code']
    list_select_related = ['product_code']

    fieldsets = (
        ('Alias Matching', {
            'fields': (
                'alias_text',
                'normalized_alias_text',
                'match_type',
                'mode_scope',
                'direction_scope',
                'product_code',
                'priority',
            )
        }),
        ('Operational Review', {
            'fields': ('is_active', 'review_status', 'alias_source'),
            'description': 'Keep risky aliases inactive until they are explicitly reviewed and approved.',
        }),
        ('Notes', {
            'fields': ('notes',),
            'classes': ('collapse',),
        }),
    )


@admin.register(ExportCOGS)
class ExportCOGSAdmin(admin.ModelAdmin):
    list_display = ['product_code', 'scope', computed_rate_scope, scope_warning, 'origin_airport', 'destination_airport', 'currency', 'get_counterparty', 'valid_from', 'valid_until']
    list_filter = ['scope', PricingRateScopeFilter, 'origin_airport', 'destination_airport', 'currency', 'carrier', 'agent']
    list_select_related = ['product_code', 'carrier', 'agent']
    search_fields = ['product_code__code']
    ordering = ['product_code', 'origin_airport', 'destination_airport']
    
    def get_counterparty(self, obj):
        return obj.carrier or obj.agent
    get_counterparty.short_description = 'Counterparty'


@admin.register(ExportSellRate)
class ExportSellRateAdmin(admin.ModelAdmin):
    list_display = ['product_code', 'scope', computed_rate_scope, scope_warning, 'origin_airport', 'destination_airport', 'currency', 'valid_from', 'valid_until']
    list_filter = ['scope', PricingRateScopeFilter, 'origin_airport', 'destination_airport', 'currency']
    list_select_related = ['product_code']
    search_fields = ['product_code__code']
    ordering = ['product_code', 'origin_airport', 'destination_airport']


@admin.register(ImportCOGS)
class ImportCOGSAdmin(admin.ModelAdmin):
    list_display = ['product_code', 'scope', 'computed_scope', scope_warning, 'origin_airport', 'destination_airport', 'currency', 'get_counterparty', 'valid_from', 'valid_until']
    list_filter = ['scope', ImportCOGSScopeFilter, 'origin_airport', 'destination_airport', 'currency', 'carrier', 'agent']
    list_select_related = ['product_code', 'carrier', 'agent']
    search_fields = ['product_code__code']
    ordering = ['product_code', 'origin_airport', 'destination_airport']
    
    def get_counterparty(self, obj):
        return obj.carrier or obj.agent
    get_counterparty.short_description = 'Counterparty'

    def computed_scope(self, obj):
        return computed_transition_scope(obj)
    computed_scope.short_description = 'Computed Scope'


@admin.register(ImportSellRate)
class ImportSellRateAdmin(admin.ModelAdmin):
    list_display = ['product_code', 'scope', computed_rate_scope, scope_warning, 'origin_airport', 'destination_airport', 'currency', 'architecture_role', 'valid_from', 'valid_until']
    list_filter = ['scope', PricingRateScopeFilter, 'origin_airport', 'destination_airport', 'currency']
    list_select_related = ['product_code']
    search_fields = ['product_code__code']
    ordering = ['product_code', 'origin_airport', 'destination_airport']

    def architecture_role(self, _obj):
        return 'Transitional lane sell only'
    architecture_role.short_description = 'Architecture Role'


@admin.register(DomesticCOGS)
class DomesticCOGSAdmin(admin.ModelAdmin):
    list_display = ['product_code', 'scope', computed_rate_scope, scope_warning, 'origin_zone', 'destination_zone', 'currency', 'agent', 'valid_from', 'valid_until']
    list_filter = ['scope', PricingRateScopeFilter, 'origin_zone', 'destination_zone', 'agent']
    list_select_related = ['product_code', 'agent', 'carrier']
    search_fields = ['product_code__code']
    ordering = ['product_code', 'origin_zone', 'destination_zone']


@admin.register(DomesticSellRate)
class DomesticSellRateAdmin(admin.ModelAdmin):
    list_display = ['product_code', 'scope', computed_rate_scope, scope_warning, 'origin_zone', 'destination_zone', 'currency', 'architecture_role', 'valid_from', 'valid_until']
    list_filter = ['scope', PricingRateScopeFilter, 'origin_zone', 'destination_zone']
    list_select_related = ['product_code']
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
    list_display = ['product_code', 'scope', computed_rate_scope, scope_warning, 'location', 'direction', 'payment_term', 'currency', 'architecture_role', 'rate_type', 'amount', 'valid_from', 'valid_until']
    list_filter = ['scope', PricingRateScopeFilter, 'location', 'direction', 'payment_term', 'currency', 'rate_type']
    list_select_related = ['product_code', 'percent_of_product_code']
    search_fields = ['product_code__code', 'location']
    ordering = ['location', 'direction', 'product_code']
    autocomplete_fields = ['product_code', 'percent_of_product_code']
    
    fieldsets = (
        ('Scope', {
            'fields': ('product_code', 'scope', 'location', 'direction', 'payment_term')
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
    list_display = ['product_code', 'scope', computed_rate_scope, scope_warning, 'location', 'direction', 'get_counterparty', 'currency', 'architecture_role', 'rate_type', 'amount', 'valid_from', 'valid_until']
    list_filter = ['scope', PricingRateScopeFilter, 'location', 'direction', 'currency', 'rate_type', 'agent', 'carrier']
    list_select_related = ['product_code', 'agent', 'carrier', 'percent_of_product_code']
    search_fields = ['product_code__code', 'location']
    ordering = ['location', 'direction', 'product_code']
    autocomplete_fields = ['product_code', 'agent', 'carrier', 'percent_of_product_code']
    
    def get_counterparty(self, obj):
        return obj.carrier or obj.agent
    get_counterparty.short_description = 'Counterparty'
    
    fieldsets = (
        ('Scope', {
            'fields': ('product_code', 'scope', 'location', 'direction')
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


@admin.register(ProductCodeCreationRequest)
class ProductCodeCreationRequestAdmin(admin.ModelAdmin):
    list_display = [
        'source_label',
        'suggested_name',
        'suggested_bucket',
        'suggested_basis',
        'status',
        'created_by',
        'created_at',
    ]
    list_filter = ['status', 'suggested_bucket', 'suggested_basis']
    search_fields = ['source_label', 'suggested_name', 'suggested_reason', 'rejection_reason']
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['-created_at']

