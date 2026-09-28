from datetime import date
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from quotes.contracts.journey_contracts import JourneyStatus
from quotes.services.air_journey_planner import AirJourneyPlanner
from quotes.services.corridor_air_journey_planner import CorridorAirJourneyPlanner

from core.corridor_models import GeoCorridorPolicy
from core.geo_models import GeoLocation, GeoLocationIdentifier

pytestmark = pytest.mark.django_db


def airport(code, country):
    location = GeoLocation(
        canonical_name=code, country_code=country, location_type="AIRPORT"
    )
    location.save()
    GeoLocationIdentifier.objects.create(location=location, scheme="IATA", code=code)
    return location


def approved_geography():
    return airport("POM", "PG"), airport("BNE", "AU"), airport("SYD", "AU")


def run(*args):
    output = StringIO()
    call_command("seed_approved_air_corridors", *args, stdout=output)
    return output.getvalue()


def test_only_approved_direct_disabled_rows_created_and_rerun_reuses():
    approved_geography()
    assert run().count("DRY RUN: created") == 2
    assert GeoCorridorPolicy.objects.count() == 0

    assert run("--apply").count("APPLY: created") == 2
    rows = list(GeoCorridorPolicy.objects.order_by("destination__identifiers__code"))
    assert {(row.origin.identifiers.get(scheme="IATA").code,
             row.destination.identifiers.get(scheme="IATA").code) for row in rows} == {
        ("POM", "BNE"), ("POM", "SYD")
    }
    assert all(row.transport_mode == "AIR" and row.via_hub_id is None
               and row.valid_from == date(2026, 9, 28) and row.valid_until is None
               and row.is_active and not row.automation_enabled
               and not row.requires_transit_hub for row in rows)
    assert run("--apply").count("APPLY: reused") == 2
    assert GeoCorridorPolicy.objects.count() == 2
    assert GeoCorridorPolicy.objects.filter(automation_enabled=True).count() == 0


def test_missing_or_conflicting_geography_fails_without_partial_seed():
    airport("POM", "PG")
    airport("BNE", "AU")
    with pytest.raises(CommandError, match="SYD"):
        run("--apply")
    assert GeoCorridorPolicy.objects.count() == 0

    airport("SYD", "PG")
    with pytest.raises(CommandError, match="SYD"):
        run("--apply")
    assert GeoCorridorPolicy.objects.count() == 0


@pytest.mark.parametrize("conflict", ["via", "enabled", "date"])
def test_conflicting_existing_corridor_fails_without_creating_second_row(conflict):
    pom, bne, _ = approved_geography()
    fields = {
        "origin": pom, "destination": bne, "transport_mode": "AIR",
        "valid_from": date(2026, 9, 28),
    }
    if conflict == "via":
        fields["via_hub"] = airport("RAB", "PG")
    elif conflict == "enabled":
        fields["automation_enabled"] = True
    else:
        fields["valid_from"] = date(2026, 9, 27)
    GeoCorridorPolicy.objects.create(**fields)
    with pytest.raises(CommandError, match="Conflicting AIR corridor"):
        run("--apply")
    assert GeoCorridorPolicy.objects.count() == 1


def test_disabled_seed_does_not_switch_live_planner():
    approved_geography()
    run("--apply")
    request = {
        "origin_country": "PG", "destination_country": "AU",
        "origin_code": "POM", "destination_code": "BNE",
        "service_domain": "AIR", "service_scope": "A2A", "quote_date": "2026-09-28",
    }
    legacy = AirJourneyPlanner().plan(request)
    generic = CorridorAirJourneyPlanner().plan(request)
    assert legacy.status == JourneyStatus.PLANNED
    assert [(leg.origin_code, leg.destination_code) for leg in legacy.legs] == [("POM", "BNE")]
    assert generic.status == JourneyStatus.NEEDS_REVIEW
    assert [(leg.origin_code, leg.destination_code) for leg in generic.legs] == [("POM", "BNE")]
