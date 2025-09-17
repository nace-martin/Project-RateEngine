from django.contrib import admin

from .models import CurrencyRates, FeeTypes, Providers, Services, Stations


class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Stations)
class StationsAdmin(ReadOnlyAdmin):
    list_display = ("id", "iata", "city", "country")
    search_fields = ("iata", "city", "country")


@admin.register(Providers)
class ProvidersAdmin(ReadOnlyAdmin):
    list_display = ("id", "name", "provider_type")
    list_filter = ("provider_type",)
    search_fields = ("name",)


@admin.register(FeeTypes)
class FeeTypesAdmin(ReadOnlyAdmin):
    list_display = ("id", "code", "description", "basis")


@admin.register(Services)
class ServicesAdmin(ReadOnlyAdmin):
    list_display = ("id", "code", "name", "basis")


@admin.register(CurrencyRates)
class CurrencyRatesAdmin(ReadOnlyAdmin):
    list_display = ("id", "as_of_ts", "base_ccy", "quote_ccy", "rate", "source")
    list_filter = ("base_ccy", "quote_ccy", "source")
