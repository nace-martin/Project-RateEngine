# backend/ratecards/admin.py

from django.contrib import admin
from .models import (
    PartnerRateCard, PartnerRateLane, PartnerRate
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
