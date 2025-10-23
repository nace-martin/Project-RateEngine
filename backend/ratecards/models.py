# backend/ratecards/models.py

import uuid
from django.db import models
from django.utils.translation import gettext_lazy as _
from core.models import City, Airport, Port # Import location models

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
