"""Permanent geographic network corridor policy foundation."""

import uuid

from django.core.exceptions import ValidationError
from django.db import models


class TransportMode(models.TextChoices):
    AIR = "AIR", "Air"
    SEA = "SEA", "Sea"
    ROAD = "ROAD", "Road"


class GeoCorridorPolicy(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    origin = models.ForeignKey(
        "core.GeoLocation",
        on_delete=models.PROTECT,
        related_name="corridor_origins",
    )
    destination = models.ForeignKey(
        "core.GeoLocation",
        on_delete=models.PROTECT,
        related_name="corridor_destinations",
    )
    via_hub = models.ForeignKey(
        "core.GeoLocation",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="corridor_hubs",
    )
    transport_mode = models.CharField(max_length=16, choices=TransportMode.choices)
    automation_enabled = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    requires_transit_hub = models.BooleanField(default=False)
    default_transit_days = models.PositiveIntegerField(null=True, blank=True)
    valid_from = models.DateField()
    valid_until = models.DateField(null=True, blank=True)

    class Meta:
        db_table = "geo_corridor_policy"
        constraints = (
            models.UniqueConstraint(
                fields=["origin", "destination", "transport_mode"],
                condition=models.Q(via_hub__isnull=True),
                name="geo_corridor_direct_uniq",
            ),
            models.UniqueConstraint(
                fields=["origin", "destination", "transport_mode", "via_hub"],
                condition=models.Q(via_hub__isnull=False),
                name="geo_corridor_hub_uniq",
            ),
            models.CheckConstraint(
                condition=~models.Q(origin=models.F("destination")),
                name="geo_corridor_origin_dest_distinct",
            ),
            models.CheckConstraint(
                condition=models.Q(via_hub__isnull=True)
                | (
                    ~models.Q(via_hub=models.F("origin"))
                    & ~models.Q(via_hub=models.F("destination"))
                ),
                name="geo_corridor_via_hub_distinct",
            ),
            models.CheckConstraint(
                condition=models.Q(requires_transit_hub=False)
                | models.Q(via_hub__isnull=False),
                name="geo_corridor_hub_required_when_flagged",
            ),
            models.CheckConstraint(
                condition=models.Q(valid_until__isnull=True)
                | models.Q(valid_until__gt=models.F("valid_from")),
                name="geo_corridor_valid_window",
            ),
            models.CheckConstraint(
                condition=models.Q(transport_mode__in=["AIR", "SEA", "ROAD"]),
                name="geo_corridor_transport_mode_valid",
            ),
        )

    def clean(self):
        super().clean()
        if self.origin_id and self.destination_id and self.origin_id == self.destination_id:
            raise ValidationError(
                {"destination": "Origin and destination locations must be distinct."}
            )
        if self.via_hub_id:
            if self.via_hub_id == self.origin_id:
                raise ValidationError(
                    {"via_hub": "Via hub cannot be identical to origin location."}
                )
            if self.via_hub_id == self.destination_id:
                raise ValidationError(
                    {"via_hub": "Via hub cannot be identical to destination location."}
                )
        if self.requires_transit_hub and not self.via_hub_id:
            raise ValidationError(
                {"via_hub": "Via hub location is required when requires_transit_hub is True."}
            )
        if self.valid_from and self.valid_until and self.valid_until <= self.valid_from:
            raise ValidationError(
                {"valid_until": "valid_until must be strictly greater than valid_from."}
            )

    def __str__(self):
        hub_str = f" via {self.via_hub}" if self.via_hub else ""
        return f"{self.origin} -> {self.destination}{hub_str} ({self.transport_mode})"
