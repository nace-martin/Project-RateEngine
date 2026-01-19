import uuid
from django.db import models
from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
# from .models import Quote

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
        'quotes.Quote',
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
    
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
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
