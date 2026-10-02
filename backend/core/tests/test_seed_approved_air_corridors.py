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
TEST_EFFECTIVE_FROM = "2026-10-03"
APPROVED = {
    ("BNE", "POM", "IMPORT"), ("SYD", "POM", "IMPORT"),
    ("POM", "BNE", "EXPORT"), ("POM", "SYD", "EXPORT"),
}


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
    dry_run = run("--effective-from", TEST_EFFECTIVE_FROM)
    assert dry_run.count("DRY RUN: would create") == 4
    for origin, destination, direction in APPROVED:
        assert (f"{origin}->{destination} {direction} DIRECT AIR "
                f"valid_from={TEST_EFFECTIVE_FROM} valid_until=NULL "
                "automation_enabled=False") in dry_run
    assert GeoCorridorPolicy.objects.count() == 0

    assert run("--apply", "--effective-from", TEST_EFFECTIVE_FROM).count("APPLY: created") == 4
    rows = list(GeoCorridorPolicy.objects.all())
    assert {(row.origin.identifiers.get(scheme="IATA").code,
             row.destination.identifiers.get(scheme="IATA").code) for row in rows} == {
        (origin, destination) for origin, destination, _ in APPROVED
    }
    assert all(row.transport_mode == "AIR" and row.via_hub_id is None
               and row.valid_from == date.fromisoformat(TEST_EFFECTIVE_FROM) and row.valid_until is None
               and row.is_active and not row.automation_enabled
               and not row.requires_transit_hub and row.default_transit_days is None
               for row in rows)
    assert run("--apply", "--effective-from", TEST_EFFECTIVE_FROM).count("APPLY: reused") == 4
    assert GeoCorridorPolicy.objects.count() == 4
    assert GeoCorridorPolicy.objects.filter(automation_enabled=True).count() == 0


def test_missing_or_invalid_effective_date_fails_without_writes():
    approved_geography()
    with pytest.raises(CommandError, match="explicit --effective-from"):
        run("--apply")
    with pytest.raises(CommandError, match="explicit --effective-from"):
        run()
    with pytest.raises(CommandError, match="valid YYYY-MM-DD"):
        run("--apply", "--effective-from", "2026-02-30")
    assert GeoCorridorPolicy.objects.count() == 0


def test_missing_or_conflicting_geography_fails_without_partial_seed():
    airport("POM", "PG")
    airport("BNE", "AU")
    with pytest.raises(CommandError, match="SYD"):
        run("--apply", "--effective-from", TEST_EFFECTIVE_FROM)
    assert GeoCorridorPolicy.objects.count() == 0

    airport("SYD", "PG")
    with pytest.raises(CommandError, match="SYD"):
        run("--apply", "--effective-from", TEST_EFFECTIVE_FROM)
    assert GeoCorridorPolicy.objects.count() == 0


@pytest.mark.parametrize("conflict", ["via", "enabled", "expiry"])
def test_conflicting_existing_corridor_fails_without_creating_second_row(conflict):
    pom, bne, _ = approved_geography()
    fields = {
        "origin": pom, "destination": bne, "transport_mode": "AIR",
        "valid_from": date.fromisoformat(TEST_EFFECTIVE_FROM),
    }
    if conflict == "via":
        fields["via_hub"] = airport("RAB", "PG")
    elif conflict == "enabled":
        fields["automation_enabled"] = True
    else:
        fields["valid_until"] = date(2026, 10, 30)
    GeoCorridorPolicy.objects.create(**fields)
    with pytest.raises(CommandError, match="Conflicting AIR corridor"):
        run("--apply", "--effective-from", TEST_EFFECTIVE_FROM)
    assert GeoCorridorPolicy.objects.count() == 1


def test_existing_approved_exports_get_explicit_date_update_only():
    pom, bne, syd = approved_geography()
    existing = [GeoCorridorPolicy.objects.create(
        origin=pom, destination=destination, transport_mode="AIR",
        valid_from=date(2026, 9, 28),
    ) for destination in (bne, syd)]
    dry_run = run("--effective-from", TEST_EFFECTIVE_FROM)
    assert dry_run.count("DRY RUN: would update") == 2
    assert dry_run.count("DRY RUN: would create") == 2
    assert "valid_from=2026-09-28->2026-10-03" in dry_run
    assert all(row.valid_from == date(2026, 9, 28) for row in existing)
    assert GeoCorridorPolicy.objects.count() == 2

    applied = run("--apply", "--effective-from", TEST_EFFECTIVE_FROM)
    assert applied.count("APPLY: updated") == 2
    assert applied.count("APPLY: created") == 2
    assert GeoCorridorPolicy.objects.count() == 4
    assert all(GeoCorridorPolicy.objects.get(pk=row.pk).valid_from
               == date.fromisoformat(TEST_EFFECTIVE_FROM) for row in existing)
    assert run("--apply", "--effective-from", TEST_EFFECTIVE_FROM).count("APPLY: reused") == 4


def test_unrelated_corridor_remains_unchanged():
    _, bne, syd = approved_geography()
    unrelated = GeoCorridorPolicy.objects.create(
        origin=bne, destination=syd, transport_mode="SEA",
        valid_from=date(2025, 1, 1), automation_enabled=True,
    )
    before = {field.name: getattr(unrelated, field.attname)
              for field in GeoCorridorPolicy._meta.fields}
    run("--apply", "--effective-from", TEST_EFFECTIVE_FROM)
    unrelated.refresh_from_db()
    assert {field.name: getattr(unrelated, field.attname)
            for field in GeoCorridorPolicy._meta.fields} == before
    assert GeoCorridorPolicy.objects.count() == 5


def test_disabled_seed_does_not_switch_live_planner():
    approved_geography()
    run("--apply", "--effective-from", TEST_EFFECTIVE_FROM)
    for origin, destination, _ in APPROVED:
        request = {
            "origin_country": "PG" if origin == "POM" else "AU",
            "destination_country": "PG" if destination == "POM" else "AU",
            "origin_code": origin, "destination_code": destination,
            "service_domain": "AIR", "service_scope": "A2A",
            "quote_date": TEST_EFFECTIVE_FROM,
        }
        generic = CorridorAirJourneyPlanner().plan(request)
        assert generic.status == JourneyStatus.NEEDS_REVIEW
        assert [(leg.origin_code, leg.destination_code) for leg in generic.legs] == [(origin, destination)]
        assert any(blocker.value == "ROUTE_AUTOMATION_DISABLED" for blocker in generic.blockers)
        if origin == "POM":
            legacy = AirJourneyPlanner().plan(request)
            assert legacy.status == JourneyStatus.PLANNED
            assert [(leg.origin_code, leg.destination_code) for leg in legacy.legs] == [(origin, destination)]
