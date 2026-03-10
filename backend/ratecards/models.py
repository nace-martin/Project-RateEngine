# backend/ratecards/models.py

import uuid
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from django.utils import timezone
from core.models import City, Airport, Port
from parties.models import Company
from services.models import ServiceComponent, UNIT_CHOICES as SERVICE_UNIT_CHOICES

# Simplified for our focus on the AIR module.
MODE_CHOICES = [
    ('AIR', _('Air')),
    # ('SEA', _('Sea')),  # Defer until Sea module is built
    # ('ROAD', _('Road')), # Defer until Road module is built
]

SHIPMENT_TYPE_CHOICES = [
    ('GENERAL', _('General Cargo')),
    # ('FCL', _('FCL')), # This is SEA
    # ('LCL', _('LCL')), # This is SEA
    # ('BULK', _('Bulk')), # This is SEA
]


# ##############################################################################
# V3 PARTNER RATE CARD MODELS (BUY-SIDE)
# ##############################################################################

class PartnerRateCard(models.Model):
    """
    The top-level "filing cabinet" for a partner's rate card.
    Defines who it's from, the currency, and its validity.
    """
    supplier = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="partner_rate_cards",
        help_text="The partner/supplier these rates are from."
    )
    name = models.CharField(
        max_length=255,
        unique=True,
        help_text="A descriptive name, e.g., 'EFM AUD Import Rates 2025'"
    )
    currency_code = models.CharField(
        max_length=3,
        help_text="The 3-letter ISO currency code of the rates (e.g., AUD, USD)."
    )
    valid_from = models.DateField(
        null=True, blank=True,
        help_text="The date this rate card becomes active."
    )
    valid_until = models.DateField(
        null=True, blank=True,
        help_text="The date this rate card expires."
    )
    
    service_level = models.CharField(
        max_length=20,
        choices=[
            ('DIRECT', 'Direct'),
            ('VIA_BNE', 'Via Brisbane'),
            ('VIA_SYD', 'Via Sydney'),
            ('STANDARD', 'Standard'),
        ],
        default='STANDARD',
        db_index=True,
        help_text="Service level for routing (e.g., DIRECT for narrow-body, VIA_BNE for wide-body)"
    )
    
    route_lane_constraint = models.ForeignKey(
        'core.RouteLaneConstraint',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='rate_cards',
        help_text="Aircraft/routing constraint for this rate card"
    )
    
    RATE_TYPE_CHOICES = [
        ('BUY_RATE', 'Buy Rate (Cost)'),
        ('SELL_RATE', 'Sell Rate'),
    ]
    rate_type = models.CharField(
        max_length=20,
        choices=RATE_TYPE_CHOICES,
        default='BUY_RATE',
        db_index=True,
        help_text="Whether this is a Buy/Cost rate or a Sell rate"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.supplier.name} - {self.currency_code})"

    class Meta:
        verbose_name = "Partner Rate Card"
        verbose_name_plural = "Partner Rate Cards"
        ordering = ['name']


