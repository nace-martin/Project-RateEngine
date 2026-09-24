# backend/core/models.py

import uuid
from decimal import Decimal
from django.core.validators import RegexValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from .geo_models import GeoLocation, GeoLocationIdentifier  # noqa: F401 - Django model registration
from .corridor_models import GeoCorridorPolicy, TransportMode  # noqa: F401 - Django model registration
from .fx_market_models import FxMarketRate  # noqa: F401 - Django model registration

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
    currency = models.ForeignKey(
        Currency,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='countries',
        help_text="Default currency used in this country."
    )

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

class Location(models.Model):
    """
    Represents an airport location using standard IATA codes.
    Service scope (D2D, A2D, etc.) determines the service level.
    """

    class Kind(models.TextChoices):
        AIRPORT = 'AIRPORT', _('Airport')
        PORT = 'PORT', _('Port')
        CITY = 'CITY', _('City')
        ADDRESS = 'ADDRESS', _('Address')

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    kind = models.CharField(
        max_length=20,
        choices=Kind.choices,
        db_index=True,
        default=Kind.AIRPORT,
    )
    name = models.CharField(max_length=255, help_text="Human-readable label for the location.")
    code = models.CharField(
        max_length=3,
        db_index=True,
        validators=[
            RegexValidator(
                regex=r"^[A-Z]{3}$",
                message="Location code must be a 3-letter uppercase IATA code.",
            )
        ],
        help_text="IATA airport code (e.g., BNE, POM, SYD)"
    )
    country = models.ForeignKey(
        Country,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='locations'
    )
    city = models.ForeignKey(
        City,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='locations'
    )
    airport = models.ForeignKey(
        Airport,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='locations'
    )
    port = models.ForeignKey(
        Port,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='locations'
    )
    address_line = models.CharField(max_length=255, blank=True)
    metadata = models.JSONField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    @property
    def display_name(self) -> str:
        if self.city and self.city.name:
            return self.city.name
        if self.airport and self.airport.city and self.airport.city.name:
            return self.airport.city.name
        if self.port and self.port.city and self.port.city.name:
            return self.port.city.name
        return self.name

    def __str__(self):
        code = self.code
        if code:
            return f"{code} - {self.display_name}"
        return self.display_name

    class Meta:
        indexes = [
            models.Index(fields=['code']),
            models.Index(fields=['country', 'code']),
            models.Index(fields=['kind', 'code'], name='idx_location_kind_code'),
        ]
        ordering = ['name']

# --- NEW Models based on the Backend Design Spec ---

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
    margin_pct = models.DecimalField(max_digits=5, decimal_places=4, default=0.20)
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

