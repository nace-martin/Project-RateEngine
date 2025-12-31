# backend/quotes/models.py

import uuid
from datetime import timedelta

from django.conf import settings  # For AUTH_USER_MODEL
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

# Import models needed for V3 ForeignKeys
from parties.models import Company, Contact
# --- UPDATED IMPORT ---
from core.models import Policy, FxSnapshot, Location
# --- END UPDATE ---
from services.models import MODE_CHOICES, ServiceComponent, SERVICE_SCOPE_CHOICES


# --- V3 Refactored Quote Model ---
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

    def __str__(self):
        return self.quote_number or str(self.id)

    def save(self, *args, **kwargs):
        if not self.quote_number:
            # Note: This is a simple counter. For production, a more robust
            # sequential ID generator might be needed to avoid race conditions.
            last_quote = Quote.objects.all().order_by('created_at').last()
            last_id = 0
            if last_quote and last_quote.quote_number and '-' in last_quote.quote_number:
                try:
                    last_id = int(last_quote.quote_number.split('-')[1])
                except (ValueError, IndexError):
                    last_id = 0
            self.quote_number = f"QT-{last_id + 1}"

        if not self.valid_until:
            created = self.created_at or timezone.now()
            self.valid_until = (created + timedelta(days=7)).date()

        super().save(*args, **kwargs)


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

    # --- V3 Audit Fields (from _save_quote_v3) ---
    cost_source = models.CharField(max_length=50, null=True, blank=True)
    cost_source_description = models.CharField(max_length=255, null=True, blank=True)
    is_rate_missing = models.BooleanField(default=False)
    is_informational = models.BooleanField(
        default=False,
        help_text="If True, this is a conditional charge shown as a note, not included in totals."
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

# --- V3 SpotChargeLine MODEL ---

    
    def clean(self):
        from django.core.exceptions import ValidationError
        
        if self.unit_basis == self.UnitBasis.PERCENTAGE:
            if self.percentage is None:
                raise ValidationError({'percentage': 'Percentage is required when unit basis is PERCENTAGE.'})
            if not self.percent_applies_to:
                raise ValidationError({'percent_applies_to': 'Must specify what the percentage applies to.'})
            if self.percent_applies_to == self.PercentAppliesTo.SPECIFIC_LINE and not self.target_line:
                raise ValidationError({'target_line': 'Target line is required for SPECIFIC_LINE percentage.'})
        else:
            if self.amount is None:
                raise ValidationError({'amount': 'Amount is required for non-percentage charges.'})


# =============================================================================
# SPOT PRICING ENVELOPE (SPE) MODELS
# =============================================================================

class SpotPricingEnvelopeDB(models.Model):
    """
    Django ORM model for Spot Pricing Envelope persistence.
    
    Guardrails:
    - shipment_context_json is immutable after creation (verified by hash)
    - PNG-only scope enforced at application level
    - Status transitions controlled by SpotEnvelopeService
    """
    
    class Status(models.TextChoices):
        DRAFT = 'draft', _('Draft')
        READY = 'ready', _('Ready')
        EXPIRED = 'expired', _('Expired')
        REJECTED = 'rejected', _('Rejected')
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT
    )
    
    # Immutable shipment context stored as JSON
    # Protected by hash verification
    shipment_context_json = models.JSONField(
        help_text="Immutable shipment context. Verified by hash on read."
    )
    shipment_context_hash = models.CharField(
        max_length=64,
        help_text="SHA256 hash of shipment_context_json for integrity verification."
    )
    
    # Conditions stored as JSON
    conditions_json = models.JSONField(
        default=dict,
        help_text="SPE conditions (uncertainty tracking)."
    )
    
    # Audit trail for SPOT trigger (Tweak #5)
    spot_trigger_reason_code = models.CharField(
        max_length=50,
        help_text="Machine-readable SPOT trigger reason code."
    )
    spot_trigger_reason_text = models.TextField(
        help_text="Human-readable SPOT trigger reason for UI display."
    )
    
    # Lifecycle
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='created_spot_envelopes'
    )
    
    expires_at = models.DateTimeField(
        help_text="SPE expires after this timestamp. Non-reusable after expiry."
    )
    
    # Link to quote (optional - SPE may exist before quote)
    quote = models.ForeignKey(
        Quote,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='spot_envelopes',
        help_text="Quote this SPE is associated with (if any)."
    )
    
    class Meta:
        db_table = 'spot_pricing_envelopes'
        ordering = ['-created_at']
        verbose_name = 'Spot Pricing Envelope'
        verbose_name_plural = 'Spot Pricing Envelopes'
    
    def __str__(self):
        return f"SPE-{str(self.id)[:8]} ({self.status})"
    
    def save(self, *args, **kwargs):
        """Compute hash on save if not set."""
        import hashlib
        import json
        
        if not self.shipment_context_hash:
            normalized = json.dumps(self.shipment_context_json, sort_keys=True)
            self.shipment_context_hash = hashlib.sha256(normalized.encode()).hexdigest()
        
        super().save(*args, **kwargs)
    
    def verify_context_integrity(self) -> bool:
        """Verify shipment context has not been modified."""
        import hashlib
        import json
        
        normalized = json.dumps(self.shipment_context_json, sort_keys=True)
        current_hash = hashlib.sha256(normalized.encode()).hexdigest()
        return current_hash == self.shipment_context_hash
    
    @property
    def is_expired(self) -> bool:
        """Check if SPE has expired."""
        return timezone.now() >= self.expires_at