class PartnerRateLane(models.Model):
    """
    Defines a specific lane (route) within a PartnerRateCard.
    e.g., BNE -> POM (AIR, IMPORT, PREPAID)
    """
    
    # Direction choices - distinguishes IMPORT from EXPORT lanes
    DIRECTION_CHOICES = [
        ('IMPORT', _('Import')),
        ('EXPORT', _('Export')),
    ]
    
    # Payment term choices - constrains which payment terms this lane applies to
    PAYMENT_TERM_CHOICES = [
        ('ANY', _('Any')),        # Applies to both PREPAID and COLLECT
        ('PREPAID', _('Prepaid')),
        ('COLLECT', _('Collect')),
    ]
    
    rate_card = models.ForeignKey(
        PartnerRateCard,
        on_delete=models.CASCADE,
        related_name="lanes"
    )
    
    mode = models.CharField(
        max_length=10,
        choices=MODE_CHOICES,
        default='AIR',
        help_text="The freight mode this lane applies to (AIR only, for now)."
    )
    shipment_type = models.CharField(
        max_length=20,
        choices=SHIPMENT_TYPE_CHOICES,
        default='GENERAL',
        help_text="The cargo type this lane applies to (General Cargo only, for now)."
    )
    
    # NEW: Direction discriminator (required, indexed)
    direction = models.CharField(
        max_length=10,
        choices=DIRECTION_CHOICES,
        default='IMPORT',  # Default for migration, should be inferred in backfill
        db_index=True,
        help_text="Shipment direction: IMPORT (into PNG) or EXPORT (out of PNG)."
    )
    
    # NEW: Payment term discriminator (indexed, defaults to ANY)
    payment_term = models.CharField(
        max_length=10,
        choices=PAYMENT_TERM_CHOICES,
        default='ANY',
        db_index=True,
        help_text="Payment term constraint: ANY (both), PREPAID, or COLLECT."
    )

    # --- Location Fields (Air) ---
    origin_airport = models.ForeignKey(
        'core.Airport',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='partner_origin_lanes',
        help_text="Origin airport (for AIR mode)."
    )
    destination_airport = models.ForeignKey(
        'core.Airport',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='partner_destination_lanes',
        help_text="Destination airport (for AIR mode)."
    )

    # --- Location Fields (Sea) ---
    origin_port = models.ForeignKey(
        'core.Port',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='partner_origin_lanes_sea',
        help_text="Origin port (for SEA mode - NOT YET SUPPORTED)."
    )
    destination_port = models.ForeignKey(
        'core.Port',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='partner_destination_lanes_sea',
        help_text="Destination port (for SEA mode - NOT YET SUPPORTED)."
    )

    def clean(self):
        """
        Validates that the lane's locations and shipment type are
        consistent with the selected mode.
        """
        super().clean()
        
        # --- AIR Mode Validation (Only mode supported) ---
        if self.mode == 'AIR':
            if not self.origin_airport or not self.destination_airport:
                raise ValidationError(
                    "For AIR mode, Origin Airport and Destination Airport are required."
                )
            if self.origin_port or self.destination_port:
                raise ValidationError("For AIR mode, Port fields must be empty.")
            if self.shipment_type not in ['GENERAL']:
                raise ValidationError(
                    "For AIR mode, Shipment Type must be 'General Cargo'."
                )

        # --- Block other modes for now ---
        else:
            raise ValidationError(f"Mode '{self.get_mode_display()}' is not yet supported.")

    def __str__(self):
        if self.mode == 'AIR':
            payment_str = f", {self.payment_term}" if self.payment_term != 'ANY' else ""
            return f"{self.origin_airport} -> {self.destination_airport} ({self.direction}{payment_str})"
        return f"Unsupported Lane ({self.rate_card.name})"

    class Meta:
        verbose_name = "Partner Rate Lane"
        verbose_name_plural = "Partner Rate Lanes"
        # Updated: Include direction and payment_term in unique constraint
        unique_together = [
            ['rate_card', 'origin_airport', 'destination_airport', 'direction', 'payment_term'],
            ['rate_card', 'origin_port', 'destination_port', 'direction', 'payment_term'],
        ]
        ordering = ['mode', 'direction', 'origin_airport', 'origin_port']


