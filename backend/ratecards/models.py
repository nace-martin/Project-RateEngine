# backend/ratecards/models.py

import uuid
from django.db import models
from django.utils.translation import gettext_lazy as _
from core.models import City, Airport, Port # Import location models
from parties.models import Company
from services.models import ServiceComponent

MODE_CHOICES = [('AIR', _('Air')), ('SEA', _('Sea')), ('ROAD', _('Road'))]
SHIPMENT_TYPE_CHOICES = [
    ('GENERAL', _('General Cargo')),
    ('FCL', _('FCL')),
    ('LCL', _('LCL')),
    ('BULK', _('Bulk')),
]

class RateCard(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # --- CHANGE THESE FIELDS ---
    # Link to Airport for Air rates primarily
    origin_airport = models.ForeignKey(
        Airport, 
        on_delete=models.PROTECT, 
        related_name='ratecards_origin',
        null=True, blank=True
    )
    destination_airport = models.ForeignKey(
        Airport, 
        on_delete=models.PROTECT, 
        related_name='ratecards_destination',
        null=True, blank=True
    )
    # OLD: origin_city_code = models.CharField(max_length=3)
    # OLD: destination_city_code = models.CharField(max_length=3)
    # --- END CHANGE ---

    carrier = models.CharField(max_length=10, default="PX") 
    minimum_charge = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default="PGK")

    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        # Update str representation
        return f"Rate Card {self.origin_airport_id}-{self.destination_airport_id} ({self.carrier})"

    class Meta:
        # Update unique_together constraint
        unique_together = ('origin_airport', 'destination_airport', 'carrier', 'effective_from')


class RateCardBreak(models.Model):
    # ... (no changes needed here) ...
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    rate_card = models.ForeignKey(RateCard, related_name='breaks', on_delete=models.CASCADE)
    weight_break_kg = models.DecimalField(max_digits=10, decimal_places=2)
    rate_per_kg = models.DecimalField(max_digits=10, decimal_places=2)
    # ... (str, Meta) ...
    class Meta:
        ordering = ['weight_break_kg']
        unique_together = ('rate_card', 'weight_break_kg')


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
        help_text="A descriptive name, e.g., 'EFM AUD Import Airfreight 2025'"
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
    mode = models.CharField(
        max_length=10,
        choices=MODE_CHOICES,  # Assumes MODE_CHOICES is defined in this file or imported
        default='AIR',
        help_text="The freight mode this card applies to (e.g., AIR, SEA)."
    )
    shipment_type = models.CharField(
        max_length=20,
        choices=SHIPMENT_TYPE_CHOICES, # Assumes SHIPMENT_TYPE_CHOICES is defined or imported
        default='GENERAL',
        help_text="The shipment type this card applies to (e.g., GENERAL, FCL, LCL)."
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
    e.g., BNE -> POM.
    """
    rate_card = models.ForeignKey(
        PartnerRateCard,
        on_delete=models.CASCADE,
        related_name="lanes"
    )
    origin_airport = models.ForeignKey(
        'core.Airport',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='partner_origin_lanes',
        help_text="Origin airport for this lane."
    )
    destination_airport = models.ForeignKey(
        'core.Airport',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='partner_destination_lanes',
        help_text="Destination airport for this lane."
    )
    # TODO: Add origin/destination Country/City/Port fields as needed for Sea/Road.

    def __str__(self):
        return f"{self.origin_airport} -> {self.destination_airport} ({self.rate_card.name})"

    class Meta:
        verbose_name = "Partner Rate Lane"
        verbose_name_plural = "Partner Rate Lanes"
        unique_together = [['rate_card', 'origin_airport', 'destination_airport']]
        ordering = ['origin_airport', 'destination_airport']


class PartnerRate(models.Model):
    """
    The actual rate line for a specific service on a specific lane.
    This is the "rate sheet" that links a ServiceComponent (like 'Freight')
    to its buy-side cost (e.g., min charge, per-kg tiers) in a foreign currency.
    """
    # Define choices for 'unit' based on ServiceComponent's choices
    UNIT_CHOICES = [
        ('PER_KG', _('Per KG')),
        ('PER_SHIPMENT', _('Per Shipment')),
        ('PER_CBM', _('Per CBM')),
        ('PER_PIECE', _('Per Piece')),
        ('PER_CONTAINER', _('Per Container')),
    ]

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
        choices=UNIT_CHOICES,
        default='PER_KG',
        help_text="The unit of measure for this rate."
    )
    min_charge_fcy = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0.00,
        help_text="Minimum charge in the card's foreign currency (FCY)."
    )
    flat_fee_fcy = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True, blank=True,
        help_text="A flat fee for 'PER_SHIPMENT' units, in FCY."
    )
    tiering_json = models.JSONField(
        null=True, blank=True,
        help_text="For 'PER_KG' units. Stores tier breaks and rates. "
                  "e.g., [{'break': 0, 'rate': 5.50}, {'break': 100, 'rate': 5.00}]"
    )
    
    def __str__(self):
        return f"{self.service_component.name} on {self.lane}"

    class Meta:
        verbose_name = "Partner Rate"
        verbose_name_plural = "Partner Rates"
        unique_together = [['lane', 'service_component']]