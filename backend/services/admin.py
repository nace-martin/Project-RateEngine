# backend/services/admin.py

from django.contrib import admin
from .models import ServiceComponent, IncotermRule

@admin.register(ServiceComponent)
class ServiceComponentAdmin(admin.ModelAdmin):
    # Add cost_type and cost_source to list_display and list_filter
    list_display = (
        'code', 'description', 'mode', 'leg', 'category', 
        'cost_type', 'cost_source', 'cost_currency_type', # New fields
        'unit', 'base_pgk_cost', 'is_active'
    )
    list_filter = ('mode', 'leg', 'category', 'cost_type', 'cost_source', 'is_active') # New fields
    search_fields = ('code', 'description')
    ordering = ('mode', 'leg', 'code')
    # Make fields editable in list view for quick adjustments
    list_editable = ('is_active', 'cost_type', 'cost_source', 'cost_currency_type', 'base_pgk_cost')

@admin.register(IncotermRule)
class IncotermRuleAdmin(admin.ModelAdmin):
    list_display = ('mode', 'shipment_type', 'incoterm', 'is_active')
    list_filter = ('mode', 'shipment_type', 'is_active')
    search_fields = ('incoterm', 'description')
    ordering = ('mode', 'shipment_type', 'incoterm')
    # Use filter_horizontal for easier selection of many components
    filter_horizontal = ('service_components',)