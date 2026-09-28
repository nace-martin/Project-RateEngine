"""Seed only the two AIR corridors approved for Wave 3B4E."""

from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.corridor_models import GeoCorridorPolicy
from core.geo_models import GeoLocation, GeoLocationIdentifier

APPROVED = (("POM", "BNE"), ("POM", "SYD"))
VALID_FROM = date(2026, 9, 28)
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


def seed(*, apply):
    locations = {code: _airport(code) for code in COUNTRIES}
    actions = []
    for origin_code, destination_code in APPROVED:
        origin, destination = locations[origin_code], locations[destination_code]
        matches = list(GeoCorridorPolicy.objects.filter(
            origin=origin, destination=destination, transport_mode="AIR"
        )[:2])
        if len(matches) > 1:
            raise CommandError(f"Conflicting AIR corridors for {origin_code}->{destination_code}.")
        if matches:
            row = matches[0]
            if (row.via_hub_id is not None or row.valid_from != VALID_FROM
                    or row.valid_until is not None or not row.is_active
                    or row.automation_enabled or row.requires_transit_hub
                    or row.default_transit_days is not None):
                raise CommandError(f"Conflicting AIR corridor for {origin_code}->{destination_code}.")
            actions.append(("reused", origin_code, destination_code, origin, destination))
        else:
            actions.append(("created", origin_code, destination_code, origin, destination))
    if apply:
        for action, _, _, origin, destination in actions:
            if action == "created":
                GeoCorridorPolicy.objects.create(
                    origin=origin, destination=destination, via_hub=None,
                    transport_mode="AIR", valid_from=VALID_FROM, valid_until=None,
                    is_active=True, automation_enabled=False, requires_transit_hub=False,
                )
    return [(action, origin, destination) for action, origin, destination, _, _ in actions]


class Command(BaseCommand):
    help = "Dry-run or apply exactly the two business-approved 3B4E AIR corridors."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Create missing approved rows.")

    @transaction.atomic
    def handle(self, *args, **options):
        actions = seed(apply=options["apply"])
        mode = "APPLY" if options["apply"] else "DRY RUN"
        for action, origin, destination in actions:
            self.stdout.write(f"{mode}: {action} {origin}->{destination} DIRECT AIR {VALID_FROM}..NULL automation_enabled=False")