class PartnerRate(models.Model):
    """
    The actual rate line for a specific service on a specific lane.
    This is the "rate sheet" that links a ServiceComponent (like 'Freight')
    to its buy-side cost in a foreign currency.
    """
    lane = models.ForeignKey(
        PartnerRateLane,
        on_delete=models.CASCADE,
        related_name="rates",
        help_text="The lane this rate applies to."
    )
    service_component = models.ForeignKey(
        ServiceComponent,
        on_delete=models.CASCADE,
        related_name="partner_rates",
        help_text="The ServiceComponent this rate is for (e.g., 'Freight', 'Handling')."
    )
    unit = models.CharField(
        max_length=20,
        choices=SERVICE_UNIT_CHOICES,
        default='PER_KG',
        help_text="The unit of measure for this rate."
    )
    min_charge_fcy = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True, blank=True, # <-- Made nullable
        help_text="Minimum charge in the card's foreign currency (FCY)."
    )
    max_charge_fcy = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True, blank=True,
        help_text="Maximum charge (cap) in the card's foreign currency (FCY)."
    )

    # --- REFACTORED RATE FIELDS ---
    rate_per_kg_fcy = models.DecimalField(
        max_digits=10, decimal_places=4,
        null=True, blank=True,
        help_text="For 'PER_KG' units. The rate per kilogram in FCY."
    )
    rate_per_shipment_fcy = models.DecimalField(
        max_digits=10, decimal_places=2,
        null=True, blank=True,
        help_text="For 'SHIPMENT' units. A flat fee per shipment in FCY."
    )
    # --- END REFACTOR ---
    
    # --- REMOVED: flat_fee_fcy (renamed) ---
    tiering_json = models.JSONField(
        null=True, blank=True,
        help_text="JSON defining tiered pricing rules (e.g., weight breaks)."
    )

    # --- ADDED VALIDATION METHOD ---
    def clean(self):
        """
        Validate that the correct rate field is filled in based on the unit.
        """
        super().clean()
        if self.unit == 'PER_KG':
            if self.rate_per_kg_fcy is None:
                raise ValidationError({
                    'rate_per_kg_fcy': "For a 'PER_KG' unit, you must provide a 'Rate Per KG'."
                })
            if self.rate_per_shipment_fcy is not None:
                raise ValidationError({
                    'rate_per_shipment_fcy': "Cannot have a 'Rate Per Shipment' with a 'PER_KG' unit."
                })

        elif self.unit == 'SHIPMENT':
            if self.rate_per_shipment_fcy is None:
                raise ValidationError({
                    'rate_per_shipment_fcy': "For a 'SHIPMENT' unit, you must provide a 'Rate Per Shipment'."
                })
            if self.rate_per_kg_fcy is not None:
                raise ValidationError({
                    'rate_per_kg_fcy': "Cannot have a 'Rate Per KG' with a 'SHIPMENT' unit."
                })
        
        # Add more validation for other units like CBM, TEU when we add them
    # --- END OF ADDED METHOD ---

    def __str__(self):
        return f"{self.service_component} on {self.lane}"

    class Meta:
        verbose_name = "Partner Rate"
        verbose_name_plural = "Partner Rates"
        unique_together = [['lane', 'service_component']]


# ##############################################################################
# A2D DAP LEGACY ARCHIVE
# ##############################################################################

class A2DDAPRateArchive(models.Model):
    """
    Immutable archive of decommissioned A2DDAPRate rows.

    This table is populated by migration 0012 before removing the live
    A2DDAPRate table to preserve historical configuration evidence.
    """

    source_rate_id = models.BigIntegerField(unique=True, db_index=True)
    payment_term = models.CharField(max_length=10, db_index=True)
    currency = models.CharField(max_length=3, db_index=True)
    service_component_code = models.CharField(max_length=50, db_index=True)
    unit_basis = models.CharField(max_length=20)
    rate = models.DecimalField(max_digits=10, decimal_places=4)
    min_charge = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    max_charge = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    percent_of_component_code = models.CharField(max_length=50, null=True, blank=True)
    display_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    source_created_at = models.DateTimeField(null=True, blank=True)
    source_updated_at = models.DateTimeField(null=True, blank=True)
    archived_at = models.DateTimeField(default=timezone.now, db_index=True)
    snapshot = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return (
            f"Archived A2D DAP #{self.source_rate_id} "
            f"{self.payment_term}/{self.currency}/{self.service_component_code}"
        )

    class Meta:
        db_table = 'a2d_dap_rate_archive'
        verbose_name = "A2D DAP Rate Archive"
        verbose_name_plural = "A2D DAP Rate Archive"
        ordering = ['-archived_at', 'source_rate_id']
