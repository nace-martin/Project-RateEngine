# backend/quotes/models.py

import uuid
from datetime import timedelta

from django.conf import settings  # For AUTH_USER_MODEL
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

# Import models needed for V3 ForeignKeys
from parties.models import Company, Contact, Organization
# --- UPDATED IMPORT ---
from core.models import Policy, FxSnapshot, Location
from core.commodity import COMMODITY_CHOICES, DEFAULT_COMMODITY_CODE
# --- END UPDATE ---
from services.models import MODE_CHOICES, ServiceComponent, SERVICE_SCOPE_CHOICES


# --- V3 Refactored Quote Model ---
# Re-export SPOT models for backward compatibility
from .spot_models import (
    SpotPricingEnvelopeDB,
    SPEChargeLineDB,
    SPEAcknowledgementDB,
)

class Quote(models.Model):
    """
    Main V3 quote object.
    """

    class Status(models.TextChoices):
        DRAFT = 'DRAFT', _('Draft')
        FINALIZED = 'FINALIZED', _('Finalized')  # Renamed from FINAL for consistency
        SENT = 'SENT', _('Sent to Customer')
        ACCEPTED = 'ACCEPTED', _('Accepted')  # Post-MVP
        LOST = 'LOST', _('Lost')  # Post-MVP
        EXPIRED = 'EXPIRED', _('Expired')  # Post-MVP
        INCOMPLETE = 'INCOMPLETE', _('Incomplete (Missing Data)')

    class ShipmentType(models.TextChoices):
        IMPORT = 'IMPORT', _('Import')
        EXPORT = 'EXPORT', _('Export')
        DOMESTIC = 'DOMESTIC', _('Domestic')

    class PaymentTerm(models.TextChoices):
        PREPAID = 'PREPAID', _('Prepaid')
        COLLECT = 'COLLECT', _('Collect')

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    quote_number = models.CharField(max_length=50, unique=True, blank=True, help_text="Auto-generated human-readable ID.")

    # --- V3 Core Fields ---
    customer = models.ForeignKey(
        Company,
        on_delete=models.PROTECT,
        related_name='quotes_as_customer',
        help_text="The primary customer requesting the quote."
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="quotes",
        help_text="Tenant/account branding context for this quote.",
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
    incoterm = models.CharField(
        max_length=3, blank=True, null=True,
        help_text="Incoterm code (e.g., EXW, FOB, DAP). Null for Domestic."
    )
    payment_term = models.CharField(max_length=10, choices=PaymentTerm.choices, default='PREPAID')
    service_scope = models.CharField(
        max_length=3,
        choices=SERVICE_SCOPE_CHOICES,
        null=True,
        blank=True,
        help_text="User-selected scope (e.g., D2D, D2A) used by the v1.1 engine."
    )

    output_currency = models.CharField(
        max_length=3,
        help_text="The 3-letter ISO currency code the quote is presented in.",
        default='PGK'
    )

    valid_until = models.DateField(
        null=True, blank=True,
        help_text="Date the quote expires."
    )

    # --- REFACTORED LOCATION FIELDS ---
    # Removed origin_code and destination_code CharFields
    origin_location = models.ForeignKey(
        Location,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='quotes_as_origin',
        help_text="Generic origin location (airport, port, city, address)."
    )
    destination_location = models.ForeignKey(
        Location,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='quotes_as_destination',
        help_text="Generic destination location (airport, port, city, address)."
    )
    # --- END REFACTOR ---

    policy = models.ForeignKey(
        Policy,
        on_delete=models.PROTECT, null=True, blank=True,
        help_text="Policy version used (may be overridden by customer profile)."
    )
    fx_snapshot = models.ForeignKey(
        FxSnapshot,
        on_delete=models.PROTECT,
        help_text="The exact FX snapshot used for this quote calculation.",
        null=True, blank=True
    )

    commodity_code = models.CharField(
        max_length=10,
        choices=COMMODITY_CHOICES,
        default=DEFAULT_COMMODITY_CODE,
        db_index=True,
        help_text="Commodity classification used for conditional pricing decisions.",
    )
    is_dangerous_goods = models.BooleanField(default=False)
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
    
    # --- Lifecycle Timestamps ---
    finalized_at = models.DateTimeField(
        null=True, blank=True,
        help_text="Timestamp when quote was finalized."
    )
    finalized_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True, related_name='finalized_quotes',
        help_text="User who finalized the quote."
    )
    
    # --- Archiving ---
    is_archived = models.BooleanField(
        default=False, 
        db_index=True,
        help_text="True if soft-deleted/archived (e.g. > 3 months old)."
    )
    
    sent_at = models.DateTimeField(
        null=True, blank=True,
        help_text="Timestamp when quote was sent to customer."
    )
    sent_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True, related_name='sent_quotes',
        help_text="User who sent the quote."
    )

    @property
    def is_spot_quote(self) -> bool:
        """Returns True if this quote has an associated Spot Pricing Envelope."""
        if not self.pk:
            return False
        return self.spot_envelopes.exists()

    def __str__(self):
        return self.quote_number or str(self.id)

    def save(self, *args, **kwargs):
        # Generate temporary quote_number for drafts if not set
        if not self.quote_number:
            # DRAFT quotes get a temporary identifier
            # Permanent QT-YYYY-NNNN is assigned on finalize()
            self.quote_number = f"DRAFT-{uuid.uuid4().hex[:8].upper()}"

        # REMOVED: Do not set valid_until for Drafts. 
        # Expiry is now exclusively for Finalized quotes.

        super().save(*args, **kwargs)
    
    def finalize(self, user=None):
        """
        Transition quote from DRAFT to FINALIZED.
        Assigns a permanent sequential quote_number in format: QT-YYYY-NNNN
        Sets valid_until to configured quote validity days (default 7 days) from now.
        
        Uses database-level locking to prevent race conditions.
        
        Args:
            user: The user finalizing the quote (optional)
            
        Returns:
            The assigned quote_number
            
        Raises:
            ValueError: If quote is already finalized
        """
        from django.db import transaction
        
        if self.status == self.Status.FINALIZED:
            raise ValueError(f"Quote {self.quote_number} is already finalized.")
        
        if self.status == self.Status.SENT:
            raise ValueError(f"Quote {self.quote_number} has already been sent.")
        
        current_year = timezone.now().year
        
        with transaction.atomic():
            # Lock the table to prevent race conditions
            # Get the highest quote number for the current year
            year_prefix = f"QT-{current_year}-"
            
            last_quote = (
                Quote.objects
                .filter(quote_number__startswith=year_prefix)
                .select_for_update()
                .order_by('-quote_number')
                .first()
            )
            
            if last_quote and last_quote.quote_number:
                try:
                    # Extract sequence number: QT-2026-0001 -> 0001 -> 1
                    seq_part = last_quote.quote_number.split('-')[-1]
                    last_seq = int(seq_part)
                except (ValueError, IndexError):
                    last_seq = 0
            else:
                last_seq = 0
            
            # Generate new sequential number with 4-digit padding
            new_seq = last_seq + 1
            self.quote_number = f"QT-{current_year}-{new_seq:04d}"
            
            # Update status, timestamps AND expiry
            self.status = self.Status.FINALIZED
            self.finalized_at = timezone.now()
            
            # Always reset expiry from finalization timestamp so clones/stale values
            # cannot carry old validity windows into newly finalized quotes.
            validity_days = getattr(settings, 'QUOTE_VALIDITY_DAYS', 7)
            try:
                validity_days = int(validity_days)
            except (TypeError, ValueError):
                validity_days = 7
            if validity_days < 1:
                validity_days = 7
            self.valid_until = (timezone.now() + timedelta(days=validity_days)).date()
                
            if user:
                self.finalized_by = user
            
            self.save()
        
        return self.quote_number


