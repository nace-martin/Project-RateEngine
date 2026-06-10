# backend/quotes/spot_learning_models.py
"""
SPOT Resolution Learning Models

These models support the confidence-based self-learning resolution system
for SPOT charge exceptions. Instead of blocking Sales users from progressing
quotes, the system learns from every user resolution decision and uses that
history to auto-resolve, suggest, or ask in future encounters.

SpotResolutionLearningEvent: Immutable, append-only record of every
    resolution decision. This is the training corpus for confidence scoring.

SpotChargeMappingMemory: Aggregated learned/locked mappings derived from
    learning events. Manager/Admin can lock mappings to prevent learning
    from overriding them.
"""

import uuid
from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _


class SpotResolutionLearningEvent(models.Model):
    """
    Immutable record of a SPOT charge resolution decision.

    Append-only. Never mutated after creation.
    Used to train confidence scoring for future auto-resolution.

    Each row records:
    - What the system saw (source label, normalization status, suggestion)
    - What the user decided (resolved product code, keep/remove conditional)
    - Shipment context (route, mode, supplier) for contextual scoring
    """

    class ResolutionType(models.TextChoices):
        MANUAL_PRODUCT_CODE = 'MANUAL_PRODUCT_CODE', _('Manual ProductCode Selection')
        CONFIRM_PATTERN_MATCH = 'CONFIRM_PATTERN_MATCH', _('Confirm Pattern Match')
        OVERRIDE_SUGGESTION = 'OVERRIDE_SUGGESTION', _('Override System Suggestion')
        CONDITIONAL_KEEP = 'CONDITIONAL_KEEP', _('Conditional Charge Kept')
        CONDITIONAL_REMOVE = 'CONDITIONAL_REMOVE', _('Conditional Charge Removed')
        AUTO_RESOLVED = 'AUTO_RESOLVED', _('System Auto-Resolved')

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # --- What was resolved ---
    charge_line = models.ForeignKey(
        'quotes.SPEChargeLineDB',
        on_delete=models.SET_NULL,
        null=True,
        related_name='learning_events',
        help_text='The charge line that was resolved.',
    )
    envelope = models.ForeignKey(
        'quotes.SpotPricingEnvelopeDB',
        on_delete=models.SET_NULL,
        null=True,
        related_name='learning_events',
        help_text='The SPE this resolution belongs to.',
    )

    # --- The input signal (what the system saw) ---
    source_label = models.CharField(
        max_length=255,
        help_text='Original raw charge label from the source content.',
    )
    normalized_label = models.CharField(
        max_length=255,
        db_index=True,
        help_text='Deterministically normalized label for matching.',
    )
    bucket = models.CharField(
        max_length=30,
        help_text='Charge bucket: airfreight, origin_charges, destination_charges.',
    )
    normalization_status_before = models.CharField(
        max_length=20,
        help_text='Normalization status before user intervention (MATCHED, AMBIGUOUS, UNMAPPED).',
    )
    normalization_method_before = models.CharField(
        max_length=20,
        blank=True,
        default='',
        help_text='Normalization method before user intervention (EXACT_ALIAS, PATTERN_ALIAS, NONE).',
    )
    system_suggested_product_code = models.ForeignKey(
        'pricing_v4.ProductCode',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+',
        help_text='ProductCode the system suggested (from deterministic normalization), if any.',
    )

    # --- The output decision (what the user chose) ---
    resolution_type = models.CharField(
        max_length=30,
        choices=ResolutionType.choices,
        db_index=True,
    )
    resolved_product_code = models.ForeignKey(
        'pricing_v4.ProductCode',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+',
        help_text='ProductCode the user selected (null for conditional REMOVE).',
    )
    user_agreed_with_suggestion = models.BooleanField(
        default=False,
        help_text='True when user confirmed the system suggestion without changing it.',
    )

    # --- Shipment context signals (denormalized for fast querying) ---
    origin_code = models.CharField(max_length=5, blank=True, default='', db_index=True)
    destination_code = models.CharField(max_length=5, blank=True, default='', db_index=True)
    mode = models.CharField(max_length=10, blank=True, default='', db_index=True)
    shipment_type = models.CharField(max_length=10, blank=True, default='', db_index=True)
    service_scope = models.CharField(max_length=10, blank=True, default='')
    source_kind = models.CharField(
        max_length=20, blank=True, default='', db_index=True,
        help_text='Source batch kind: AIRLINE, AGENT, MANUAL, OTHER.',
    )
    source_label_supplier = models.CharField(
        max_length=255, blank=True, default='',
        help_text='Source batch label (agent/airline name).',
    )

    # --- Audit ---
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='+',
    )
    resolved_at = models.DateTimeField(auto_now_add=True, db_index=True)
    confidence_at_resolution = models.FloatField(
        null=True,
        blank=True,
        help_text='Confidence score at the time of resolution (null for pre-learning / cold-start).',
    )

    class Meta:
        db_table = 'spot_resolution_learning_events'
        ordering = ['-resolved_at']
        verbose_name = 'Spot Resolution Learning Event'
        verbose_name_plural = 'Spot Resolution Learning Events'
        indexes = [
            models.Index(
                fields=['normalized_label', 'bucket', 'shipment_type'],
                name='srl_label_bucket_type_idx',
            ),
            models.Index(
                fields=['normalized_label', 'resolved_product_code'],
                name='srl_label_product_idx',
            ),
        ]

    def __str__(self):
        return (
            f"LearningEvent {str(self.id)[:8]}: "
            f"{self.normalized_label} -> {self.resolution_type}"
        )


