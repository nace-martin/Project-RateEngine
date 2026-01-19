import uuid
from decimal import Decimal
from django.db import models
from django.utils.translation import gettext_lazy as _

from core.models import Location
from parties.models import Company
from services.models import ServiceComponent
from quotes.models import Quote

# --- Enums ---

class ChargeMethod(models.TextChoices):
    WEIGHT_BREAK = 'WEIGHT_BREAK', _('Weight Break')
    FLAT = 'FLAT', _('Flat Fee')
    PER_UNIT = 'PER_UNIT', _('Per Unit')
    PERCENT = 'PERCENT', _('Percentage')

class ChargeUnit(models.TextChoices):
    KG = 'KG', _('Per Kg')
    CBM = 'CBM', _('Per CBM')
    PIECE = 'PIECE', _('Per Piece')
    SHIPMENT = 'SHIPMENT', _('Per Shipment')
    # Add others as needed (TEU, FEU, etc.)

class RateScope(models.TextChoices):
    CONTRACT = 'CONTRACT', _('Contract Rate')
    SPOT = 'SPOT', _('Spot Rate')

class Mode(models.TextChoices):
    AIR = 'AIR', _('Air')
    SEA = 'SEA', _('Sea')
    ROAD = 'ROAD', _('Road')

# --- Geography ---

class Zone(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=255)
    mode = models.CharField(max_length=10, choices=Mode.choices, null=True, blank=True)
    partner = models.ForeignKey(Company, on_delete=models.CASCADE, null=True, blank=True, help_text="If set, this zone is specific to a partner's definition.")

    def __str__(self):
        return f"{self.code} - {self.name}"

class ZoneMember(models.Model):
    zone = models.ForeignKey(Zone, on_delete=models.CASCADE, related_name='members')
    location = models.ForeignKey(Location, on_delete=models.CASCADE, related_name='zone_memberships')

    class Meta:
        unique_together = ('zone', 'location')

    def __str__(self):
        return f"{self.location} in {self.zone}"

# --- Contract Rate Cards ---

class RateCard(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    supplier = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='v3_rate_cards')
    mode = models.CharField(max_length=10, choices=Mode.choices)
    origin_zone = models.ForeignKey(Zone, on_delete=models.PROTECT, related_name='rate_cards_as_origin')
    destination_zone = models.ForeignKey(Zone, on_delete=models.PROTECT, related_name='rate_cards_as_destination')
    currency = models.CharField(max_length=3, help_text="ISO 3-letter currency code")
    scope = models.CharField(max_length=20, choices=RateScope.choices, default=RateScope.CONTRACT)
    
    valid_from = models.DateField(null=True, blank=True)
    valid_until = models.DateField(null=True, blank=True)
    priority = models.IntegerField(default=100, help_text="Lower number = higher priority")
    
    name = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['mode', 'scope', 'priority', 'valid_from']),
        ]

    def __str__(self):
        return f"{self.name} ({self.supplier})"

class RateLine(models.Model):
    card = models.ForeignKey(RateCard, on_delete=models.CASCADE, related_name='lines')
    component = models.ForeignKey(ServiceComponent, on_delete=models.PROTECT)
    method = models.CharField(max_length=20, choices=ChargeMethod.choices)
    unit = models.CharField(max_length=20, choices=ChargeUnit.choices, null=True, blank=True)
    
    min_charge = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    
    # For PERCENT method
    percent_value = models.DecimalField(max_digits=5, decimal_places=4, null=True, blank=True, help_text="e.g. 0.05 for 5%")
    percent_of_component = models.ForeignKey(ServiceComponent, on_delete=models.PROTECT, null=True, blank=True, related_name='percent_lines')
    
    description = models.CharField(max_length=255, blank=True)

    def __str__(self):
        return f"{self.component.code} on {self.card.name}"

class RateBreak(models.Model):
    line = models.ForeignKey(RateLine, on_delete=models.CASCADE, related_name='breaks')
    from_value = models.DecimalField(max_digits=12, decimal_places=2)
    to_value = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, help_text="Null means infinity/open-ended")
    rate = models.DecimalField(max_digits=12, decimal_places=4, help_text="Rate per unit in card currency")

    class Meta:
        ordering = ['from_value']

    def __str__(self):
        return f"{self.from_value} - {self.to_value or 'Max'}: {self.rate}"