# --- V3 QuoteVersion MODEL ---
class QuoteVersion(models.Model):
    """
    Stores a snapshot of a single quote calculation.
    All lines and totals are linked to this model.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    quote = models.ForeignKey(Quote, on_delete=models.CASCADE, related_name='versions')

    version_number = models.PositiveIntegerField(help_text="Sequential version number (e.g., 1, 2, 3).")

    payload_json = models.JSONField(
        help_text="The V3 API request payload used for this calculation.",
        null=True, blank=True
    )
    policy = models.ForeignKey(
        Policy,
        on_delete=models.PROTECT, null=True, blank=True,
        help_text="Policy snapshot used for this version (if applicable)."
    )
    fx_snapshot = models.ForeignKey(
        FxSnapshot,
        on_delete=models.PROTECT,
        help_text="FX snapshot used for this version.",
        null=True, blank=True
    )

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
    
    # --- Engine Version Tracking ---
    engine_version = models.CharField(
        max_length=10,
        choices=[('V3', 'V3 Legacy'), ('V4', 'V4 ProductCode')],
        default='V4',
        help_text="Pricing engine version used for this calculation."
    )

    class Meta:
        unique_together = ('quote', 'version_number')
        ordering = ['quote', '-version_number']

    def __str__(self):
        return f"{self.quote.quote_number} - v{self.version_number}"


# --- V3 QuoteLine MODEL ---
class QuoteLine(models.Model):
    """
    A single, auditable line item within a specific QuoteVersion.
    This is the V3-aligned model that matches the _save_quote_v3 method.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    quote_version = models.ForeignKey(
        QuoteVersion,
        related_name='lines',
        on_delete=models.CASCADE
    )
    service_component = models.ForeignKey(
        ServiceComponent,
        on_delete=models.PROTECT,
        null=True  # Allow null for potential manual/summary lines
    )

    # --- V3 Calculation Fields (from _save_quote_v3) ---
    cost_pgk = models.DecimalField(max_digits=12, decimal_places=2, default=0.0)
    cost_fcy = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    cost_fcy_currency = models.CharField(max_length=3, null=True, blank=True)

    sell_pgk = models.DecimalField(max_digits=12, decimal_places=2, default=0.0)
    sell_pgk_incl_gst = models.DecimalField(max_digits=12, decimal_places=2, default=0.0)

    sell_fcy = models.DecimalField(max_digits=12, decimal_places=2, default=0.0)
    sell_fcy_incl_gst = models.DecimalField(max_digits=12, decimal_places=2, default=0.0)
    sell_fcy_currency = models.CharField(max_length=3, null=True, blank=True)

    exchange_rate = models.DecimalField(max_digits=12, decimal_places=6, null=True, blank=True)

    # --- V3 Categorization Fields ---
    leg = models.CharField(max_length=20, null=True, blank=True, help_text="ORIGIN, MAIN, or DESTINATION")
    bucket = models.CharField(max_length=50, null=True, blank=True, help_text="e.g., origin_charges, airfreight, destination_charges")

    # --- V3 Audit Fields (from _save_quote_v3) ---
    cost_source = models.CharField(max_length=50, null=True, blank=True)
    cost_source_description = models.CharField(max_length=255, null=True, blank=True)
    is_rate_missing = models.BooleanField(default=False)
    is_informational = models.BooleanField(
        default=False,
        help_text="If True, this is a conditional charge shown as a note, not included in totals."
    )
    conditional = models.BooleanField(default=False)

    # --- PNG GST Classification Fields ---
    GST_CATEGORY_SERVICE_IN_PNG = 'service_in_PNG'
    GST_CATEGORY_EXPORT_SERVICE = 'export_service'
    GST_CATEGORY_OFFSHORE_SERVICE = 'offshore_service'
    GST_CATEGORY_IMPORTED_GOODS = 'imported_goods'

    GST_CATEGORY_CHOICES = [
        (GST_CATEGORY_SERVICE_IN_PNG, 'Service in PNG (10% GST)'),
        (GST_CATEGORY_EXPORT_SERVICE, 'Export Service (0% Zero-Rated)'),
        (GST_CATEGORY_OFFSHORE_SERVICE, 'Offshore Service (0% Exempt)'),
        (GST_CATEGORY_IMPORTED_GOODS, 'Imported Goods (0% - Customs)'),
    ]

    gst_category = models.CharField(
        max_length=20,
        choices=GST_CATEGORY_CHOICES,
        null=True, blank=True,
        help_text="PNG GST classification for this line item"
    )
    gst_rate = models.DecimalField(
        max_digits=5, decimal_places=4, default=0,
        help_text="GST rate applied (0.10 = 10%)"
    )
    gst_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        help_text="Calculated GST amount for this line"
    )

    def __str__(self):
        name = self.service_component.description if self.service_component else 'Manual Line'
        return f"v{self.quote_version.version_number} - {name}"


