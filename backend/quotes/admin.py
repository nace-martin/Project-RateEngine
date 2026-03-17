# backend/quotes/admin.py

from django.contrib import admin
from .models import (
    Quote, QuoteVersion, QuoteLine, QuoteTotal, OverrideNote
)
from .spot_models import (
    SpotPricingEnvelopeDB, SPEChargeLineDB, SPEAcknowledgementDB, SPEManagerApprovalDB
)

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
        'shipment_type',
        'commodity_code',
        'approval_required',
        'origin_location',
        'destination_location',
        'status', 
        'created_at', 
        'created_by'
    )
    list_filter = ('status', 'mode', 'shipment_type', 'approval_required', 'created_at')
    search_fields = ('quote_number', 'customer__name')
    # --- END UPDATES ---
    
    inlines = [QuoteVersionInline]
    
    # Make fields read-only in the admin, as they are set by the compute logic
    readonly_fields = (
        'quote_number', 'customer', 'contact', 'mode', 'shipment_type', 
        'incoterm', 'payment_term', 'output_currency', 
        'origin_location', 'destination_location',
        'policy', 'fx_snapshot', 'commodity_code', 'approval_required', 'approval_reason',
        'is_dangerous_goods', 'status',
        'request_details_json', 'created_at', 'created_by', 'updated_at',
        'finalized_at', 'finalized_by', 'sent_at', 'sent_by'
    )

# --- SPOT Mode Admin Configuration ---

class SPEChargeLineInline(admin.TabularInline):
    model = SPEChargeLineDB
    extra = 0
    can_delete = False
    readonly_fields = ('code', 'description', 'amount', 'currency', 'unit', 'bucket', 'is_primary_cost', 'source_reference', 'entered_by', 'entered_at')

class SPEAcknowledgementInline(admin.StackedInline):
    model = SPEAcknowledgementDB
    extra = 0
    can_delete = False
    readonly_fields = ('acknowledged_by', 'acknowledged_at', 'statement')

class SPEManagerApprovalInline(admin.StackedInline):
    model = SPEManagerApprovalDB
    extra = 0
    can_delete = False
    readonly_fields = ('approved', 'manager', 'decision_at', 'comment')

class SpotPricingEnvelopeAdmin(admin.ModelAdmin):
    model = SpotPricingEnvelopeDB
    list_display = ('__str__', 'status', 'spot_trigger_reason_code', 'created_by', 'created_at', 'expires_at')
    list_filter = ('status', 'spot_trigger_reason_code', 'created_at')
    search_fields = ('id', 'created_by__username', 'spot_trigger_reason_code')
    
    inlines = [SPEChargeLineInline, SPEAcknowledgementInline, SPEManagerApprovalInline]
    
    readonly_fields = (
        'id', 'status', 'shipment_context_json', 'shipment_context_hash',
        'conditions_json', 'spot_trigger_reason_code', 'spot_trigger_reason_text',
        'created_at', 'created_by', 'expires_at', 'quote'
    )
    
    fieldsets = (
        ('Lifecycle', {
            'fields': ('id', 'status', 'created_at', 'created_by', 'expires_at', 'quote')
        }),
        ('Trigger Context', {
            'fields': ('spot_trigger_reason_code', 'spot_trigger_reason_text', 'shipment_context_json', 'shipment_context_hash')
        }),
        ('Conditions', {
            'fields': ('conditions_json',)
        }),
    )

# Register your models
admin.site.register(Quote, QuoteAdmin)
admin.site.register(QuoteVersion, QuoteVersionAdmin)
admin.site.register(SpotPricingEnvelopeDB, SpotPricingEnvelopeAdmin)
