from django.db import models
from django.conf import settings

class ShipmentPiece(models.Model):
    quote = models.ForeignKey('Quote', on_delete=models.CASCADE, related_name="pieces")
    quantity = models.PositiveIntegerField(default=1)
    length_cm = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    width_cm = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    height_cm = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    weight_kg = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    def __str__(self):
        return f"{self.quantity} x {self.weight_kg}kg piece for Quote #{self.quote.id}"
from django.db import models
from django.conf import settings

class Client(models.Model):
    name = models.CharField(max_length=200, unique=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    org_type = models.CharField(max_length=32, default="customer")  # customer/agent/carrier
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class RateCard(models.Model):
    ORIGINS = [("BNE","Brisbane"),("SYD","Sydney")]
    DESTS   = [("POM","Port Moresby"),("LAE","Lae")]

    origin = models.CharField(max_length=8, choices=ORIGINS)
    destination = models.CharField(max_length=8, choices=DESTS)
    min_charge = models.DecimalField(max_digits=10, decimal_places=2)
    brk_45  = models.DecimalField(max_digits=10, decimal_places=2)
    brk_100 = models.DecimalField(max_digits=10, decimal_places=2)
    brk_250 = models.DecimalField(max_digits=10, decimal_places=2)
    brk_500 = models.DecimalField(max_digits=10, decimal_places=2)
    brk_1000= models.DecimalField(max_digits=10, decimal_places=2)
    caf_pct = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    def __str__(self):
        return f"{self.origin} to {self.destination}"

class Quote(models.Model):
    client = models.ForeignKey(Client, on_delete=models.PROTECT, related_name="quotes")
    origin = models.CharField(max_length=8)
    destination = models.CharField(max_length=8)
    mode = models.CharField(max_length=16, choices=[("air","Air"),("sea","Sea"),("customs","Customs")])
    actual_weight_kg = models.DecimalField(max_digits=10, decimal_places=2)
    volume_cbm = models.DecimalField(max_digits=10, decimal_places=3, default=0)
    chargeable_weight_kg = models.DecimalField(max_digits=10, decimal_places=2)
    rate_used_per_kg = models.DecimalField(max_digits=10, decimal_places=2)
    base_cost = models.DecimalField(max_digits=12, decimal_places=2)
    margin_pct = models.DecimalField(max_digits=5, decimal_places=2, default=20.00) # Default 20% margin
    total_sell = models.DecimalField(max_digits=12, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Quote for {self.client.name} - {self.total_sell}"