# --- V3 QuoteTotal MODEL ---
class QuoteTotal(models.Model):
    """
    Final totals for a specific QuoteVersion.
    This is the V3-aligned model that matches the _save_quote_v3 method.
    """

    quote_version = models.OneToOneField(
        QuoteVersion,
        primary_key=True,
        related_name='totals',
        on_delete=models.CASCADE
    )

    # --- V3 Total Fields (from _save_quote_v3) ---
    total_cost_pgk = models.DecimalField(max_digits=12, decimal_places=2, default=0.0)

    total_sell_pgk = models.DecimalField(max_digits=12, decimal_places=2, default=0.0)
    total_sell_pgk_incl_gst = models.DecimalField(max_digits=12, decimal_places=2, default=0.0)

    total_sell_fcy = models.DecimalField(max_digits=12, decimal_places=2, default=0.0)
    total_sell_fcy_incl_gst = models.DecimalField(max_digits=12, decimal_places=2, default=0.0)
    total_sell_fcy_currency = models.CharField(max_length=3, default='PGK')

    has_missing_rates = models.BooleanField(default=False)
    notes = models.TextField(null=True, blank=True)
    
    # --- Engine Version Tracking (denormalized for reporting) ---
    engine_version = models.CharField(
        max_length=10,
        default='V4',
        help_text="Pricing engine version (denormalized for reporting queries)."
    )

    @property
    def gross_profit(self):
        """Calculate Gross Profit (Sell - Cost) in PGK."""
        return self.total_sell_pgk - self.total_cost_pgk

    @property
    def margin_percent(self):
        """Calculate Margin % as ((Sell - Cost) / Sell) * 100."""
        if self.total_sell_pgk and self.total_sell_pgk > 0:
            return (self.gross_profit / self.total_sell_pgk) * 100
        return 0

    def __str__(self):
        return f"Totals for v{self.quote_version.version_number} of {self.quote_version.quote.quote_number}"