# --- Spot Rates (Quote Local) ---

class QuoteSpotRate(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    quote = models.ForeignKey(Quote, on_delete=models.CASCADE, related_name='spot_rates')
    supplier = models.ForeignKey(Company, on_delete=models.PROTECT)
    
    origin_location = models.ForeignKey(Location, on_delete=models.PROTECT, related_name='spot_rates_as_origin')
    destination_location = models.ForeignKey(Location, on_delete=models.PROTECT, related_name='spot_rates_as_destination')
    mode = models.CharField(max_length=10, choices=Mode.choices)
    currency = models.CharField(max_length=3)
    
    valid_until = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Spot Rate for {self.quote.quote_number} from {self.supplier}"

class QuoteSpotCharge(models.Model):
    spot_rate = models.ForeignKey(QuoteSpotRate, on_delete=models.CASCADE, related_name='charges')
    component = models.ForeignKey(ServiceComponent, on_delete=models.PROTECT)
    method = models.CharField(max_length=20, choices=ChargeMethod.choices)
    unit = models.CharField(max_length=20, choices=ChargeUnit.choices, null=True, blank=True)
    
    rate = models.DecimalField(max_digits=12, decimal_places=4, default=Decimal("0.00"), help_text="Flat amount or rate per unit")
    min_charge = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    
    # For PERCENT method
    percent_value = models.DecimalField(max_digits=5, decimal_places=4, null=True, blank=True)
    percent_of_component = models.ForeignKey(ServiceComponent, on_delete=models.PROTECT, null=True, blank=True, related_name='spot_percent_charges')
    
    description = models.CharField(max_length=255, blank=True)

    def __str__(self):
        return f"{self.component.code}: {self.rate}"

# --- Local / System Fees ---

class LocalFeeRule(models.Model):
    component = models.ForeignKey(ServiceComponent, on_delete=models.PROTECT)
    mode = models.CharField(max_length=10, choices=Mode.choices, null=True, blank=True)
    
    origin_location = models.ForeignKey(Location, on_delete=models.PROTECT, null=True, blank=True, related_name='local_fees_as_origin')
    destination_location = models.ForeignKey(Location, on_delete=models.PROTECT, null=True, blank=True, related_name='local_fees_as_destination')
    
    method = models.CharField(max_length=20, choices=ChargeMethod.choices)
    unit = models.CharField(max_length=20, choices=ChargeUnit.choices, null=True, blank=True)
    
    flat_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    rate_per_unit = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    
    # Percentage-based charges
    percent_value = models.DecimalField(max_digits=5, decimal_places=4, null=True, blank=True, help_text="Percentage as decimal (e.g., 0.10 for 10%)")
    percent_of_component = models.ForeignKey(ServiceComponent, on_delete=models.PROTECT, null=True, blank=True, related_name='local_fee_percentage_dependencies', help_text="Component to calculate percentage of")
    
    currency = models.CharField(max_length=3, default='PGK')
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"Local Fee: {self.component.code}"

# --- Sell-Side Configuration ---

class ComponentMargin(models.Model):
    """
    Configures the margin percentage to apply when converting buy costs to sell prices.
    Allows per-component margin configuration (e.g., 20% for Freight, 15% for Pickup).
    """
    component = models.ForeignKey(ServiceComponent, on_delete=models.PROTECT, related_name='margin_rules')
    margin_percent = models.DecimalField(
        max_digits=5, 
        decimal_places=4,
        help_text="Margin as decimal (e.g., 0.20 for 20%)"
    )
    customer_segment = models.CharField(
        max_length=50, 
        blank=True,
        help_text="Optional: segment-specific margin (VIP, STANDARD, BULK, etc.)"
    )
    effective_from = models.DateField(null=True, blank=True)
    effective_until = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ('component', 'customer_segment')
        indexes = [
            models.Index(fields=['component', 'is_active']),
        ]
    
    def __str__(self):
        segment = f" ({self.customer_segment})" if self.customer_segment else ""
        percent = (self.margin_percent * 100).quantize(Decimal('0.1'))
        return f"{self.component.code}: {percent}%{segment}"
