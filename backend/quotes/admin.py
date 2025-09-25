from django.contrib import admin
from django.utils.html import format_html
from .models import Quotation, QuoteVersion, ShipmentPiece, Charge

@admin.register(Quotation)
class QuotationAdmin(admin.ModelAdmin):
    list_display = ("reference", "customer", "status", "service_type", "scope", "payment_term", "sell_currency", "created_at")
    search_fields = ("reference", "customer__name")
    list_filter = ("status", "service_type", "scope", "payment_term", "sell_currency", "created_at")
    date_hierarchy = "created_at"

@admin.register(QuoteVersion)
class QuoteVersionAdmin(admin.ModelAdmin):
    list_display = ("quotation", "version_no", "created_by", "locked_at", "sell_currency", "valid_from", "valid_to", "created_at")
    list_filter = ("locked_at", "sell_currency", "created_at")
    search_fields = ("quotation__reference",)
    readonly_fields = ("version_no", "created_by", "created_at")

    def get_readonly_fields(self, request, obj=None):
        ro = list(super().get_readonly_fields(request, obj))
        if obj and obj.locked_at:
            # lock the whole form
            for f in obj._meta.fields:
                if f.name not in ro:
                    ro.append(f.name)
        return ro

@admin.register(Charge)
class ChargeAdmin(admin.ModelAdmin):
    list_display = ("version", "stage", "side", "code", "description", "basis", "qty", "unit_price", "extended_price", "is_taxable", "gst_percentage", "currency")
    list_filter = ("stage", "side", "is_taxable", "currency")
    search_fields = ("version__quotation__reference", "code", "description")

    def get_readonly_fields(self, request, obj=None):
        # Prevent edits when parent is locked
        if obj and obj.version.locked_at:
            return [f.name for f in obj._meta.fields]
        return super().get_readonly_fields(request, obj)

@admin.register(ShipmentPiece)
class ShipmentPieceAdmin(admin.ModelAdmin):
    list_display = ("version", "length_cm", "width_cm", "height_cm", "weight_kg", "count")
    search_fields = ("version__quotation__reference",)

    def get_readonly_fields(self, request, obj=None):
        if obj and obj.version.locked_at:
            return [f.name for f in obj._meta.fields]
        return super().get_readonly_fields(request, obj)
