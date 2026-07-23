# backend/quotes/models.py

import uuid
from datetime import timedelta

from django.conf import settings  # For AUTH_USER_MODEL
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

# Import models needed for V3 ForeignKeys
from parties.models import Branch, Company, Contact, Department, Organization
# --- UPDATED IMPORT ---
from core.models import Policy, FxSnapshot, Location
from core.commodity import COMMODITY_CHOICES, DEFAULT_COMMODITY_CODE
# --- END UPDATE ---
from services.models import MODE_CHOICES, ServiceComponent, SERVICE_SCOPE_CHOICES
from pricing_v4.contracts.charge_context import JourneyDirection, JourneyPattern, LegRole, ProductCodeDomain, TransportMode


# --- V3 Refactored Quote Model ---
# Re-export SPOT models for backward compatibility
from .spot_models import (
    SpotPricingEnvelopeDB,  # noqa: F401
    SPEChargeLineDB,        # noqa: F401
    SPEAcknowledgementDB,   # noqa: F401
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
    branch = models.ForeignKey(
        Branch,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="quotes",
        help_text="Future RBAC branch scope. Nullable until backfilled and enforced.",
    )
    department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="quotes",
        help_text="Future RBAC department scope. Nullable until backfilled and enforced.",
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="owned_quotes",
        help_text="Future RBAC record owner. Nullable until ownership rules are enforced.",
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
    opportunity = models.ForeignKey(
        "crm.Opportunity",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="quotes",
        help_text="CRM opportunity this quote supports, if any.",
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
        is_create = self._state.adding
        if is_create and self.created_by_id:
            from accounts.scope import resolve_create_scope_for_user

            create_scope = resolve_create_scope_for_user(self.created_by)
            if self.owner_id is None:
                self.owner = create_scope.owner
            if self.organization_id is None:
                self.organization = create_scope.organization
            if self.branch_id is None:
                self.branch = create_scope.branch
            if self.department_id is None:
                self.department = create_scope.department

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


class RouteAutomationPolicyDB(models.Model):
    """Audited dark-mode route automation policy.

    Missing policy means disabled. Phase 16E-A seeds supported patterns as disabled
    only; no route is enabled by this PR.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    route_pattern = models.CharField(max_length=20, choices=[(item.value, item.value) for item in JourneyPattern], unique=True, db_index=True)
    enabled = models.BooleanField(default=False, db_index=True)
    disabled_reason = models.TextField(blank=True, default="")
    effective_from = models.DateField(null=True, blank=True)
    effective_until = models.DateField(null=True, blank=True)
    required_rate_gate_json = models.JSONField(default=dict, blank=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'route_automation_policies'
        ordering = ['route_pattern']
        verbose_name = 'Route Automation Policy'
        verbose_name_plural = 'Route Automation Policies'

    def clean(self):
        super().clean()
        if self.enabled:
            raise ValidationError({'enabled': 'Phase 16E-A does not enable route automation.'})
        if not self.disabled_reason:
            raise ValidationError({'disabled_reason': 'Disabled route policies require an explicit reason.'})

    def __str__(self):
        return f"{self.route_pattern}: {'enabled' if self.enabled else 'disabled'}"


class ShipmentJourneyDB(models.Model):
    class Status(models.TextChoices):
        PLANNED = 'PLANNED', 'Planned'
        NEEDS_REVIEW = 'NEEDS_REVIEW', 'Needs review'
        PRICED = 'PRICED', 'Priced'
        FINALIZED = 'FINALIZED', 'Finalized'
        SUPERSEDED = 'SUPERSEDED', 'Superseded'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    quote = models.ForeignKey(Quote, on_delete=models.CASCADE, null=True, blank=True, related_name='shipment_journeys')
    spot_envelope = models.ForeignKey('quotes.SpotPricingEnvelopeDB', on_delete=models.CASCADE, null=True, blank=True, related_name='shipment_journeys')
    revision = models.PositiveIntegerField()
    direction = models.CharField(max_length=10, choices=[(item.value, item.value) for item in JourneyDirection], blank=True, default='')
    pattern = models.CharField(max_length=20, choices=[(item.value, item.value) for item in JourneyPattern], blank=True, default='')
    gateway_code = models.CharField(max_length=10, blank=True, default='POM')
    customer_origin_code = models.CharField(max_length=20, blank=True, default='')
    customer_destination_code = models.CharField(max_length=20, blank=True, default='')
    route_policy_key = models.CharField(max_length=50, blank=True, default='')
    rule_version = models.CharField(max_length=80)
    input_fingerprint = models.CharField(max_length=64, db_index=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PLANNED, db_index=True)
    blockers_json = models.JSONField(default=list, blank=True)
    supersedes = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='superseded_by')
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    finalized_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'shipment_journeys'
        ordering = ['-created_at', '-revision']
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quote__isnull=False) | models.Q(spot_envelope__isnull=False),
                name='shipment_journey_parent_required',
            ),
            models.UniqueConstraint(fields=['quote', 'revision'], condition=models.Q(quote__isnull=False), name='uniq_shipment_journey_quote_revision'),
            models.UniqueConstraint(fields=['spot_envelope', 'revision'], condition=models.Q(spot_envelope__isnull=False), name='uniq_shipment_journey_spot_revision'),
        ]

    def clean(self):
        super().clean()
        if not self.quote_id and not self.spot_envelope_id:
            raise ValidationError('ShipmentJourneyDB requires either quote or SPOT envelope parent.')
        if self.status == self.Status.FINALIZED and self.finalized_at is None:
            raise ValidationError({'finalized_at': 'Finalized shipment journeys require finalized_at.'})
        if self.finalized_at is not None and self.status != self.Status.FINALIZED:
            raise ValidationError({'status': 'finalized_at is only valid when status is FINALIZED.'})

    def _validate_finalized_immutability(self):
        if not self.pk:
            return
        previous = type(self).objects.filter(pk=self.pk).first()
        if not previous or previous.status != self.Status.FINALIZED:
            return
        immutable_fields = [
            'revision', 'direction', 'pattern', 'gateway_code', 'customer_origin_code',
            'customer_destination_code', 'route_policy_key', 'rule_version', 'input_fingerprint',
            'status', 'blockers_json', 'supersedes_id', 'created_by_id', 'finalized_at',
        ]
        for field_name in immutable_fields:
            if getattr(previous, field_name) != getattr(self, field_name):
                raise ValidationError('Finalized shipment journey revisions are immutable.')
        for parent_field in ['quote_id', 'spot_envelope_id']:
            previous_value = getattr(previous, parent_field)
            current_value = getattr(self, parent_field)
            if previous_value and previous_value != current_value:
                raise ValidationError('Finalized shipment journey parent links are immutable.')
            if previous_value is None and current_value is None:
                continue
            if previous_value is None and current_value:
                continue

    def save(self, *args, **kwargs):
        self.full_clean()
        self._validate_finalized_immutability()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.status == self.Status.FINALIZED:
            raise ValidationError('Finalized shipment journey revisions cannot be deleted.')
        return super().delete(*args, **kwargs)

    def __str__(self):
        return f"Journey {self.revision} {self.pattern or 'UNSUPPORTED'}"


class ShipmentLegDB(models.Model):
    class Status(models.TextChoices):
        PLANNED = 'PLANNED', 'Planned'
        NEEDS_REVIEW = 'NEEDS_REVIEW', 'Needs review'
        PRICED = 'PRICED', 'Priced'
        FINALIZED = 'FINALIZED', 'Finalized'
        SUPERSEDED = 'SUPERSEDED', 'Superseded'

    class RateCoverageStatus(models.TextChoices):
        NOT_CHECKED = 'NOT_CHECKED', 'Not checked'
        MISSING = 'MISSING', 'Missing'
        AVAILABLE = 'AVAILABLE', 'Available'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    journey = models.ForeignKey(ShipmentJourneyDB, on_delete=models.CASCADE, related_name='legs')
    leg_key = models.CharField(max_length=120)
    sequence = models.PositiveIntegerField()
    role = models.CharField(max_length=32, choices=[(item.value, item.value) for item in LegRole])
    transport_mode = models.CharField(max_length=32, choices=[(item.value, item.value) for item in TransportMode])
    origin_code = models.CharField(max_length=20)
    destination_code = models.CharField(max_length=20)
    product_code_domain = models.CharField(max_length=10, choices=[(item.value, item.value) for item in ProductCodeDomain])
    required = models.BooleanField(default=True)
    service_scope = models.CharField(max_length=20, blank=True, default='')
    chargeable_weight = models.DecimalField(max_digits=12, decimal_places=3, null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PLANNED, db_index=True)
    rate_coverage_status = models.CharField(max_length=20, choices=RateCoverageStatus.choices, default=RateCoverageStatus.NOT_CHECKED, db_index=True)
    blockers_json = models.JSONField(default=list, blank=True)

    class Meta:
        db_table = 'shipment_legs'
        ordering = ['journey', 'sequence']
        constraints = [
            models.UniqueConstraint(fields=['journey', 'sequence'], name='uniq_shipment_leg_journey_sequence'),
            models.UniqueConstraint(fields=['journey', 'leg_key'], name='uniq_shipment_leg_journey_leg_key'),
        ]

    def clean(self):
        super().clean()
        if self.journey_id:
            parent = ShipmentJourneyDB.objects.get(pk=self.journey_id)
            if parent.status == ShipmentJourneyDB.Status.FINALIZED:
                raise ValidationError('Finalized shipment journey legs are immutable.')
        if self.sequence < 1:
            raise ValidationError({'sequence': 'Leg sequence starts at 1.'})
        if self.role == LegRole.INTERNATIONAL_IMPORT.value and self.destination_code != 'POM':
            raise ValidationError({'destination_code': 'International import legs must end at POM.'})
        if self.role == LegRole.INTERNATIONAL_EXPORT.value and self.origin_code != 'POM':
            raise ValidationError({'origin_code': 'International export legs must start at POM.'})
        if self.role == LegRole.DOMESTIC_ON_FORWARDING.value and self.origin_code != 'POM':
            raise ValidationError({'origin_code': 'Domestic on-forwarding legs must start at POM.'})
        if self.role == LegRole.DOMESTIC_PRE_CARRIAGE.value and self.destination_code != 'POM':
            raise ValidationError({'destination_code': 'Domestic pre-carriage legs must end at POM.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        parent = ShipmentJourneyDB.objects.get(pk=self.journey_id) if self.journey_id else None
        if parent and parent.status == ShipmentJourneyDB.Status.FINALIZED:
            raise ValidationError('Finalized shipment journey legs are immutable.')
        return super().delete(*args, **kwargs)

    def __str__(self):
        return self.leg_key


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
    description = models.CharField(
        max_length=500, 
        null=True, 
        blank=True,
        help_text="Custom display name for this line (e.g. from AI extraction). Falls back to component description if null."
    )
    leg = models.CharField(max_length=20, null=True, blank=True, help_text="ORIGIN, MAIN, or DESTINATION")
    bucket = models.CharField(max_length=50, null=True, blank=True, help_text="e.g., origin_charges, airfreight, destination_charges")

    # --- V3 Audit Fields (from _save_quote_v3) ---
    cost_source = models.CharField(max_length=50, null=True, blank=True)
    cost_source_description = models.CharField(max_length=255, null=True, blank=True)
    is_rate_missing = models.BooleanField(default=False)
    product_code = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        help_text="Persisted canonical product code used in quote_result.",
    )
    component = models.CharField(
        max_length=30,
        null=True,
        blank=True,
        help_text="Persisted canonical quote_result component.",
    )
    basis = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        help_text="Persisted canonical quote_result basis label.",
    )
    rule_family = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        help_text="Persisted canonical pricing calculation family.",
    )
    service_family = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        help_text="Optional semantic/commercial family kept separate from rule_family.",
    )
    unit_type = models.CharField(
        max_length=30,
        null=True,
        blank=True,
        help_text="Persisted canonical quote_result unit type.",
    )
    rate = models.DecimalField(
        max_digits=18,
        decimal_places=6,
        null=True,
        blank=True,
        help_text="Persisted canonical line rate when a stable rate is available.",
    )
    rate_source = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        help_text="Persisted canonical quote_result rate source.",
    )
    canonical_cost_source = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        help_text="Persisted canonical quote_result cost source.",
    )
    is_spot_sourced = models.BooleanField(
        null=True,
        blank=True,
        help_text="Persisted canonical SPOT-source flag.",
    )
    is_manual_override = models.BooleanField(
        null=True,
        blank=True,
        help_text="Persisted canonical manual-override flag.",
    )
    calculation_notes = models.TextField(
        null=True,
        blank=True,
        help_text="Persisted canonical line-level audit notes.",
    )
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

    # Phase 16E-A dark-mode journey audit context. Nullable to avoid historical
    # backfills and non-behavioural until later orchestration phases.
    journey_leg = models.ForeignKey(
        'quotes.ShipmentLegDB',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='quote_lines',
    )
    charge_context_json = models.JSONField(default=dict, blank=True)
    product_code_resolution_audit_json = models.JSONField(default=dict, blank=True)

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
    service_notes = models.TextField(
        null=True,
        blank=True,
        help_text="Persisted canonical service-facing notes.",
    )
    customer_notes = models.TextField(
        null=True,
        blank=True,
        help_text="Persisted canonical customer-facing notes.",
    )
    internal_notes = models.TextField(
        null=True,
        blank=True,
        help_text="Persisted canonical internal notes.",
    )
    warnings_json = models.JSONField(
        default=list,
        blank=True,
        help_text="Persisted canonical quote_result warnings.",
    )
    audit_metadata_json = models.JSONField(
        default=dict,
        blank=True,
        help_text="Persisted structured audit metadata for quote_result.",
    )
    
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
