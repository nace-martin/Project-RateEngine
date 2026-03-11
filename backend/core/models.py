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

    def __str__(self):
        return f"{self.code} - {self.name}"

    class Meta:
        indexes = [
            models.Index(fields=['code']),
            models.Index(fields=['country', 'code']),
            models.Index(fields=['kind', 'code'], name='idx_location_kind_code'),
        ]
        ordering = ['name']

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


class AircraftType(models.Model):
    """
    Aircraft type with cargo capacity constraints.
    Defines physical limitations for cargo door dimensions and piece weights.
    """
    code = models.CharField(
        max_length=10,
        unique=True,
        help_text="Aircraft type code (e.g., B737, B767, A320)"
    )
    name = models.CharField(max_length=100, help_text="Full aircraft name")
    
    class AircraftClass(models.TextChoices):
        NARROW_BODY = 'NARROW_BODY', _('Narrow Body')
        WIDE_BODY = 'WIDE_BODY', _('Wide Body')
   
    aircraft_class = models.CharField(
        max_length=20,
        choices=AircraftClass.choices,
        help_text="Aircraft classification"
    )
    
    # Cargo door constraints (in cm)
    max_length_cm = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Maximum cargo piece length in cm"
    )
    max_width_cm = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Maximum cargo piece width in cm"
    )
    max_height_cm = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Maximum cargo piece height in cm"
    )
    max_piece_weight_kg = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Maximum individual piece weight in kg"
    )
    
    # ULD support
    supports_uld = models.BooleanField(
        default=False,
        help_text="Whether aircraft supports Unit Load Device (ULD) pallets"
    )
    
    notes = models.TextField(blank=True, help_text="Additional notes about aircraft capabilities")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.code} - {self.name}"

    class Meta:
        ordering = ['code']
        verbose_name = "Aircraft Type"
        verbose_name_plural = "Aircraft Types"


class RouteLaneConstraint(models.Model):
    """
    Defines which aircraft operates on which route lane.
    Links origin-destination pairs to aircraft types and service levels.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    origin = models.ForeignKey(
        Location,
        on_delete=models.CASCADE,
        related_name='lane_constraints_origin',
        help_text="Origin location for this lane"
    )
    destination = models.ForeignKey(
        Location,
        on_delete=models.CASCADE,
        related_name='lane_constraints_destination',
        help_text="Destination location for this lane"
    )
    
    service_level = models.CharField(
        max_length=20,
        help_text="Service level code (e.g., DIRECT, VIA_BNE)"
    )
    
    aircraft_type = models.ForeignKey(
        AircraftType,
        on_delete=models.PROTECT,
        related_name='route_lanes',
        help_text="Aircraft type operating this lane"
    )
    
    # Optional intermediate routing point
    via_location = models.ForeignKey(
        Location,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='lane_constraints_via',
        help_text="Intermediate routing point (e.g., BNE for SYD→BNE→POM)"
    )
    
    is_active = models.BooleanField(default=True, help_text="Whether this lane is currently operational")
    priority = models.IntegerField(
        default=1,
        help_text="Lower number = higher priority when selecting lanes (1 = highest)"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        via_text = f" via {self.via_location.code}" if self.via_location else ""
        return f"{self.origin.code}->{self.destination.code}{via_text} ({self.service_level}, {self.aircraft_type.code})"

    class Meta:
        unique_together = [['origin', 'destination', 'service_level']]
        ordering = ['origin__code', 'destination__code', 'priority']
        verbose_name = "Route Lane Constraint"
        verbose_name_plural = "Route Lane Constraints"

