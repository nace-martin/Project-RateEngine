# backend/ratecards/admin.py

from django.contrib import admin
from .models import (
    PartnerRateCard, PartnerRateLane, PartnerRate
)


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