class SpotChargeMappingMemory(models.Model):
    """
    Aggregated learned/locked charge mapping.

    Represents a stable mapping from a normalized charge label (in context)
    to a canonical ProductCode. Derived from SpotResolutionLearningEvent
    frequency and consensus.

    Manager/Admin can lock a mapping to prevent future learning events from
    overriding it. Locked mappings act as deterministic overrides similar to
    ChargeAlias but scoped to SPOT resolution context.

    Schema-only for Phase 10.3a. Populated by future slices (10.3c+).
    """

    class Status(models.TextChoices):
        LEARNED = 'LEARNED', _('Learned')
        LOCKED = 'LOCKED', _('Locked')
        RETIRED = 'RETIRED', _('Retired')

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # --- Mapping identity ---
    normalized_label = models.CharField(
        max_length=255,
        db_index=True,
        help_text='Deterministically normalized charge label.',
    )
    bucket = models.CharField(
        max_length=30,
        blank=True,
        default='',
        help_text='Charge bucket scope (empty = any bucket).',
    )
    shipment_type = models.CharField(
        max_length=10,
        blank=True,
        default='',
        db_index=True,
        help_text='Shipment type scope (empty = any type).',
    )
    product_code = models.ForeignKey(
        'pricing_v4.ProductCode',
        on_delete=models.PROTECT,
        related_name='spot_mapping_memories',
        help_text='Canonical ProductCode this label resolves to.',
    )

    # --- Confidence and status ---
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.LEARNED,
        db_index=True,
    )
    confidence_score = models.FloatField(
        default=0.0,
        help_text='Latest computed confidence score for this mapping.',
    )
    event_count = models.PositiveIntegerField(
        default=0,
        help_text='Number of learning events supporting this mapping.',
    )
    last_used_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='Timestamp of the most recent learning event for this mapping.',
    )

    # --- Lock management ---
    locked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+',
        help_text='Manager/Admin who locked this mapping.',
    )
    locked_at = models.DateTimeField(
        null=True,
        blank=True,
    )
    lock_note = models.TextField(
        blank=True,
        default='',
        help_text='Reason for locking this mapping.',
    )

    # --- Timestamps ---
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'spot_charge_mapping_memory'
        ordering = ['-confidence_score', '-event_count']
        verbose_name = 'Spot Charge Mapping Memory'
        verbose_name_plural = 'Spot Charge Mapping Memories'
        indexes = [
            models.Index(
                fields=['normalized_label', 'bucket', 'shipment_type', 'status'],
                name='scmm_lookup_idx',
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['normalized_label', 'bucket', 'shipment_type', 'product_code'],
                name='scmm_unique_mapping',
            ),
        ]

    def __str__(self):
        return (
            f"Memory {str(self.id)[:8]}: "
            f"{self.normalized_label} -> {self.product_code.code} "
            f"({self.status}, {self.confidence_score:.2f})"
        )
