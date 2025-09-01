from django.contrib import admin, messages
from .models import (
    Providers, Stations, Ratecards, RatecardConfig, Lanes, LaneBreaks,
    FeeTypes, RatecardFees, Services, ServiceItems, SellCostLinksSimple,
    CurrencyRates, PricingPolicy,
)
from .engine import validate_break_monotonic

class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False

@admin.register(Ratecards)
class RatecardsAdmin(ReadOnlyAdmin):
    list_display = ("id","name","role","scope","direction","audience","currency","status","effective_date","expiry_date")
    list_filter  = ("role","scope","direction","audience","currency","status")
    search_fields = ("name",)

@admin.register(Lanes)
class LanesAdmin(ReadOnlyAdmin):
    list_display = ("id","ratecard","origin","dest","airline","is_direct")
    list_filter  = ("airline","is_direct","ratecard","origin","dest")
    autocomplete_fields = ("ratecard","origin","dest")
    actions = ["validate_breaks"]

    def validate_breaks(self, request, queryset):
        any_warn = False
        for lane in queryset:
            warnings = validate_break_monotonic(lane.id)
            if warnings:
                any_warn = True
                for w in warnings:
                    messages.warning(request, f"Lane {lane.id}: {w}")
        if not any_warn:
            messages.info(request, "Selected lanes have monotonic breaks.")
    validate_breaks.short_description = "Validate lane break monotonicity"

@admin.register(LaneBreaks)
class LaneBreaksAdmin(ReadOnlyAdmin):
    list_display = ("id","lane","break_code","min_charge","per_kg")
    list_filter  = ("break_code","lane")

@admin.register(Stations)
class StationsAdmin(ReadOnlyAdmin):
    list_display = ("id","iata","city","country")
    search_fields = ("iata","city","country")

@admin.register(Providers)
class ProvidersAdmin(ReadOnlyAdmin):
    list_display = ("id","name","provider_type")
    list_filter  = ("provider_type",)
    search_fields = ("name",)

@admin.register(RatecardConfig)
class RatecardConfigAdmin(ReadOnlyAdmin):
    list_display = ("id","ratecard","dim_factor_kg_per_m3","rate_strategy")
    list_filter  = ("rate_strategy",)

@admin.register(FeeTypes)
class FeeTypesAdmin(ReadOnlyAdmin):
    list_display = ("id","code","description","basis")

@admin.register(RatecardFees)
class RatecardFeesAdmin(ReadOnlyAdmin):
    list_display = ("id","ratecard","fee_type","currency","amount","min_amount","max_amount")

@admin.register(Services)
class ServicesAdmin(ReadOnlyAdmin):
    list_display = ("id","code","name","basis")

@admin.register(ServiceItems)
class ServiceItemsAdmin(ReadOnlyAdmin):
    list_display = ("id","ratecard","service","currency","amount","tax_pct","min_amount","max_amount","percent_of_service_code")

@admin.register(SellCostLinksSimple)
class SellCostLinksSimpleAdmin(ReadOnlyAdmin):
    list_display = ("id","sell_item","buy_fee_code","mapping_type","mapping_value")

@admin.register(CurrencyRates)
class CurrencyRatesAdmin(ReadOnlyAdmin):
    list_display = ("id","as_of_ts","base_ccy","quote_ccy","rate","source")
    list_filter  = ("base_ccy","quote_ccy","source")

@admin.register(PricingPolicy)
class PricingPolicyAdmin(ReadOnlyAdmin):
    list_display = ("id","audience","caf_on_fx","gst_applies","gst_pct")
    list_filter  = ("audience",)
