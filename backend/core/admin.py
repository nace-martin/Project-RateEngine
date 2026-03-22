# backend/core/admin.py

from django.contrib import admin
from .models import (
    Currency, Country, City, Airport, FxRate,
    FxSnapshot, Policy, Surcharge,
    AircraftType, RouteLaneConstraint
)

admin.site.register(Currency)
admin.site.register(Country)
admin.site.register(City)
admin.site.register(Airport)
admin.site.register(FxRate)
admin.site.register(FxSnapshot)
admin.site.register(Policy)
admin.site.register(Surcharge)


@admin.register(AircraftType)
class AircraftTypeAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'aircraft_class', 'max_length_cm', 'max_width_cm', 'max_height_cm', 'max_piece_weight_kg', 'supports_uld']
    list_filter = ['aircraft_class', 'supports_uld']
    search_fields = ['code', 'name']
    fieldsets = (
        ('Basic Information', {
            'fields': ('code', 'name', 'aircraft_class', 'supports_uld')
        }),
        ('Cargo Door Constraints (cm)', {
            'fields': ('max_length_cm', 'max_width_cm', 'max_height_cm')
        }),
        ('Weight Constraints', {
            'fields': ('max_piece_weight_kg',)
        }),
        ('Additional Information', {
            'fields': ('notes',),
            'classes': ('collapse',)
        }),
    )


@admin.register(RouteLaneConstraint)
class RouteLaneConstraintAdmin(admin.ModelAdmin):
    list_display = ['origin', 'destination', 'service_level', 'aircraft_type', 'via_location', 'priority', 'is_active']
    list_filter = ['service_level', 'is_active', 'aircraft_type']
    search_fields = ['origin__code', 'destination__code', 'service_level']
    list_editable = ['priority', 'is_active']
    ordering = ['origin__code', 'destination__code', 'priority']
    fieldsets = (
        ('Route Information', {
            'fields': ('origin', 'destination', 'service_level', 'via_location')
        }),
        ('Aircraft & Priority', {
            'fields': ('aircraft_type', 'priority', 'is_active')
        }),
    )
