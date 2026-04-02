import uuid
from types import SimpleNamespace
from django.db import models
from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
# from .models import Quote

# =============================================================================
# SPOT PRICING ENVELOPE (SPE) MODELS
# =============================================================================


def _normalize_spot_missing_components(raw_value):
    if raw_value is None:
        return None
    if isinstance(raw_value, str):
        raw_list = [item.strip() for item in raw_value.split(",")]
    elif isinstance(raw_value, (list, tuple, set)):
        raw_list = list(raw_value)
    else:
        return []
    return [str(item).upper() for item in raw_list if str(item).strip()]


def _normalize_spot_shipment_context(ctx: dict, quote_payment_term=None) -> dict:
    normalized = dict(ctx or {})
    origin_code = str(normalized.get("origin_code") or "").upper()
    destination_code = str(normalized.get("destination_code") or "").upper()
    normalized["origin_code"] = origin_code
    normalized["destination_code"] = destination_code

    try:
        from quotes.spot_services import ScopeValidator

        origin_country, destination_country = ScopeValidator.normalize_countries(
            origin_country=normalized.get("origin_country"),
            destination_country=normalized.get("destination_country"),
            origin_airport=origin_code,
            destination_airport=destination_code,
        )
        normalized["origin_country"] = origin_country
        normalized["destination_country"] = destination_country
    except Exception:
        pass

    payment_term = str(
        normalized.get("payment_term")
        or quote_payment_term
        or ""
    ).strip().upper()
    if payment_term in {"PREPAID", "COLLECT"}:
        normalized["payment_term"] = payment_term
    elif "payment_term" in normalized:
        normalized.pop("payment_term", None)

    normalized["missing_components"] = _normalize_spot_missing_components(
        normalized.get("missing_components")
    )
    return normalized


def _shipment_type_from_spot_context(ctx: dict) -> str:
    origin_country = str(ctx.get("origin_country") or "").upper()
    destination_country = str(ctx.get("destination_country") or "").upper()
    if origin_country == "PG" and destination_country == "PG":
        return "DOMESTIC"
    if origin_country == "PG":
        return "EXPORT"
    return "IMPORT"


