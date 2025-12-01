from django.contrib import admin
from .models import (
    Zone, ZoneMember, RateCard, RateLine, RateBreak,
    QuoteSpotRate, QuoteSpotCharge, LocalFeeRule
)

class ZoneMemberInline(admin.TabularInline):
    model = ZoneMember
    extra = 1

@admin.register(Zone)
class ZoneAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'mode', 'partner')
    inlines = [ZoneMemberInline]

class RateBreakInline(admin.TabularInline):
    model = RateBreak
    extra = 1

class RateLineInline(admin.TabularInline):
    model = RateLine
    extra = 1
    show_change_link = True

@admin.register(RateCard)
class RateCardAdmin(admin.ModelAdmin):
    list_display = ('name', 'supplier', 'mode', 'origin_zone', 'destination_zone', 'valid_from', 'priority')
    list_filter = ('mode', 'scope', 'supplier')
    inlines = [RateLineInline]

@admin.register(RateLine)
class RateLineAdmin(admin.ModelAdmin):
    list_display = ('card', 'component', 'method', 'unit')
    inlines = [RateBreakInline]

@admin.register(QuoteSpotRate)
class QuoteSpotRateAdmin(admin.ModelAdmin):
    list_display = ('quote', 'supplier', 'mode', 'origin_location', 'destination_location')

@admin.register(LocalFeeRule)
class LocalFeeRuleAdmin(admin.ModelAdmin):
    list_display = ('component', 'mode', 'method', 'flat_amount', 'is_active')
