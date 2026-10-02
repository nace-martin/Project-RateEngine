"""Seed the four directional, direct Pilot v1 AIR corridors."""

from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.corridor_models import GeoCorridorPolicy
from core.geo_models import GeoLocation, GeoLocationIdentifier

APPROVED = (
    ("BNE", "POM", "IMPORT"),
    ("SYD", "POM", "IMPORT"),
    ("POM", "BNE", "EXPORT"),
    ("POM", "SYD", "EXPORT"),
)
COUNTRIES = {"POM": "PG", "BNE": "AU", "SYD": "AU"}


def _airport(code):
    identifiers = list(
        GeoLocationIdentifier.objects.select_related("location").filter(
            scheme=GeoLocationIdentifier.Scheme.IATA, code=code
        )[:2]
    )
    if len(identifiers) != 1:
        raise CommandError(f"Expected exactly one IATA geography for {code}.")
    location = identifiers[0].location
    if (location.location_type != GeoLocation.LocationType.AIRPORT
            or not location.is_active or location.country_code != COUNTRIES[code]):
        raise CommandError(f"Invalid IATA airport geography for {code}.")
    return location


def seed(*, apply, effective_from):
    locations = {code: _airport(code) for code in COUNTRIES}
    actions = []
    for origin_code, destination_code, direction in APPROVED:
        origin, destination = locations[origin_code], locations[destination_code]
        matches = list(GeoCorridorPolicy.objects.filter(
            origin=origin, destination=destination, transport_mode="AIR"
        )[:2])
        if len(matches) > 1:
            raise CommandError(f"Conflicting AIR corridors for {origin_code}->{destination_code}.")
        if matches:
            row = matches[0]
            if (row.via_hub_id is not None or row.valid_until is not None or not row.is_active
                    or row.automation_enabled or row.requires_transit_hub
                    or row.default_transit_days is not None):
                raise CommandError(f"Conflicting AIR corridor for {origin_code}->{destination_code}.")
            action = "reused" if row.valid_from == effective_from else "updated"
            actions.append((action, origin_code, destination_code, direction, row, row.valid_from))
        else:
            actions.append(("created", origin_code, destination_code, direction,
                            (origin, destination), None))
    if apply:
        for action, _, _, _, target, _ in actions:
            if action == "created":
                origin, destination = target
                GeoCorridorPolicy.objects.create(
                    origin=origin, destination=destination, via_hub=None,
                    transport_mode="AIR", valid_from=effective_from, valid_until=None,
                    is_active=True, automation_enabled=False, requires_transit_hub=False,
                )
            elif action == "updated":
                target.valid_from = effective_from
                target.save(update_fields=["valid_from"])
    return [(action, origin, destination, direction,
             prior_date if action == "updated" else None)
            for action, origin, destination, direction, _, prior_date in actions]


class Command(BaseCommand):
    help = "Dry-run or apply exactly four directional Pilot v1 AIR corridors."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Create missing approved rows.")
        parser.add_argument("--effective-from", help="Explicit YYYY-MM-DD validity start (required for dry-run and apply).")

    @transaction.atomic
    def handle(self, *args, **options):
        value = options["effective_from"]
        if not value:
            raise CommandError("An explicit --effective-from YYYY-MM-DD is required.")
        try:
            effective_from = date.fromisoformat(value)
        except ValueError as exc:
            raise CommandError("--effective-from must be a valid YYYY-MM-DD date.") from exc
        if effective_from.isoformat() != value:
            raise CommandError("--effective-from must be a valid YYYY-MM-DD date.")
        actions = seed(apply=options["apply"], effective_from=effective_from)
        mode = "APPLY" if options["apply"] else "DRY RUN"
        for action, origin, destination, direction, prior_date in actions:
            verb = action if options["apply"] else f"would {action.removesuffix('d')}"
            validity = (f"valid_from={prior_date}->{effective_from}" if prior_date
                        else f"valid_from={effective_from}")
            self.stdout.write(
                f"{mode}: {verb} {origin}->{destination} {direction} DIRECT AIR "
                f"{validity} valid_until=NULL automation_enabled=False"
            )
