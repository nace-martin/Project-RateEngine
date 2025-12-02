# backend/services/admin.py

from django.contrib import admin
from .models import (
    ServiceCode,
    ServiceComponent,
    ServiceRule,
    ServiceRuleComponent,
)

@admin.register(ServiceCode)
class ServiceCodeAdmin(admin.ModelAdmin):
    list_display = (
        'code', 'description', 'location_type', 'service_category',
        'pricing_method', 'is_taxable', 'gl_code', 'is_active'
    )
    list_filter = ('location_type', 'service_category', 'pricing_method', 'is_taxable', 'is_active')
    search_fields = ('code', 'description', 'gl_code')
    ordering = ('code',)
    list_editable = ('is_active', 'is_taxable')
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('code', 'description', 'is_active')
        }),
        ('Classification', {
            'fields': ('location_type', 'service_category', 'pricing_method')
        }),
        ('Accounting & Tax', {
            'fields': ('is_taxable', 'gl_code', 'revenue_account', 'cost_account')
        }),
        ('Validation Rules', {
            'fields': ('requires_weight', 'requires_dimensions', 'is_mandatory')
        }),
        ('Metadata', {
            'fields': ('notes', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
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
