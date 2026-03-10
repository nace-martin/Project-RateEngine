# backend/ratecards/admin.py

from django.contrib import admin
from .models import (
    PartnerRateCard, PartnerRateLane, PartnerRate, A2DDAPRateArchive
)


class PartnerRateInline(admin.TabularInline):
    model = PartnerRate
    extra = 1
    fields = (
        'service_component',
        'unit',
        'rate_per_kg_fcy',
        'rate_per_shipment_fcy',
        'min_charge_fcy',
    )


class PartnerRateLaneAdmin(admin.ModelAdmin):
    model = PartnerRateLane
    list_display = (
        'id',
        'rate_card',
        'mode',
        'shipment_type',
        'origin_airport',
        'destination_airport',
    )
    list_filter = ('rate_card', 'mode', 'shipment_type')
    inlines = [PartnerRateInline]
    fields = ('rate_card', 'mode', 'shipment_type', 'origin_airport', 'destination_airport')


class PartnerRateLaneInline(admin.TabularInline):
    model = PartnerRateLane
    fields = ('mode', 'shipment_type', 'origin_airport', 'destination_airport')
    extra = 1


class PartnerRateCardAdmin(admin.ModelAdmin):
    model = PartnerRateCard
    list_display = ('name', 'supplier', 'currency_code', 'valid_from', 'valid_until')
    list_filter = ('supplier', 'currency_code')
    inlines = [PartnerRateLaneInline]


admin.site.register(PartnerRateCard, PartnerRateCardAdmin)
admin.site.register(PartnerRateLane, PartnerRateLaneAdmin)
admin.site.register(PartnerRate)


@admin.register(A2DDAPRateArchive)
class A2DDAPRateArchiveAdmin(admin.ModelAdmin):
    list_display = (
        'source_rate_id',
        'payment_term',
        'currency',
        'service_component_code',
        'rate',
        'archived_at',
    )
    list_filter = ('payment_term', 'currency', 'is_active', 'archived_at')
    search_fields = ('source_rate_id', 'service_component_code', 'percent_of_component_code')
    ordering = ('-archived_at', '-source_rate_id')
    readonly_fields = [field.name for field in A2DDAPRateArchive._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
