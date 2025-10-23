# backend/ratecards/admin.py

from django.contrib import admin
from .models import (
    RateCard, RateCardBreak,
    PartnerRateCard, PartnerRateLane, PartnerRate
)

@admin.register(RateCard)
class RateCardAdmin(admin.ModelAdmin):
    list_display = ('origin_airport', 'destination_airport', 'carrier', 'effective_from', 'effective_to', 'is_active')
    list_filter = ('carrier', 'is_active')
    search_fields = ('origin_airport__code', 'destination_airport__code', 'carrier')
    ordering = ('origin_airport', 'destination_airport', 'carrier')

@admin.register(RateCardBreak)
class RateCardBreakAdmin(admin.ModelAdmin):
    list_display = ('rate_card', 'weight_break_kg', 'rate_per_kg')
    list_filter = ('rate_card',)
    search_fields = ('rate_card__origin_airport__code', 'rate_card__destination_airport__code')
    ordering = ('rate_card', 'weight_break_kg')


# New Admin classes for Partner Rates
class PartnerRateInline(admin.TabularInline):
    model = PartnerRate
    extra = 1

class PartnerRateLaneAdmin(admin.ModelAdmin):
    model = PartnerRateLane
    list_display = ('id', 'rate_card', 'origin_airport', 'destination_airport')
    list_filter = ('rate_card',)
    inlines = [PartnerRateInline]

class PartnerRateLaneInline(admin.TabularInline):
    model = PartnerRateLane
    extra = 1

class PartnerRateCardAdmin(admin.ModelAdmin):
    model = PartnerRateCard
    list_display = ('name', 'supplier', 'currency_code', 'mode', 'valid_from', 'valid_until')
    list_filter = ('supplier', 'mode', 'currency_code')
    inlines = [PartnerRateLaneInline]

# Register the new models
admin.site.register(PartnerRateCard, PartnerRateCardAdmin)
admin.site.register(PartnerRateLane, PartnerRateLaneAdmin)
admin.site.register(PartnerRate) # Registering this directly is also useful