# --- V3 OverrideNote MODEL ---
class OverrideNote(models.Model):
    """
    Records a manual override made during the quote process.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    quote_version = models.ForeignKey(
        QuoteVersion,
        on_delete=models.CASCADE,
        related_name='overrides'
    )

    field = models.CharField(
        max_length=100,
        help_text="Identifier of what was overridden (e.g., 'manual_rate:FRT_AIR')."
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

    def __str__(self):
        return f"Override on {self.quote_version}: {self.field}"

    class Meta:
        ordering = ['-created_at']


# --- QuoteEvent MODEL for Funnel Tracking ---
class QuoteEvent(models.Model):
    """
    Event-based logging for quote lifecycle tracking.
    Enables accurate funnel analysis and time-to-quote metrics.
    """

    class EventType(models.TextChoices):
        CREATED = 'CREATED', 'Created'
        FINALIZED = 'FINALIZED', 'Finalized'
        SENT = 'SENT', 'Sent'
        ACCEPTED = 'ACCEPTED', 'Accepted'
        LOST = 'LOST', 'Lost'
        EXPIRED = 'EXPIRED', 'Expired'
        REVISED = 'REVISED', 'Revised'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    quote = models.ForeignKey(
        Quote,
        on_delete=models.CASCADE,
        related_name='events'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='+'
    )
    event_type = models.CharField(
        max_length=20,
        choices=EventType.choices
    )
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    metadata = models.JSONField(
        null=True, blank=True,
        help_text="Optional additional context for the event."
    )

    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['quote', 'event_type']),
            models.Index(fields=['timestamp', 'event_type']),
        ]

    def __str__(self):
        return f"{self.quote.quote_number} - {self.event_type} at {self.timestamp}"
