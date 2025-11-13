# backend/quotes/admin.py

from django.contrib import admin
from .models import Quote, QuoteVersion, QuoteLine, QuoteTotal, OverrideNote

class QuoteLineInline(admin.TabularInline):
    model = QuoteLine
    extra = 0
    readonly_fields = [f.name for f in QuoteLine._meta.fields] # Make all fields read-only
    can_delete = False

class QuoteTotalInline(admin.StackedInline):
    model = QuoteTotal
    readonly_fields = [f.name for f in QuoteTotal._meta.fields]
    can_delete = False
    
class OverrideNoteInline(admin.TabularInline):
    model = OverrideNote
    extra = 0
    readonly_fields = [f.name for f in OverrideNote._meta.fields]
    can_delete = False

class QuoteVersionAdmin(admin.ModelAdmin):
    model = QuoteVersion
    list_display = ('quote', 'version_number', 'status', 'created_at', 'created_by')
    list_filter = ('status', 'created_at')
    inlines = [QuoteTotalInline, QuoteLineInline, OverrideNoteInline]
    readonly_fields = ('quote', 'version_number', 'payload_json', 'policy', 'fx_snapshot', 'status', 'reason', 'created_at', 'created_by')

class QuoteVersionInline(admin.TabularInline):
    model = QuoteVersion
    extra = 0
    fields = ('version_number', 'status', 'created_at', 'created_by')
    readonly_fields = ('version_number', 'status', 'created_at', 'created_by')
    can_delete = False
    show_change_link = True # Allow clicking to the full version

class QuoteAdmin(admin.ModelAdmin):
    model = Quote
    
    # --- UPDATED FIELDS ---
    list_display = (
        'quote_number', 
        'customer', 
        'mode', 
        'shipment_type', # <-- Show our new field
        'origin_airport', # <-- Show new field
        'destination_airport', # <-- Show new field
        'status', 
        'created_at', 
        'created_by'
    )
    list_filter = ('status', 'mode', 'shipment_type', 'created_at')
    search_fields = ('quote_number', 'customer__name')
    # --- END UPDATES ---
    
    inlines = [QuoteVersionInline]
    
    # Make fields read-only in the admin, as they are set by the compute logic
    readonly_fields = (
        'quote_number', 'customer', 'contact', 'mode', 'shipment_type', 
        'incoterm', 'payment_term', 'output_currency', 
        'origin_airport', 'destination_airport', 'origin_port', 'destination_port',
        'policy', 'fx_snapshot', 'is_dangerous_goods', 'status', 
        'request_details_json', 'created_at', 'created_by', 'updated_at'
    )

# Register your models
admin.site.register(Quote, QuoteAdmin)
admin.site.register(QuoteVersion, QuoteVersionAdmin)