# backend/quotes/models.py

import uuid
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.conf import settings # For AUTH_USER_MODEL
from django.utils import timezone # Add timezone for validity default
from datetime import timedelta # Add timedelta for validity default

# Import models needed for V3 ForeignKeys
from parties.models import Company, Contact 
from core.models import Policy, FxSnapshot, Currency # Import Currency
from services.models import MODE_CHOICES # Import choices from services app

# Remove the old Scenario choices if they exist at the top

# --- V3 Refactored Quote Model ---
class Quote(models.Model):
    """
    Main V3 quote object. Stores the high-level request parameters,
    links to the rulesets used, selected customer/contact, and holds
    references to calculated lines and totals.
    """
    # --- V3 Status Choices (keep or refine) ---
    class Status(models.TextChoices):
        DRAFT = 'DRAFT', _('Draft')
        FINAL = 'FINAL', _('Finalized') # Maybe 'Calculated'?
        SENT = 'SENT', _('Sent to Customer')
        ACCEPTED = 'ACCEPTED', _('Accepted')
        LOST = 'LOST', _('Lost')
        EXPIRED = 'EXPIRED', _('Expired')
        # Add 'INCOMPLETE' based on suggestions?
        INCOMPLETE = 'INCOMPLETE', _('Incomplete (Missing Data)')

    # --- V3 Shipment Type Choices ---
    class ShipmentType(models.TextChoices):
        IMPORT = 'IMPORT', _('Import')
        EXPORT = 'EXPORT', _('Export')
        DOMESTIC = 'DOMESTIC', _('Domestic')

    # --- V3 Payment Term Choices ---
    class PaymentTerm(models.TextChoices):
        PREPAID = 'PREPAID', _('Prepaid')
        COLLECT = 'COLLECT', _('Collect')

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    quote_number = models.CharField(max_length=50, unique=True, blank=True, help_text="Auto-generated human-readable ID.")
    
    # --- V3 Core Fields ---
    customer = models.ForeignKey(
        Company, 
        on_delete=models.PROTECT, # Should always have a customer
        related_name='quotes_as_customer', # Clearer relationship name
        help_text="The primary customer requesting the quote.",
        null=True, blank=True
    )
    contact = models.ForeignKey(
        Contact, 
        on_delete=models.SET_NULL, 
        null=True, blank=True,
        related_name='quotes',
        help_text="Specific contact person at the customer company."
    )
    mode = models.CharField(max_length=10, choices=MODE_CHOICES, default='AIR')
    shipment_type = models.CharField(max_length=10, choices=ShipmentType.choices, default='IMPORT')
    # Incoterm: Use CharField for flexibility, list common ones in help_text
    incoterm = models.CharField(
        max_length=3, blank=True, null=True, # Null/Blank for Domestic
        help_text="Incoterm code (e.g., EXW, FOB, DAP, DDP). Null for Domestic."
    )
    payment_term = models.CharField(max_length=10, choices=PaymentTerm.choices, default='PREPAID')
    output_currency = models.ForeignKey(
        Currency, 
        on_delete=models.PROTECT, # A quote must have an output currency
        help_text="The currency the final quote totals are presented in.",
        default='PGK'
    )
    # --- End V3 Core Fields ---

    # --- ADD THESE FIELDS ---
    valid_until = models.DateField(
        null=True, blank=True, 
        help_text="Date the quote expires."
    )
    origin_code = models.CharField(
        max_length=10, null=True, blank=True, # Allow blank for certain quote types if needed
        help_text="Origin location code (e.g., Airport IATA, Port UN/LOCODE)."
    )
    destination_code = models.CharField(
        max_length=10, null=True, blank=True,
        help_text="Destination location code."
    )
    # --- END ADD ---

    # --- Links to specific parties (optional if covered by 'customer') ---
    # We might still want these if Customer != BillTo/Shipper/Consignee
    # bill_to = models.ForeignKey(Company, ...)
    # shipper = models.ForeignKey(Company, ...)
    # consignee = models.ForeignKey(Company, ...)

    # --- Auditability & Ruleset Links ---
    # Keep Policy FK for now, although V3 might rely more on CustomerCommercialProfile
    policy = models.ForeignKey(
        Policy, 
        on_delete=models.PROTECT, null=True, blank=True, # May become less critical
        help_text="Policy version used (may be overridden by customer profile)."
    ) 
    fx_snapshot = models.ForeignKey(
        FxSnapshot, 
        on_delete=models.PROTECT, 
        help_text="The exact FX snapshot used for this quote calculation.",
        null=True, blank=True
    )
    
    # --- Optional V3 Flags ---
    is_dangerous_goods = models.BooleanField(default=False)
    # Add other flags as needed (e.g., requires_door_pickup)

    # --- Status & Meta ---
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    request_details_json = models.JSONField(
        null=True, blank=True, 
        help_text="Store the original V3 API request payload for reference/replay."
    ) 
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True, related_name='created_quotes'
    )
    updated_at = models.DateTimeField(auto_now=True)
    
    # --- Field Removed ---
    # scenario = models.CharField(...) 

    def __str__(self):
        return self.quote_number or str(self.id)

    def save(self, *args, **kwargs):
        if not self.quote_number:
            # Simple sequence - consider a more robust generator for production
            last_quote = Quote.objects.all().order_by('created_at').last()
            last_id = int(last_quote.quote_number.split('-')[1]) if last_quote and '-' in last_quote.quote_number else 1000
            self.quote_number = f"QT-{last_id + 1}"
        # --- ADD DEFAULT VALIDITY ---
        if not self.valid_until and self.created_at:
             self.valid_until = (self.created_at + timedelta(days=7)).date() # Default 7 days validity
        # ---
        super().save(*args, **kwargs)

