# backend/ratecards/models.py

import uuid
from django.db import models
from django.utils.translation import gettext_lazy as _

class RateCard(models.Model):
    """
    Represents an air freight rate card for a specific lane.
    This is a cleaner, simplified model.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # Using simple CharFields for city codes for now. Can be linked to core.City later.
    origin_city_code = models.CharField(max_length=3)
    destination_city_code = models.CharField(max_length=3)
    
    carrier = models.CharField(max_length=10, default="PX") # Defaulting to Air Niugini as per spec
    minimum_charge = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default="PGK")
    
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"Rate Card {self.origin_city_code}-{self.destination_city_code} ({self.carrier})"

    class Meta:
        unique_together = ('origin_city_code', 'destination_city_code', 'carrier', 'effective_from')


class RateCardBreak(models.Model):
    """
    Represents a single weight break line item within a RateCard.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    rate_card = models.ForeignKey(RateCard, related_name='breaks', on_delete=models.CASCADE)
    
    # The weight break in KG. This is the lower bound of the bracket.
    # e.g., 100 means this rate applies to shipments >= 100kg and < next break.
    weight_break_kg = models.DecimalField(max_digits=10, decimal_places=2)
    rate_per_kg = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.rate_card}: {self.weight_break_kg}kg @ {self.rate_per_kg}/kg"

    class Meta:
        ordering = ['weight_break_kg']
        unique_together = ('rate_card', 'weight_break_kg')
