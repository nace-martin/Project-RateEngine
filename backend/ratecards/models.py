from django.db import models

class RatecardFile(models.Model):
    """Represents an uploaded rate card file."""
    file = models.FileField(upload_to='ratecards/')
    name = models.CharField(max_length=255)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return self.name

class RateCardLane(models.Model):
    """
    Represents a specific lane (origin-destination pair) within a rate card.
    """
    ratecard_file = models.ForeignKey(RatecardFile, related_name='lanes', on_delete=models.CASCADE)
    origin_code = models.CharField(max_length=3, help_text="IATA code for the origin airport")
    destination_code = models.CharField(max_length=3, help_text="IATA code for the destination airport")

    class Meta:
        unique_together = ('ratecard_file', 'origin_code', 'destination_code')

    def __str__(self):
        return f"{self.origin_code} -> {self.destination_code} ({self.ratecard_file.name})"

class RateBreak(models.Model):
    """
    Stores a single weight break and its corresponding rate for a specific lane.
    e.g., +45kg, +100kg
    """
    lane = models.ForeignKey(RateCardLane, related_name='breaks', on_delete=models.CASCADE)
    weight_break_kg = models.DecimalField(max_digits=10, decimal_places=2, help_text="The minimum weight for this rate break (e.g., 45 for +45kg)")
    rate_per_kg = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        ordering = ['weight_break_kg']

    def __str__(self):
        return f"{self.lane}: {self.weight_break_kg}kg @ {self.rate_per_kg}/kg"

class Surcharge(models.Model):
    """
    Stores an individual surcharge for a specific lane.
    """
    lane = models.ForeignKey(RateCardLane, related_name='surcharges', on_delete=models.CASCADE)
    name = models.CharField(max_length=100, help_text="Name of the surcharge (e.g., Fuel Surcharge)")
    code = models.CharField(max_length=20, help_text="Short code for the surcharge (e.g., FSC)")
    rate = models.DecimalField(max_digits=10, decimal_places=2)
    # Basis will tell us how to apply the rate, e.g., per kg, per shipment, etc.
    # For now, we'll assume a simple flat rate per shipment. This can be expanded later.
    
    def __str__(self):
        return f"{self.lane}: {self.name} ({self.code}) - {self.rate}"