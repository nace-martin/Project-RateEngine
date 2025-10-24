# backend/quotes/admin.py

from django.contrib import admin
from .models import Quote, QuoteLine, QuoteTotal, QuoteVersion, OverrideNote

class QuoteLineInline(admin.TabularInline):
    model = QuoteLine
    extra = 0
    readonly_fields = ('id',)

class QuoteTotalInline(admin.StackedInline):
    model = QuoteTotal
    can_delete = False

class QuoteVersionInline(admin.TabularInline):
    """Shows quote versions related to a Quote."""
    model = QuoteVersion
    extra = 0
    fields = ('version_number', 'status', 'reason', 'created_at', 'created_by')
    readonly_fields = ('version_number', 'created_at', 'created_by')
    ordering = ('-version_number',)
    can_delete = False
    show_change_link = True

class OverrideNoteInline(admin.TabularInline):
    """Shows override notes related to a Quote Version."""
    model = OverrideNote
    extra = 0
    fields = ('field', 'new_value', 'reason', 'created_at', 'created_by')
    readonly_fields = ('created_at', 'created_by')
    ordering = ('-created_at',)
    can_delete = False

@admin.register(QuoteVersion)
class QuoteVersionAdmin(admin.ModelAdmin):
    list_display = ('quote', 'version_number', 'status', 'created_at', 'created_by')
    list_filter = ('status', 'created_at')
    search_fields = ('quote__quote_number',)
    readonly_fields = ('created_at', 'created_by', 'payload_json', 'policy', 'fx_snapshot')
    inlines = [QuoteTotalInline, QuoteLineInline, OverrideNoteInline]

@admin.register(Quote)
class QuoteAdmin(admin.ModelAdmin):
    inlines = [QuoteVersionInline]
    list_display = ('quote_number', 'customer', 'mode', 'shipment_type', 'incoterm', 'status', 'created_at')
    list_filter = ('mode', 'shipment_type', 'status', 'created_at')
    search_fields = ('quote_number', 'customer__name')
    readonly_fields = ('id', 'quote_number', 'created_at', 'updated_at')

# Register OverrideNote if direct access needed (optional)
# admin.site.register(OverrideNote)
