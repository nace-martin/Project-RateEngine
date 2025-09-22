from django.contrib import admin, messages

from pricing.models import (
    LaneBreaks,
    Lanes,
    PricingPolicy,
    RatecardConfig,
    RatecardFees,
    Ratecards,
    SellCostLinksSimple,
    ServiceItems,
)
from pricing.services.pricing_service import validate_break_monotonic


@admin.register(Ratecards)
class RatecardsAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "role",
        "scope",
        "direction",
        "audience",
        "currency",
        "status",
        "effective_date",
        "expiry_date",
    )
    list_filter = ("role", "scope", "direction", "audience", "currency", "status")
    search_fields = ("name",)


@admin.register(Lanes)
class LanesAdmin(admin.ModelAdmin):
    list_display = ("id", "ratecard", "origin", "dest", "airline", "is_direct")
    list_filter = ("airline", "is_direct", "ratecard", "origin", "dest")
    autocomplete_fields = ("ratecard", "origin", "dest")
    actions = ["validate_breaks"]

    def validate_breaks(self, request, queryset):
        any_warn = False
        for lane in queryset:
            warnings = validate_break_monotonic(lane.id)
            if warnings:
                any_warn = True
                for warning in warnings:
                    messages.warning(request, f"Lane {lane.id}: {warning}")
        if not any_warn:
            messages.info(request, "Selected lanes have monotonic breaks.")

    validate_breaks.short_description = "Validate lane break monotonicity"


@admin.register(LaneBreaks)
class LaneBreaksAdmin(admin.ModelAdmin):
    list_display = ("id", "lane", "break_code", "min_charge", "per_kg")
    list_filter = ("break_code", "lane")


@admin.register(RatecardConfig)
class RatecardConfigAdmin(admin.ModelAdmin):
    list_display = ("id", "ratecard", "dim_factor_kg_per_m3", "rate_strategy")
    list_filter = ("rate_strategy",)


@admin.register(RatecardFees)
class RatecardFeesAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "ratecard",
        "fee_type",
        "currency",
        "amount",
        "min_amount",
        "max_amount",
    )


@admin.register(ServiceItems)
class ServiceItemsAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "ratecard",
        "service",
        "currency",
        "amount",
        "tax_pct",
        "min_amount",
        "max_amount",
        "percent_of_service_code",
    )


@admin.register(SellCostLinksSimple)
class SellCostLinksSimpleAdmin(admin.ModelAdmin):
    list_display = ("id", "sell_item", "buy_fee_code", "mapping_type", "mapping_value")


@admin.register(PricingPolicy)
class PricingPolicyAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "audience",
        "caf_buy_pct",
        "caf_sell_pct",
        "gst_applies",
        "gst_pct",
    )
    list_filter = ("audience",)

