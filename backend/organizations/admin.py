from django.contrib import admin

from .models import Organizations


@admin.register(Organizations)
class OrganizationsAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "audience", "default_sell_currency", "country_code")
    list_filter = ("audience", "default_sell_currency", "country_code")
    search_fields = ("name",)
