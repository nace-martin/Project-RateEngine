# backend/services/admin.py

from django.contrib import admin
from .models import ServiceComponent, IncotermRule

@admin.register(ServiceComponent)
class ServiceComponentAdmin(admin.ModelAdmin):
    list_display = ('code', 'description', 'mode', 'leg', 'unit', 'base_pgk_cost', 'is_active')
    list_filter = ('mode', 'leg', 'is_active')
    search_fields = ('code', 'description')
    ordering = ('mode', 'leg', 'code')

@admin.register(IncotermRule)
class IncotermRuleAdmin(admin.ModelAdmin):
    list_display = ('mode', 'shipment_type', 'incoterm', 'is_active')
    list_filter = ('mode', 'shipment_type', 'is_active')
    search_fields = ('incoterm', 'description')
    ordering = ('mode', 'shipment_type', 'incoterm')
    # Use filter_horizontal for easier selection of many components
    filter_horizontal = ('service_components',)