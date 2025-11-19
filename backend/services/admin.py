# backend/services/admin.py

from django.contrib import admin
from .models import (
    ServiceComponent,
    ServiceRule,
    ServiceRuleComponent,
)

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

class ServiceRuleComponentInline(admin.TabularInline):
    model = ServiceRuleComponent
    extra = 1
    autocomplete_fields = ('service_component',)
    fields = ('service_component', 'sequence', 'leg_owner', 'is_mandatory', 'notes')


@admin.register(ServiceRule)
class ServiceRuleAdmin(admin.ModelAdmin):
    list_display = (
        'mode',
        'direction',
        'incoterm',
        'payment_term',
        'service_scope',
        'output_currency_type',
        'is_active',
    )
    list_filter = (
        'mode',
        'direction',
        'payment_term',
        'service_scope',
        'output_currency_type',
        'is_active',
    )
    search_fields = ('description', 'incoterm', 'notes')
    ordering = ('mode', 'direction', 'incoterm', 'payment_term', 'service_scope')
    inlines = [ServiceRuleComponentInline]
