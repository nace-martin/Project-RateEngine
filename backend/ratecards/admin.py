# backend/ratecards/admin.py

from django.contrib import admin

from .models import PartnerRateCard, PartnerRateLane, PartnerRate


class LegacyReferenceAdmin(admin.ModelAdmin):
    actions = None

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(PartnerRateCard)
class PartnerRateCardAdmin(LegacyReferenceAdmin):
    list_display = (
        'name',
        'supplier',
        'currency_code',
        'rate_type',
        'valid_from',
        'valid_until',
        'legacy_status',
    )
    list_filter = ('supplier', 'currency_code', 'rate_type')
    search_fields = ('name', 'supplier__name')
    readonly_fields = [field.name for field in PartnerRateCard._meta.fields]

    def legacy_status(self, _obj):
        return 'Legacy V3 reference only'
    legacy_status.short_description = 'Status'


@admin.register(PartnerRateLane)
class PartnerRateLaneAdmin(LegacyReferenceAdmin):
    list_display = (
        'rate_card',
        'direction',
        'payment_term',
        'origin_airport',
        'destination_airport',
        'legacy_status',
    )
    list_filter = ('direction', 'payment_term', 'mode')
    search_fields = ('rate_card__name', 'origin_airport__iata_code', 'destination_airport__iata_code')
    readonly_fields = [field.name for field in PartnerRateLane._meta.fields]

    def legacy_status(self, _obj):
        return 'Superseded by pricing_v4'
    legacy_status.short_description = 'Status'


@admin.register(PartnerRate)
class PartnerRateAdmin(LegacyReferenceAdmin):
    list_display = (
        'lane',
        'service_component',
        'unit',
        'rate_per_kg_fcy',
        'rate_per_shipment_fcy',
        'legacy_status',
    )
    list_filter = ('unit',)
    search_fields = ('lane__rate_card__name', 'service_component__code')
    readonly_fields = [field.name for field in PartnerRate._meta.fields]

    def legacy_status(self, _obj):
        return 'Legacy V3 reference only'
    legacy_status.short_description = 'Status'
