# backend/core/models.py

import uuid
from decimal import Decimal
from django.db import models
from django.utils.translation import gettext_lazy as _

# --- Existing Core Models (with minor enhancements) ---

class Currency(models.Model):
    code = models.CharField(max_length=3, primary_key=True, help_text="ISO 4217 currency code.")
    name = models.CharField(max_length=50)
    minor_units = models.PositiveSmallIntegerField(default=2)

    def __str__(self):
        return self.code

    class Meta:
        verbose_name_plural = "Currencies"

class Country(models.Model):
    code = models.CharField(max_length=2, primary_key=True, help_text="ISO 3166-1 alpha-2 country code.")
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name_plural = "Countries"

class City(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    country = models.ForeignKey(Country, on_delete=models.CASCADE)
    name = models.CharField(max_length=100, db_index=True) # Add index

    def __str__(self):
        return f"{self.name}, {self.country.code}"

    class Meta:
        verbose_name_plural = "Cities"
        unique_together = ('country', 'name') # Ensure unique city names per country
        ordering = ['country__code', 'name'] # Add default ordering

class Airport(models.Model):
    # Use IATA code as primary key for simplicity if guaranteed unique
    iata_code = models.CharField(max_length=3, primary_key=True, help_text="IATA 3-letter airport code.")
    name = models.CharField(max_length=100)
    city = models.ForeignKey(City, on_delete=models.PROTECT, null=True, blank=True) # Protect city link

    def __str__(self):
        return self.iata_code

    class Meta:
         ordering = ['iata_code'] # Add default ordering

# --- ADD PORT MODEL ---
class Port(models.Model):
    """Represents a Sea Port, typically identified by UN/LOCODE."""
    # Using UN/LOCODE as the primary key assumes uniqueness
    unlocode = models.CharField(max_length=5, primary_key=True, help_text="UN/LOCODE (e.g., PGPOM, AUBNE).")
    name = models.CharField(max_length=100)
    city = models.ForeignKey(City, on_delete=models.PROTECT, null=True, blank=True) # Link to City

    def __str__(self):
        return self.unlocode

    class Meta:
         ordering = ['unlocode'] # Add default ordering
# --- END ADD ---

# --- NEW Models based on the Backend Design Spec ---

class FxRate(models.Model):
    """
    Stores the LATEST available foreign exchange rates. This table is for live/indicative
    rates and is updated daily. Quotes will NOT link to this directly; they will
    link to an immutable FxSnapshot.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    base_currency = models.ForeignKey(Currency, related_name='fx_base_rates', on_delete=models.CASCADE)
    quote_currency = models.ForeignKey(Currency, related_name='fx_quote_rates', on_delete=models.CASCADE)
    tt_buy = models.DecimalField(max_digits=18, decimal_places=8, null=True, blank=True, help_text="Telegraphic Transfer Buy Rate")
    tt_sell = models.DecimalField(max_digits=18, decimal_places=8, null=True, blank=True, help_text="Telegraphic Transfer Sell Rate")
    source = models.CharField(max_length=50)
    last_updated = models.DateTimeField()

    def __str__(self):
        return f"{self.base_currency}/{self.quote_currency}"

    class Meta:
        unique_together = ('base_currency', 'quote_currency', 'source')


class FxSnapshot(models.Model):
    """
    An immutable snapshot of all FX rates at a specific point in time.
    Each quote MUST link to one of these to ensure its calculation is replayable.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    as_of_timestamp = models.DateTimeField(db_index=True)
    source = models.CharField(max_length=50)
    rates = models.JSONField(help_text="A JSON blob of all currency rates at the time of the snapshot.")
    caf_percent = models.DecimalField(
        max_digits=5, decimal_places=4, default=Decimal("0.0"), # Example default, should be set during creation
        help_text="Currency Adjustment Factor % applied at the time of snapshot."
    )
    fx_buffer_percent = models.DecimalField(
        max_digits=5, decimal_places=4, default=Decimal("0.0"), # Example default
        help_text="Additional FX buffer/hedge % applied at the time of snapshot."
    )

    def __str__(self):
        return f"FX Snapshot from {self.source} at {self.as_of_timestamp}"


class Policy(models.Model):
    """
    A versioned set of core business rules (CAF, margins, etc.).
    This allows us to change policies over time without affecting historical quotes.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, default="Default Policy")
    caf_import_pct = models.DecimalField(max_digits=5, decimal_places=4, default=0.05)
    caf_export_pct = models.DecimalField(max_digits=5, decimal_places=4, default=0.10)
    margin_pct = models.DecimalField(max_digits=5, decimal_places=4, default=0.15)
    is_pgk_per_fcy = models.BooleanField(default=True)
    
    class RoundingMode(models.TextChoices):
        PER_LINE_UP = 'PER_LINE_UP', _('Per Line Up')
        TOTAL_UP = 'TOTAL_UP', _('Total Up')
    
    rounding_mode_agent_aud = models.CharField(max_length=20, choices=RoundingMode.choices, default=RoundingMode.PER_LINE_UP)
    include_gst_in_agent_quote = models.BooleanField(default=True)
    
    effective_from = models.DateTimeField()
    effective_to = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.name} (Effective: {self.effective_from.strftime('%Y-%m-%d')})"


class Surcharge(models.Model):
    """
    Configurable surcharges, primarily for PX Export calculations.
    Moves surcharge logic from code into manageable data.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, help_text="e.g., AW, BI, MY, SC, BP")
    description = models.CharField(max_length=255)
    
    class Basis(models.TextChoices):
        FLAT = 'FLAT', _('Flat Rate')
        PER_KG = 'PER_KG', _('Per Kilogram')
        FORMULA = 'FORMULA', _('Complex Formula')

    basis = models.CharField(max_length=20, choices=Basis.choices)
    rate = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    minimum_charge = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    currency = models.ForeignKey(Currency, on_delete=models.PROTECT)
    formula = models.TextField(null=True, blank=True, help_text="For complex rules like BP, implemented in code.")
    
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.code


class LocalTariff(models.Model):
    """
    Manages local charges for services like pickup, clearance, cartage, etc.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    country = models.ForeignKey(Country, on_delete=models.CASCADE)
    charge_code = models.CharField(max_length=50, help_text="e.g., 'CARTAGE', 'CLEARANCE', 'AGENCY_FEE'")
    description = models.CharField(max_length=255)

    class Basis(models.TextChoices):
        FLAT = 'FLAT', _('Flat Rate')
        PER_KG = 'PER_KG', _('Per Kilogram')
        FORMULA = 'FORMULA', _('Complex Formula')
        
    basis = models.CharField(max_length=20, choices=Basis.choices)
    rate = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    minimum_charge = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    maximum_charge = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    currency = models.ForeignKey(Currency, on_delete=models.PROTECT)
    gst_rate = models.DecimalField(max_digits=5, decimal_places=4, default=0.10)
    formula_name = models.CharField(max_length=50, null=True, blank=True, help_text="Name of the function in code to calculate this, e.g., 'calculate_png_cartage'.")

    def __str__(self):
        return f"{self.charge_code} - {self.country.code}"