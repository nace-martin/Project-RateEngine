from django.contrib import admin

from .models import (
    Shipment,
    ShipmentAddressBookEntry,
    ShipmentCharge,
    ShipmentDocument,
    ShipmentEvent,
    ShipmentPiece,
    ShipmentSettings,
    ShipmentTemplate,
)


class ShipmentPieceInline(admin.TabularInline):
    model = ShipmentPiece
    extra = 0


class ShipmentChargeInline(admin.TabularInline):
    model = ShipmentCharge
    extra = 0


@admin.register(Shipment)
class ShipmentAdmin(admin.ModelAdmin):
    list_display = (
        "connote_number",
        "status",
        "shipment_date",
        "origin_code",
        "destination_code",
        "total_chargeable_weight_kg",
    )
    list_filter = ("status", "shipment_date", "organization")
    search_fields = (
        "connote_number",
        "reference_number",
        "shipper_company_name",
        "consignee_company_name",
    )
    inlines = [ShipmentPieceInline, ShipmentChargeInline]


@admin.register(ShipmentAddressBookEntry)
class ShipmentAddressBookEntryAdmin(admin.ModelAdmin):
    list_display = ("label", "company_name", "company", "contact", "party_role", "organization", "is_active")
    list_filter = ("party_role", "organization", "is_active")
    search_fields = ("label", "company_name", "contact_name", "city", "country_code", "company__name", "contact__email")


@admin.register(ShipmentTemplate)
class ShipmentTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "organization", "is_active", "updated_at")
    list_filter = ("organization", "is_active")
    search_fields = ("name", "description")


@admin.register(ShipmentDocument)
class ShipmentDocumentAdmin(admin.ModelAdmin):
    list_display = ("shipment", "document_type", "file_name", "created_at")


@admin.register(ShipmentEvent)
class ShipmentEventAdmin(admin.ModelAdmin):
    list_display = ("shipment", "event_type", "created_by", "created_at")


@admin.register(ShipmentSettings)
class ShipmentSettingsAdmin(admin.ModelAdmin):
    list_display = ("organization", "connote_station_code", "connote_mode_code", "updated_at")
