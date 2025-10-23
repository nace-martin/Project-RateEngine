# backend/quotes/admin.py

from django.contrib import admin
# Add QuoteVersion and OverrideNote to imports
from .models import Quote, QuoteLine, QuoteTotal, QuoteVersion, OverrideNote 

class QuoteLineInline(admin.TabularInline):
    # ... (no change) ...
    model = QuoteLine
    extra = 0
    readonly_fields = ('id',) # Make id readonly if needed

class QuoteTotalInline(admin.StackedInline):
    # ... (no change) ...
    model = QuoteTotal
    can_delete = False # Usually only one total record

# --- ADD INLINES FOR VERSIONING/OVERRIDES ---
class QuoteVersionInline(admin.TabularInline):
    """Shows quote versions related to a Quote."""
    model = QuoteVersion
    extra = 0
    fields = ('version_no', 'status', 'reason', 'created_at', 'created_by')
    readonly_fields = ('version_no', 'created_at', 'created_by') # Typically read-only here
    ordering = ('-version_no',)
    can_delete = False
    show_change_link = True # Allows clicking to the full QuoteVersion admin

class OverrideNoteInline(admin.TabularInline):
    """Shows override notes related to a Quote Version."""
    model = OverrideNote
    extra = 0
    fields = ('field', 'new_value', 'reason', 'created_at', 'created_by')
    readonly_fields = ('created_at', 'created_by')
    ordering = ('-created_at',)
    can_delete = False

# --- REGISTER QuoteVersion SEPARATELY ---
@admin.register(QuoteVersion)
class QuoteVersionAdmin(admin.ModelAdmin):
    list_display = ('quote', 'version_no', 'status', 'created_at', 'created_by')
    list_filter = ('status', 'created_at')
    search_fields = ('quote__quote_number',)
    readonly_fields = ('created_at', 'created_by', 'payload_json', 'policy', 'fx_snapshot') # Make key fields read-only
    inlines = [OverrideNoteInline] # Show overrides linked to this version

# --- UPDATE QuoteAdmin ---
@admin.register(Quote)
class QuoteAdmin(admin.ModelAdmin):
    inlines = [QuoteTotalInline, QuoteLineInline, QuoteVersionInline] # Add QuoteVersionInline
    list_display = ('quote_number', 'customer', 'mode', 'shipment_type', 'incoterm', 'status', 'created_at')
    list_filter = ('mode', 'shipment_type', 'status', 'created_at')
    search_fields = ('quote_number', 'customer__name')
    # Make V3 fields read-only after creation? Depends on workflow.
    readonly_fields = ('id', 'quote_number', 'created_at', 'updated_at') 

# Register OverrideNote if direct access needed (optional)
# admin.site.register(OverrideNote)