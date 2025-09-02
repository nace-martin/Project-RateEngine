from django.contrib import admin
from .models import Client, Quote, RateCard


@admin.register(RateCard)
class RateCardAdmin(admin.ModelAdmin):
    list_display = (
        'origin', 'destination', 'min_charge',
        'brk_45', 'brk_100', 'brk_250', 'brk_500', 'brk_1000',
        'caf_pct', 'created_at',
    )
    search_fields = ('origin', 'destination')
    list_filter = ('origin', 'destination')
    ordering = ('origin', 'destination', '-created_at')
    list_per_page = 50


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'phone', 'org_type', 'created_at')
    search_fields = ('name', 'email')
    list_filter = ('org_type',)
    ordering = ('name',)


@admin.register(Quote)
class QuoteAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'client', 'origin', 'destination', 'shipment_type', 'service_scope',
        'chargeable_weight_kg', 'rate_used_per_kg', 'base_cost', 'total_sell',
        'created_at',
    )
    search_fields = ('client__name', 'origin', 'destination')
    list_filter = ('shipment_type', 'service_scope', 'origin', 'destination')
    ordering = ('-created_at',)
