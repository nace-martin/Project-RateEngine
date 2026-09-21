"""Permanent geography foundation; legacy pricing still uses core.models.Location."""

import uuid

from django.db import models
from django.db.models.functions import Trim, Upper


class GeoLocation(models.Model):
    class LocationType(models.TextChoices):
        AIRPORT = "AIRPORT", "Airport"
        SEAPORT = "SEAPORT", "Seaport"
        CITY = "CITY", "City"
        INLAND_HUB = "INLAND_HUB", "Inland hub"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    canonical_name = models.CharField(max_length=255)
    country_code = models.CharField(max_length=2)
    state_province = models.CharField(max_length=100, blank=True)
    location_type = models.CharField(max_length=16, choices=LocationType.choices)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "geo_location"
        constraints = (
            models.CheckConstraint(
                condition=models.Q(
                    location_type__in=["AIRPORT", "SEAPORT", "CITY", "INLAND_HUB"]
                ),
                name="geo_location_type_valid",
            ),
        )

    def __str__(self):
        return self.canonical_name


class GeoLocationIdentifier(models.Model):
    class Scheme(models.TextChoices):
        IATA = "IATA", "IATA"
        ICAO = "ICAO", "ICAO"
        UNLOCODE = "UNLOCODE", "UN/LOCODE"
        INTERNAL_STATION = "INTERNAL_STATION", "Internal station"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    location = models.ForeignKey(
        GeoLocation, on_delete=models.PROTECT, related_name="identifiers"
    )
    scheme = models.CharField(max_length=16, choices=Scheme.choices)
    code = models.CharField(max_length=32)

    class Meta:
        db_table = "geo_location_identifier"
        constraints = (
            models.UniqueConstraint(
                fields=["scheme", "code"], name="geo_identifier_scheme_code_uniq"
            ),
            models.CheckConstraint(
                condition=models.Q(
                    scheme__in=["IATA", "ICAO", "UNLOCODE", "INTERNAL_STATION"]
                ),
                name="geo_identifier_scheme_valid",
            ),
            models.CheckConstraint(
                condition=~models.Q(code="") & models.Q(code=Upper(Trim("code"))),
                name="geo_identifier_code_normalized",
            ),
        )

    def __str__(self):
        return f"{self.scheme}/{self.code}"