# --- QuoteLine and QuoteTotal ---
# Keep existing QuoteLine and QuoteTotal models for now.
# QuoteTotal already has output_currency fields which align with V3.
# QuoteLine might need refinement later to better link to ServiceComponent.

class QuoteLine(models.Model):
    """
    A single, auditable line item within a quote.
    REMAINS LARGELY UNCHANGED FOR NOW - Needs review in V3 logic phase.
    """
    class Section(models.TextChoices):
        ORIGIN = 'ORIGIN', _('Origin')
        FREIGHT = 'FREIGHT', _('Freight') # Might rename to MAIN
        DESTINATION = 'DESTINATION', _('Destination')
        INFO_ONLY = 'INFO_ONLY', _('Informational Only')

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    quote = models.ForeignKey(Quote, related_name='lines', on_delete=models.CASCADE)
    section = models.CharField(max_length=20, choices=Section.choices)
    # Link to ServiceComponent later?
    # service_component = models.ForeignKey('services.ServiceComponent', ...) 
    charge_code = models.CharField(max_length=50, help_text="e.g., 'FREIGHT', 'CARTAGE', 'AW'")
    description = models.CharField(max_length=255)
    
    basis = models.CharField(max_length=50) 
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=1.0) # Default quantity to 1
    rate = models.DecimalField(max_digits=12, decimal_places=4, default=0.0) # Rate used (native currency)
    currency = models.CharField(max_length=3) # Native currency of the rate/buy_amount
    
    buy_amount_native = models.DecimalField(max_digits=12, decimal_places=2, default=0.0) # Cost in native currency
    # Maybe add buy_amount_pgk ?
    sell_amount_pgk = models.DecimalField(max_digits=12, decimal_places=2, default=0.0) # Sell price converted to PGK (before final currency conversion)
    gst_amount_pgk = models.DecimalField(max_digits=12, decimal_places=2, default=0.0)
    
    # Audit Flags & Data
    caf_applied_pct = models.DecimalField(max_digits=5, decimal_places=4, null=True, blank=True)
    margin_applied_pct = models.DecimalField(max_digits=5, decimal_places=4, null=True, blank=True)
    rounding_applied = models.BooleanField(default=False)
    source_references = models.JSONField(null=True, blank=True, help_text="Links to sources, e.g., {'surcharge_id': '.', 'service_component_id': '.'}")

    def __str__(self):
        return f"{self.quote.quote_number} - {self.description}"

