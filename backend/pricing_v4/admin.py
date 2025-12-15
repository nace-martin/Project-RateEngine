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
    list_display = ['id', 'code', 'description', 'domain', 'category', 'default_unit', 'is_gst_applicable']
    list_filter = ['domain', 'category', 'default_unit', 'is_gst_applicable']
    search_fields = ['id', 'code', 'description']
    ordering = ['id']
    
    fieldsets = (
        ('Identity', {
            'fields': ('id', 'code', 'description', 'domain', 'category')
        }),
        ('Tax Configuration', {
            'fields': ('is_gst_applicable', 'gst_rate')
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
    list_display = ['product_code', 'origin_airport', 'destination_airport', 'currency', 'valid_from', 'valid_until']
    list_filter = ['origin_airport', 'destination_airport', 'currency']
    search_fields = ['product_code__code']
    ordering = ['product_code', 'origin_airport', 'destination_airport']


@admin.register(DomesticCOGS)
class DomesticCOGSAdmin(admin.ModelAdmin):
    list_display = ['product_code', 'origin_zone', 'destination_zone', 'currency', 'agent', 'valid_from', 'valid_until']
    list_filter = ['origin_zone', 'destination_zone', 'agent']
    search_fields = ['product_code__code']
    ordering = ['product_code', 'origin_zone', 'destination_zone']


@admin.register(DomesticSellRate)
class DomesticSellRateAdmin(admin.ModelAdmin):
    list_display = ['product_code', 'origin_zone', 'destination_zone', 'currency', 'valid_from', 'valid_until']
    list_filter = ['origin_zone', 'destination_zone']
    search_fields = ['product_code__code']
    ordering = ['product_code', 'origin_zone', 'destination_zone']
