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
        FINAL = 'FINAL', _('Finalized')
        SENT = 'SENT', _('Sent to Customer')
        ACCEPTED = 'ACCEPTED', _('Accepted')
        LOST = 'LOST', _('Lost')
        EXPIRED = 'EXPIRED', _('Expired')
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
class SpotChargeLine(models.Model):
    """
    Freeform charge line for bucket-based spot rate entry.
    Supports flexible agent rate structures from any country/format.
    """
    
    class Bucket(models.TextChoices):
        ORIGIN = 'ORIGIN', _('Origin Charges')
        FREIGHT = 'FREIGHT', _('Freight')
        DESTINATION = 'DESTINATION', _('Destination Charges')
    
    class UnitBasis(models.TextChoices):
        PER_KG = 'PER_KG', _('Per KG')
        PER_SHIPMENT = 'PER_SHIPMENT', _('Per Shipment')
        PER_AWB = 'PER_AWB', _('Per AWB')
        MINIMUM = 'MINIMUM', _('Minimum Charge')
        PER_HOUR = 'PER_HOUR', _('Per Hour')
        PERCENTAGE = 'PERCENTAGE', _('Percentage')
        OTHER = 'OTHER', _('Other')
    
    class PercentAppliesTo(models.TextChoices):
        SPECIFIC_LINE = 'SPECIFIC_LINE', _('Specific Charge Line')
        BUCKET_ORIGIN = 'BUCKET_ORIGIN', _('Origin Bucket')
        BUCKET_FREIGHT = 'BUCKET_FREIGHT', _('Freight Bucket')
        BUCKET_DESTINATION = 'BUCKET_DESTINATION', _('Destination Bucket')
        BUCKET_TOTAL = 'BUCKET_TOTAL', _('Total of All Buckets')
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    quote = models.ForeignKey(
        Quote,
        on_delete=models.CASCADE,
        related_name='spot_charges',
        help_text="The quote this spot charge belongs to."
    )
    
    bucket = models.CharField(
        max_length=20,
        choices=Bucket.choices,
        help_text="Which cost bucket this charge belongs to."
    )
    
    description = models.CharField(
        max_length=255,
        help_text="Freeform description exactly as received from agent."
    )
    
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Charge amount. Null when unit_basis is PERCENTAGE."
    )
    
    currency = models.CharField(
        max_length=3,
        help_text="3-letter ISO currency code (e.g., USD, AUD, PGK)."
    )
    
    unit_basis = models.CharField(
        max_length=50,
        choices=UnitBasis.choices,
        help_text="How this charge is calculated."
    )
    
    min_charge = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Minimum charge amount for PER_KG rates. If rate × weight is less than this, the minimum applies."
    )
    
    # FSC / Percentage fields
    percentage = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Percentage value (e.g., 20.00 for 20%). Required when unit_basis is PERCENTAGE."
    )
    
    percent_applies_to = models.CharField(
        max_length=30,
        choices=PercentAppliesTo.choices,
        null=True,
        blank=True,
        help_text="What the percentage applies to. Required when unit_basis is PERCENTAGE."
    )
    
    target_line = models.ForeignKey(
        'self',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='dependent_charges',
        help_text="Target line for SPECIFIC_LINE percentage calculation."
    )
    
    notes = models.TextField(
        blank=True,
        help_text="Optional notes about this charge."
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['bucket', 'created_at']
        verbose_name = 'Spot Charge Line'
        verbose_name_plural = 'Spot Charge Lines'
    
    def __str__(self):
        return f"{self.bucket}: {self.description} ({self.amount} {self.currency})"
    
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
