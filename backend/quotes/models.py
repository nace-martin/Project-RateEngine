from django.conf import settings
from django.db import models
from django.core.exceptions import ValidationError

class Quotation(models.Model):
    SERVICE_TYPE_CHOICES = [('IMPORT','Import'), ('EXPORT','Export'), ('DOMESTIC','Domestic')]
    TERMS_CHOICES = [('EXW','EXW'), ('FOB','FOB'), ('CIP','CIP'), ('CPT','CPT'), ('DAP','DAP'), ('DDP','DDP')]
    SCOPE_CHOICES = [('D2D','Door–Door'), ('D2A','Door–Airport'), ('A2D','Airport–Door'), ('A2A','Airport–Airport')]
    PAYMENT_TERM_CHOICES = [('PREPAID','Prepaid'), ('COLLECT','Collect')]

    reference = models.CharField(max_length=255, unique=True)
    customer = models.ForeignKey('customers.Customer', on_delete=models.PROTECT)
    date = models.DateField()
    validity_days = models.PositiveIntegerField(default=7)
    service_type = models.CharField(max_length=20, choices=SERVICE_TYPE_CHOICES)
    terms = models.CharField(max_length=20, choices=TERMS_CHOICES)
    scope = models.CharField(max_length=20, choices=SCOPE_CHOICES)
    payment_term = models.CharField(max_length=20, choices=PAYMENT_TERM_CHOICES)
    sell_currency = models.CharField(max_length=3, default='PGK')
    notes = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, default='DRAFT')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['customer', '-created_at']),
        ]

    def __str__(self):
        return self.reference

class QuoteVersion(models.Model):
    quotation = models.ForeignKey(Quotation, on_delete=models.CASCADE, related_name='versions')
    version_no = models.PositiveIntegerField()
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    locked_at = models.DateTimeField(null=True, blank=True)
    origin = models.ForeignKey('core.Station', on_delete=models.PROTECT, related_name='+')
    destination = models.ForeignKey('core.Station', on_delete=models.PROTECT, related_name='+')
    volumetric_divisor = models.PositiveIntegerField(default=6000)
    volumetric_weight_kg = models.DecimalField(max_digits=10, decimal_places=3)
    chargeable_weight_kg = models.DecimalField(max_digits=10, decimal_places=3)
    carrier_code = models.CharField(max_length=3, blank=True, null=True)
    service_level = models.CharField(max_length=50, blank=True, null=True)
    transit_time_days = models.PositiveIntegerField(blank=True, null=True)
    routing_details = models.TextField(blank=True, null=True)
    fx_snapshot = models.JSONField(default=dict)
    policy_snapshot = models.JSONField(default=dict)
    rate_provenance = models.JSONField(default=dict)
    sell_currency = models.CharField(max_length=3)
    valid_from = models.DateField()
    valid_to = models.DateField()
    calc_version = models.CharField(max_length=32, default='qe-0.1')
    created_at = models.DateTimeField(auto_now_add=True)
    idempotency_key = models.CharField(max_length=64, null=True, blank=True, unique=True)

    class Meta:
        unique_together = [('quotation','version_no')]
        indexes = [
            models.Index(fields=['quotation', '-version_no']),
            models.Index(fields=['origin', 'destination', '-created_at']),
        ]
        ordering = ['-version_no']

    @property
    def is_locked(self) -> bool:
        return self.locked_at is not None

    def __str__(self):
        return f"{self.quotation.reference} v{self.version_no}"

class ShipmentPiece(models.Model):
    version = models.ForeignKey(QuoteVersion, on_delete=models.CASCADE, related_name='pieces')
    length_cm = models.PositiveIntegerField()
    width_cm  = models.PositiveIntegerField()
    height_cm = models.PositiveIntegerField()
    weight_kg = models.DecimalField(max_digits=10, decimal_places=3)
    count = models.PositiveIntegerField(default=1)
    description = models.CharField(max_length=255, blank=True, null=True)

    def save(self, *args, **kwargs):
        if self.pk and self.version.is_locked:
            raise ValidationError("This quote version is locked and cannot be modified.")
        if not self.pk and self.version.is_locked:
            raise ValidationError("This quote version is locked and cannot accept new pieces.")
        return super().save(*args, **kwargs)

class Charge(models.Model):
    STAGE = [('ORIGIN','Origin'), ('AIR','Air'), ('DESTINATION','Destination')]
    BASIS = [('PER_KG','Per Kg'), ('FLAT','Flat'), ('PERCENT','Percent')]
    SIDE  = [('BUY','Buy'), ('SELL','Sell')]

    version = models.ForeignKey(QuoteVersion, on_delete=models.CASCADE, related_name='charges')
    stage = models.CharField(max_length=12, choices=STAGE)
    code = models.CharField(max_length=20, blank=True, null=True)
    description = models.CharField(max_length=255)
    basis = models.CharField(max_length=10, choices=BASIS, default='FLAT')
    qty = models.DecimalField(max_digits=18, decimal_places=3, default=1)
    unit_price = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    extended_price = models.DecimalField(max_digits=18, decimal_places=2)
    side = models.CharField(max_length=5, choices=SIDE, default='SELL')
    is_taxable = models.BooleanField(default=True)
    min_charge_applied = models.BooleanField(default=False)
    gst_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=10.0)
    currency = models.CharField(max_length=3, default='PGK')
    source_ref = models.CharField(max_length=64, blank=True, null=True)

    class Meta:
        indexes = [
            models.Index(fields=['version', 'side', 'stage']),
        ]

    def save(self, *args, **kwargs):
        if self.pk and self.version.is_locked:
            raise ValidationError("This quote version is locked and cannot be modified.")
        if not self.pk and self.version.is_locked:
            raise ValidationError("This quote version is locked and cannot accept new lines.")
        return super().save(*args, **kwargs)