def resolve_spot_missing_components(
    ctx: dict,
    charge_lines,
    *,
    quote_payment_term=None,
) -> list[str] | None:
    normalized = _normalize_spot_shipment_context(
        ctx,
        quote_payment_term=quote_payment_term,
    )
    stored_missing = normalized.get("missing_components")
    origin_code = normalized.get("origin_code") or ""
    destination_code = normalized.get("destination_code") or ""
    if not origin_code or not destination_code:
        return stored_missing

    service_scope = str(normalized.get("service_scope") or "P2P")
    shipment_type = _shipment_type_from_spot_context(normalized)
    payment_term = normalized.get("payment_term")

    try:
        from quotes.completeness import evaluate_from_lines
        from quotes.spot_services import RateAvailabilityService

        availability = RateAvailabilityService.get_availability(
            origin_airport=origin_code,
            destination_airport=destination_code,
            direction=shipment_type,
            service_scope=service_scope,
            payment_term=payment_term,
        )

        availability_buckets = {
            "FREIGHT": "airfreight",
            "ORIGIN_LOCAL": "origin_charges",
            "DESTINATION_LOCAL": "destination_charges",
        }

        coverage_lines = [
            SimpleNamespace(bucket=bucket, is_rate_missing=False, is_informational=False)
            for component, bucket in availability_buckets.items()
            if availability.get(component)
        ]

        for line in charge_lines or ():
            amount = getattr(line, "amount", None)
            if amount is None or amount <= 0:
                continue
            if getattr(line, "conditional", False):
                continue
            if getattr(line, "exclude_from_totals", False):
                continue
            coverage_lines.append(
                SimpleNamespace(
                    bucket=getattr(line, "bucket", None),
                    is_rate_missing=False,
                    is_informational=False,
                )
            )

        coverage = evaluate_from_lines(coverage_lines, shipment_type, service_scope)
        return coverage.missing_required
    except Exception:
        return stored_missing

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
    resolved_missing_components = models.JSONField(
        default=list,
        help_text="Cached list of SPOT components still missing actionable charges."
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
        if self._state.adding and not self.resolved_missing_components:
            self.resolved_missing_components = list(
                resolve_spot_missing_components(
                    self.shipment_context_json,
                    (),
                    quote_payment_term=getattr(self.quote, "payment_term", None),
                )
                or []
            )
        
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

    def refresh_resolved_missing_components(self, *, save: bool = True) -> list[str]:
        resolved = list(
            resolve_spot_missing_components(
                self.shipment_context_json,
                self.charge_lines.all(),
                quote_payment_term=getattr(self.quote, "payment_term", None),
            )
            or []
        )
        self.resolved_missing_components = resolved
        if save and self.pk:
            type(self).objects.filter(pk=self.pk).update(
                resolved_missing_components=resolved
            )
        return resolved


class SPESourceBatchDB(models.Model):
    """Source bundle for one airline/agent/manual intake within an SPE."""

    class SourceKind(models.TextChoices):
        AIRLINE = 'AIRLINE', _('Airline')
        AGENT = 'AGENT', _('Agent')
        MANUAL = 'MANUAL', _('Manual')
        OTHER = 'OTHER', _('Other')

    class SourceType(models.TextChoices):
        TEXT = 'TEXT', _('Text')
        PDF = 'PDF', _('PDF')
        EMAIL = 'EMAIL', _('Email')
        MANUAL = 'MANUAL', _('Manual')

    class TargetBucket(models.TextChoices):
        AIRFREIGHT = 'airfreight', _('Airfreight')
        ORIGIN_CHARGES = 'origin_charges', _('Origin Charges')
        DESTINATION_CHARGES = 'destination_charges', _('Destination Charges')
        MIXED = 'mixed', _('Mixed')

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    envelope = models.ForeignKey(
        SpotPricingEnvelopeDB,
        on_delete=models.CASCADE,
        related_name='source_batches',
    )
    source_kind = models.CharField(max_length=20, choices=SourceKind.choices, default=SourceKind.AGENT)
    source_type = models.CharField(max_length=20, choices=SourceType.choices, default=SourceType.TEXT)
    target_bucket = models.CharField(max_length=30, choices=TargetBucket.choices, default=TargetBucket.MIXED)
    label = models.CharField(max_length=255, blank=True, default="")
    source_reference = models.CharField(max_length=500, blank=True, default="")
    raw_text = models.TextField(blank=True, default="")
    file_name = models.CharField(max_length=255, blank=True, default="")
    file_content_type = models.CharField(max_length=100, blank=True, default="")
    analysis_summary_json = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'spe_source_batches'
        ordering = ['created_at']
        verbose_name = 'SPE Source Batch'
        verbose_name_plural = 'SPE Source Batches'

    def __str__(self):
        return self.label or f"{self.source_kind} {self.source_type} source"


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

    class CalculationType(models.TextChoices):
        FLAT = 'flat', _('Flat')
        PER_UNIT = 'per_unit', _('Per Unit')
        MIN_OR_PER_UNIT = 'min_or_per_unit', _('Min Or Per Unit')
        PERCENT_OF = 'percent_of', _('Percent Of Basis')
        PER_LINE_WITH_CAP = 'per_line_with_cap', _('Per Line With Cap')
        MAX_OR_PER_UNIT = 'max_or_per_unit', _('Max Or Per Unit')

    class UnitType(models.TextChoices):
        KG = 'kg', _('Kilogram')
        SHIPMENT = 'shipment', _('Shipment')
        AWB = 'awb', _('AWB')
        TRIP = 'trip', _('Trip')
        SET = 'set', _('Set')
        LINE = 'line', _('Line')
        MAN = 'man', _('Man')
        CBM = 'cbm', _('CBM')
        RT = 'rt', _('Revenue Ton')
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    envelope = models.ForeignKey(
        SpotPricingEnvelopeDB,
        on_delete=models.CASCADE,
        related_name='charge_lines'
    )
    source_batch = models.ForeignKey(
        SPESourceBatchDB,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='charge_lines',
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

    # === Canonical rule representation ===
    calculation_type = models.CharField(
        max_length=30,
        choices=CalculationType.choices,
        blank=True,
        null=True,
        help_text="Rule type for canonical evaluation"
    )
    unit_type = models.CharField(
        max_length=20,
        choices=UnitType.choices,
        blank=True,
        null=True,
        help_text="Quantity basis for PER_UNIT style calculations"
    )
    rate = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Per-unit or flat rate in charge currency"
    )
    min_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Minimum amount for composite rules"
    )
    max_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Maximum amount for composite rules"
    )
    percent = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Percent value for percentage rules"
    )
    percent_basis = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        help_text="Basis key for percentage calculation (e.g., 'freight')"
    )
    rule_meta = models.JSONField(
        default=dict,
        blank=True,
        help_text="Extensible rule params (e.g., cap thresholds)"
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

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.envelope_id:
            self.envelope.refresh_resolved_missing_components(save=True)


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
    Legacy manager approval record retained for existing data.
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
        help_text="Optional historical comment from manager."
    )
    
    class Meta:
        db_table = 'spe_manager_approvals'
        verbose_name = 'SPE Manager Approval'
        verbose_name_plural = 'SPE Manager Approvals'
    
    def __str__(self):
        status = "Approved" if self.approved else "Rejected"
        return f"{status} by {self.manager} for SPE-{str(self.envelope_id)[:8]}"