class SPEChargeLineDB(models.Model):
    """
    Single charge line within a Spot Pricing Envelope.
    
    Requires source + timestamp. Anonymous values rejected.
    Extended to support destination agent quote structures.
    """
    
    class Bucket(models.TextChoices):
        AIRFREIGHT = 'airfreight', _('Airfreight')
        ORIGIN_CHARGES = 'origin_charges', _('Origin Charges')
        DESTINATION_CHARGES = 'destination_charges', _('Destination Charges')
    
    class Unit(models.TextChoices):
        PER_KG = 'per_kg', _('Per KG')
        FLAT = 'flat', _('Flat')
        PER_AWB = 'per_awb', _('Per AWB')
        PER_SHIPMENT = 'per_shipment', _('Per Shipment')
        PERCENTAGE = 'percentage', _('Percentage')
        # Extended units for destination agent quotes
        PER_TRIP = 'per_trip', _('Per Trip')
        PER_SET = 'per_set', _('Per Set')
        PER_MAN = 'per_man', _('Per Man')
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    envelope = models.ForeignKey(
        SpotPricingEnvelopeDB,
        on_delete=models.CASCADE,
        related_name='charge_lines'
    )
    
    code = models.CharField(
        max_length=50,
        help_text="Canonical internal charge code (e.g., AIRFREIGHT_SPOT)"
    )
    description = models.CharField(max_length=255)
    
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3)
    
    unit = models.CharField(max_length=20, choices=Unit.choices)
    bucket = models.CharField(max_length=30, choices=Bucket.choices)
    
    is_primary_cost = models.BooleanField(
        default=False,
        help_text="True if this is the primary airfreight cost line."
    )
    
    conditional = models.BooleanField(default=False)
    
    # === Extended fields for agent quote representation ===
    
    min_charge = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        null=True, 
        blank=True,
        help_text="Minimum charge for 'min OR per kg' logic"
    )
    
    note = models.CharField(
        max_length=500, 
        blank=True, 
        null=True,
        help_text="Narrative conditions from agent (e.g., 'if applicable')"
    )
    
    exclude_from_totals = models.BooleanField(
        default=False,
        help_text="True for invoice-value taxes that cannot be computed"
    )
    
    percentage_basis = models.CharField(
        max_length=50, 
        blank=True, 
        null=True,
        help_text="What the percentage applies to (e.g., 'commercial_invoice')"
    )
    
    # === Original fields ===
    
    source_reference = models.CharField(
        max_length=500,
        help_text="Email ID, filename, or manual note - REQUIRED"
    )
    
    entered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='+'
    )
    entered_at = models.DateTimeField()
    
    class Meta:
        db_table = 'spe_charge_lines'
        ordering = ['bucket', 'entered_at']
        verbose_name = 'SPE Charge Line'
        verbose_name_plural = 'SPE Charge Lines'
    
    def __str__(self):
        return f"{self.bucket}: {self.description} ({self.amount} {self.currency})"


class SPEAcknowledgementDB(models.Model):
    """
    Sales acknowledgement for a Spot Pricing Envelope.
    
    Required before pricing can proceed.
    """
    
    ACKNOWLEDGEMENT_STATEMENT = "I acknowledge this is a conditional SPOT quote and not guaranteed"
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    envelope = models.OneToOneField(
        SpotPricingEnvelopeDB,
        on_delete=models.CASCADE,
        related_name='acknowledgement'
    )
    
    acknowledged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='+'
    )
    acknowledged_at = models.DateTimeField()
    
    statement = models.TextField(
        default=ACKNOWLEDGEMENT_STATEMENT,
        help_text="The acknowledgement statement agreed to."
    )
    
    class Meta:
        db_table = 'spe_acknowledgements'
        verbose_name = 'SPE Acknowledgement'
        verbose_name_plural = 'SPE Acknowledgements'
    
    def __str__(self):
        return f"Acknowledgement for SPE-{str(self.envelope_id)[:8]}"


class SPEManagerApprovalDB(models.Model):
    """
    Manager approval for high-risk SPOT quotes.
    
    Required per SpotApprovalPolicy for DG, multi-leg, low-margin, etc.
    """
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    envelope = models.OneToOneField(
        SpotPricingEnvelopeDB,
        on_delete=models.CASCADE,
        related_name='manager_approval'
    )
    
    approved = models.BooleanField()
    
    manager = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='+'
    )
    decision_at = models.DateTimeField()
    
    comment = models.TextField(
        null=True, blank=True,
        help_text="Optional comment from manager."
    )
    
    class Meta:
        db_table = 'spe_manager_approvals'
        verbose_name = 'SPE Manager Approval'
        verbose_name_plural = 'SPE Manager Approvals'
    
    def __str__(self):
        status = "Approved" if self.approved else "Rejected"
        return f"{status} by {self.manager} for SPE-{str(self.envelope_id)[:8]}"
