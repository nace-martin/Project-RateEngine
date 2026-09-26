import importlib
import json
from io import StringIO

import pytest
from django.apps import apps
from django.core.management import call_command
from django.db import transaction
from parties.models import Company
from quotes.models import Quote
from quotes.services.air_journey_planner import AirJourneyPlanner

from core.corridor_models import GeoCorridorPolicy
from core.geo_mapping import GeoMappingError, resolve_geo_location
from core.geo_models import GeoLocation, GeoLocationIdentifier
from core.models import Airport, City, Country, Location
from core.tests.helpers import create_location

backfill = importlib.import_module("core.migrations.0016_backfill_geo_airports").backfill_geo_airports


def airport_location(code, country_code, *, name=None, location_code=None):
    country, _ = Country.objects.get_or_create(code=country_code, defaults={"name": country_code})
    city = City.objects.create(country=country, name=f"City {code}")
    airport = Airport.objects.create(iata_code=code, name=name or f"Airport {code}", city=city)
    location = Location.objects.get(airport=airport)  # Airport's existing signal creates it.
    location.name = "Untrusted legacy label"
    location.code = location_code or code
    location.save(update_fields=["name", "code"])
    return location


@pytest.mark.django_db
def test_backfill_maps_proven_airports_once_and_preserves_quote_route_state():
    bne = airport_location("BNE", "AU")
    lae = airport_location("LAE", "PG")
    pom = airport_location("POM", "PG")
    duplicate = create_location(
        kind=Location.Kind.AIRPORT,
        name="Different legacy name",
        code="POM",
        airport=pom.airport,
        city=pom.city,
        country=pom.country,
    )
    customer = Company.objects.create(name="Geography test customer", is_customer=True)
    quote = Quote.objects.create(
        customer=customer, mode="AIR", shipment_type="IMPORT",
        origin_location=bne, destination_location=pom,
    )
    legacy_before = list(Location.objects.order_by("id").values())
    request = {
        "origin_country": "AU", "destination_country": "PG",
        "origin_code": "BNE", "destination_code": "POM",
        "service_domain": "AIR", "service_scope": "A2A", "quote_date": "2026-09-26",
    }
    plan_before = AirJourneyPlanner().plan(request).to_dict()

    backfill(apps, None)
    backfill(apps, None)

    assert GeoLocation.objects.count() == 3
    assert GeoLocationIdentifier.objects.filter(scheme="IATA").count() == 3
    assert {resolve_geo_location(row).country_code for row in (bne, lae, pom)} == {"AU", "PG"}
    assert resolve_geo_location(duplicate).id == resolve_geo_location(pom).id
    assert resolve_geo_location(pom).canonical_name == pom.airport.name
    assert list(Location.objects.order_by("id").values()) == legacy_before
    quote.refresh_from_db()
    assert (quote.origin_location_id, quote.destination_location_id) == (bne.id, pom.id)
    assert GeoCorridorPolicy.objects.count() == 0
    assert AirJourneyPlanner().plan(request).to_dict() == plan_before


@pytest.mark.django_db
def test_missing_fk_and_structured_mismatch_never_map_by_name_or_code():
    country, _ = Country.objects.get_or_create(code="US", defaults={"name": "United States"})
    lax = create_location(kind=Location.Kind.AIRPORT, name="LAX", code="LAX", country=country)
    wrong = airport_location("BNE", "AU", name="POM", location_code="POM")

    backfill(apps, None)

    assert GeoLocation.objects.count() == 0
    with pytest.raises(GeoMappingError, match="missing_airport"):
        resolve_geo_location(lax)
    with pytest.raises(GeoMappingError, match="location_airport_code_mismatch"):
        resolve_geo_location(wrong)
    output = StringIO()
    call_command("geo_mapping_health", stdout=output)
    report = json.loads(output.getvalue())
    assert (report["mapped"], report["unresolved"], report["conflicts"]) == (0, 1, 1)
    assert report["unresolved_locations"][0]["code"] == "LAX"
    assert report["conflict_locations"][0]["code"] == "POM"


@pytest.mark.django_db
def test_existing_identified_geography_is_preserved_and_conflicts_roll_back():
    bne = airport_location("BNE", "AU")
    geo = GeoLocation(
        canonical_name="Existing approved label", country_code="AU",
        location_type="AIRPORT", is_active=True,
    )
    geo.save()
    GeoLocationIdentifier.objects.create(location=geo, scheme="IATA", code="BNE")
    backfill(apps, None)
    assert resolve_geo_location(bne).id == geo.id
    geo.refresh_from_db()
    assert geo.canonical_name == "Existing approved label"

    geo.country_code = "PG"
    geo.save(update_fields=["country_code"])
    with pytest.raises(ValueError, match="Conflicting clean geography"), transaction.atomic():
        backfill(apps, None)
    assert GeoLocation.objects.count() == 1


@pytest.mark.django_db
def test_inactive_clean_geography_fails_closed():
    bne = airport_location("BNE", "AU")
    geo = GeoLocation(
        canonical_name="Airport BNE", country_code="AU",
        location_type="AIRPORT", is_active=False,
    )
    geo.save()
    GeoLocationIdentifier.objects.create(location=geo, scheme="IATA", code="BNE")
    with pytest.raises(GeoMappingError, match="inactive_geography"):
        resolve_geo_location(bne)
    with pytest.raises(ValueError, match="Conflicting clean geography"), transaction.atomic():
        backfill(apps, None)