class QuoteTotal(models.Model):
    """
    Final totals for the quote. Already includes output currency fields.
    REMAINS UNCHANGED.
    """
    quote = models.OneToOneField(Quote, primary_key=True, related_name='totals', on_delete=models.CASCADE)
    subtotal_pgk = models.DecimalField(max_digits=12, decimal_places=2, default=0.0)
    gst_total_pgk = models.DecimalField(max_digits=12, decimal_places=2, default=0.0)
    grand_total_pgk = models.DecimalField(max_digits=12, decimal_places=2, default=0.0)
    output_currency = models.CharField(max_length=3, default='PGK') # For agent quotes or V3 multi-currency
    grand_total_output_currency = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    notes = models.TextField(null=True, blank=True)

    def __str__(self):
        return f"Totals for {self.quote.quote_number}"

# --- ADD QuoteVersion MODEL ---
class QuoteVersion(models.Model):
    """
    Stores a snapshot of the input payload and key details for a specific
    version of a quote calculation. Essential for audit and replay.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    quote = models.ForeignKey(Quote, on_delete=models.CASCADE, related_name='versions')
    version_no = models.PositiveIntegerField(help_text="Sequential version number (e.g., 1, 2, 3).")
    
    # Store the exact input request payload that generated this version
    payload_json = models.JSONField(
        help_text="The V3 API request payload used for this calculation."
    )
    # Store references to the specific rulesets used for this version
    policy = models.ForeignKey(
        Policy, 
        on_delete=models.PROTECT, null=True, blank=True,
        help_text="Policy snapshot used for this version (if applicable)."
    ) 
    fx_snapshot = models.ForeignKey(
        FxSnapshot, 
        on_delete=models.PROTECT, 
        help_text="FX snapshot used for this version."
    )
    # Potentially store calculated totals here too for quick reference?
    # grand_total_pgk = models.DecimalField(...)
    # grand_total_output_currency = models.DecimalField(...)
    
    status = models.CharField(
        max_length=20, choices=Quote.Status.choices, default=Quote.Status.DRAFT,
        help_text="Status of the quote at the time this version was created."
    )
    reason = models.TextField(
        null=True, blank=True,
        help_text="Reason for creating this new version (e.g., 'Customer requested change', 'Initial Draft')."
    )
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True, related_name='+'
    )

    class Meta:
        unique_together = ('quote', 'version_no')
        ordering = ['quote', '-version_no'] # Show newest version first

    def __str__(self):
        return f"{self.quote.quote_number} - v{self.version_no}"

# --- ADD OverrideNote MODEL ---
class OverrideNote(models.Model):
    """
    Records a manual override made during the quote process, requiring a reason
    and tracking who made the change.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # Link to the specific version where the override was applied
    quote_version = models.ForeignKey(
        QuoteVersion, 
        on_delete=models.CASCADE, 
        related_name='overrides'
    )
    # Optional: Link to a specific line if the override applies there
    # quote_line = models.ForeignKey(QuoteLine, on_delete=models.SET_NULL, null=True, blank=True)
    
    field = models.CharField(
        max_length=100,
        help_text="Identifier of what was overridden (e.g., 'scope', 'manual_rate:FRT_AIR', 'margin_pct')."
    )
    old_value = models.TextField(null=True, blank=True)
    new_value = models.TextField()
    reason = models.TextField(help_text="Mandatory reason for the override.")
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True, related_name='+'
    )
    # Optional: Approval tracking
    # approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, ...)
    # approved_at = models.DateTimeField(...)

    def __str__(self):
        return f"Override on {self.quote_version}: {self.field}"

    class Meta:
        ordering = ['-created_at']
