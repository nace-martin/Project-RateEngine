from datetime import date

import pytest
from core.corridor_models import GeoCorridorPolicy
from core.geo_models import GeoLocation, GeoLocationIdentifier
from django.core.exceptions import ValidationError
from parties.models import Company
from pricing_v4.contracts.charge_context import (
    JourneyDirection,
    LegRole,
    ProductCodeDomain,
    TransportMode,
)

from quotes.contracts.journey_contracts import JourneyPlannerBlockerCode, JourneyStatus
from quotes.models import Quote, ShipmentJourneyDB, ShipmentLegDB
from quotes.services.air_journey_planner import AirJourneyPlanner
from quotes.services.corridor_air_journey_planner import CorridorAirJourneyPlanner

pytestmark = pytest.mark.django_db


def geo(code, country):
    location = GeoLocation(canonical_name=code, country_code=country, location_type="AIRPORT")
    location.save()
    GeoLocationIdentifier.objects.create(location=location, scheme="IATA", code=code)
    return location


def request(origin, destination, origin_country, destination_country, **overrides):
    payload = {
        "customer_origin_code": origin, "customer_destination_code": destination,
        "origin_country": origin_country, "destination_country": destination_country,
        "service_domain": "AIR", "service_scope": "A2A", "quote_date": "2026-01-15",
    }
    return payload | overrides


@pytest.mark.parametrize("origin,destination,origin_country,destination_country,role,domain,direction", [
    ("BNE", "RAB", "AU", "PG", LegRole.INTERNATIONAL_IMPORT, ProductCodeDomain.IMPORT, JourneyDirection.IMPORT),
    ("RAB", "BNE", "PG", "AU", LegRole.INTERNATIONAL_EXPORT, ProductCodeDomain.EXPORT, JourneyDirection.EXPORT),
])
def test_direct_corridor_uses_actual_png_endpoint_as_gateway(
    origin, destination, origin_country, destination_country, role, domain, direction,
):
    start, end = geo(origin, origin_country), geo(destination, destination_country)
    corridor = GeoCorridorPolicy.objects.create(
        origin=start, destination=end, transport_mode="AIR", valid_from=date(2026, 1, 1),
        automation_enabled=True,
    )
    plan = CorridorAirJourneyPlanner().plan(request(
        origin, destination, origin_country, destination_country,
    ))
    assert plan.direction == direction
    assert plan.pattern is None
    assert plan.route_policy_key == str(corridor.pk)
    assert plan.gateway_code == "RAB"
    assert plan.status == JourneyStatus.PLANNED
    assert [(leg.origin_code, leg.destination_code, leg.role, leg.product_code_domain)
            for leg in plan.legs] == [(origin, destination, role, domain)]
    assert plan.legs[0].transport_mode == TransportMode.INTERNATIONAL_AIR


@pytest.mark.parametrize("origin,destination,origin_country,destination_country,roles,domains", [
    ("SIN", "LAE", "SG", "PG",
     [LegRole.INTERNATIONAL_IMPORT, LegRole.DOMESTIC_ON_FORWARDING],
     [ProductCodeDomain.IMPORT, ProductCodeDomain.DOMESTIC]),
    ("LAE", "SIN", "PG", "SG",
     [LegRole.DOMESTIC_PRE_CARRIAGE, LegRole.INTERNATIONAL_EXPORT],
     [ProductCodeDomain.DOMESTIC, ProductCodeDomain.EXPORT]),
])
def test_transit_corridor_uses_arbitrary_via_hub_and_correct_direction(
    origin, destination, origin_country, destination_country, roles, domains,
):
    start, end = geo(origin, origin_country), geo(destination, destination_country)
    hub = geo("RAB", "PG")
    GeoCorridorPolicy.objects.create(
        origin=start, destination=end, via_hub=hub, transport_mode="AIR",
        valid_from=date(2026, 1, 1), automation_enabled=True,
    )
    plan = CorridorAirJourneyPlanner().plan(request(
        origin, destination, origin_country, destination_country,
    ))
    assert plan.gateway_code == "RAB"
    assert [leg.role for leg in plan.legs] == roles
    assert [leg.product_code_domain for leg in plan.legs] == domains
    assert [(leg.origin_code, leg.destination_code) for leg in plan.legs] == [
        (origin, "RAB"), ("RAB", destination),
    ]
    assert [leg.transport_mode for leg in plan.legs] == (
        [TransportMode.INTERNATIONAL_AIR, TransportMode.DOMESTIC_AIR]
        if origin_country != "PG" else [TransportMode.DOMESTIC_AIR, TransportMode.INTERNATIONAL_AIR]
    )
    assert not plan.blockers


def test_missing_ambiguous_and_invalid_corridors_fail_closed():
    sin, lae, rab = geo("SIN", "SG"), geo("LAE", "PG"), geo("RAB", "PG")
    payload = request("SIN", "LAE", "SG", "PG")
    planner = CorridorAirJourneyPlanner()
    assert planner.plan(payload).blockers == [JourneyPlannerBlockerCode.ROUTE_AUTOMATION_DISABLED]
    direct = GeoCorridorPolicy.objects.create(
        origin=sin, destination=lae, transport_mode="SEA", valid_from=date(2026, 1, 1),
        automation_enabled=True,
    )
    assert not planner.plan(payload).legs  # wrong mode
    direct.transport_mode = "AIR"
    direct.save()
    assert planner.plan(payload).status == JourneyStatus.PLANNED
    via = GeoCorridorPolicy.objects.create(
        origin=sin, destination=lae, via_hub=rab, transport_mode="AIR",
        valid_from=date(2026, 1, 1), automation_enabled=True,
    )
    assert planner.plan(payload).blockers == [JourneyPlannerBlockerCode.ROUTE_AUTOMATION_DISABLED]
    via.is_active = False
    via.save()
    for changes in (
        {"is_active": False},
        {"valid_from": date(2026, 1, 16)},
        {"valid_from": date(2026, 1, 1), "valid_until": date(2026, 1, 14)},
    ):
        direct.refresh_from_db()
        direct.is_active = True
        direct.valid_from = date(2026, 1, 1)
        direct.valid_until = None
        for key, value in changes.items():
            setattr(direct, key, value)
        direct.save()
        assert planner.plan(payload).blockers == [JourneyPlannerBlockerCode.ROUTE_AUTOMATION_DISABLED]


def test_unresolved_geography_and_disabled_corridor_do_not_automate():
    payload = request("SIN", "RAB", "SG", "PG")
    planner = CorridorAirJourneyPlanner()
    GeoLocation(canonical_name="SIN", country_code="SG", location_type="AIRPORT").save()
    geo("RAB", "PG")
    assert not planner.plan(payload).legs  # names cannot resolve geography
    sin = geo("SIN", "SG")
    rab = GeoLocationIdentifier.objects.get(scheme="IATA", code="RAB").location
    corridor = GeoCorridorPolicy.objects.create(
        origin=sin, destination=rab, transport_mode="AIR", valid_from=date(2026, 1, 1),
    )
    plan = planner.plan(payload)
    assert len(plan.legs) == 1
    assert plan.blockers == [JourneyPlannerBlockerCode.ROUTE_AUTOMATION_DISABLED]
    assert corridor.automation_enabled is False


def test_ambiguous_hub_iata_and_inactive_geography_fail_closed():
    sin, lae, rab = geo("SIN", "SG"), geo("LAE", "PG"), geo("RAB", "PG")
    GeoCorridorPolicy.objects.create(
        origin=sin, destination=lae, via_hub=rab, transport_mode="AIR",
        valid_from=date(2026, 1, 1), automation_enabled=True,
    )
    payload = request("SIN", "LAE", "SG", "PG")
    GeoLocationIdentifier.objects.create(location=rab, scheme="IATA", code="RBA")
    plan = CorridorAirJourneyPlanner().plan(payload)
    assert plan.legs == []
    assert JourneyPlannerBlockerCode.JOURNEY_GATEWAY_INVALID in plan.blockers
    assert JourneyPlannerBlockerCode.ROUTE_AUTOMATION_DISABLED in plan.blockers
    GeoLocationIdentifier.objects.filter(location=rab, code="RBA").delete()
    sin.is_active = False
    sin.save()
    assert CorridorAirJourneyPlanner().plan(payload).blockers == [
        JourneyPlannerBlockerCode.ROUTE_AUTOMATION_DISABLED,
    ]


def test_legacy_runtime_keeps_existing_geometry_with_no_corridor_data():
    assert GeoCorridorPolicy.objects.count() == 0
    payload = request("SIN", "LAE", "SG", "PG")
    legacy = AirJourneyPlanner().plan(payload)
    generic = CorridorAirJourneyPlanner().plan(payload)
    assert [leg.leg_key for leg in legacy.legs] == [
        "01:INTERNATIONAL_IMPORT:SIN:POM", "02:DOMESTIC_ON_FORWARDING:POM:LAE",
    ]
    assert generic.input_fingerprint != legacy.input_fingerprint
    assert generic.legs == []
    assert generic.blockers == [JourneyPlannerBlockerCode.ROUTE_AUTOMATION_DISABLED]


@pytest.mark.parametrize("role,mode,origin,destination,domain,invalid_field", [
    (LegRole.INTERNATIONAL_IMPORT, TransportMode.INTERNATIONAL_AIR,
     "SIN", "RAB", ProductCodeDomain.IMPORT, "destination_code"),
    (LegRole.DOMESTIC_ON_FORWARDING, TransportMode.DOMESTIC_AIR,
     "RAB", "LAE", ProductCodeDomain.DOMESTIC, "origin_code"),
    (LegRole.DOMESTIC_PRE_CARRIAGE, TransportMode.DOMESTIC_AIR,
     "LAE", "RAB", ProductCodeDomain.DOMESTIC, "destination_code"),
    (LegRole.INTERNATIONAL_EXPORT, TransportMode.INTERNATIONAL_AIR,
     "RAB", "SIN", ProductCodeDomain.EXPORT, "origin_code"),
])
def test_leg_validation_uses_journey_gateway_not_pom(
    role, mode, origin, destination, domain, invalid_field,
):
    customer = Company.objects.create(name="Corridor topology test", is_customer=True)
    quote = Quote.objects.create(customer=customer, mode="AIR", shipment_type="IMPORT")
    journey = ShipmentJourneyDB.objects.create(
        quote=quote, revision=1, gateway_code="RAB", rule_version="TEST",
        input_fingerprint="x" * 64,
    )
    leg = ShipmentLegDB(
        journey=journey, leg_key=f"01:{role.value}:{origin}:{destination}", sequence=1,
        role=role.value, transport_mode=mode.value,
        origin_code=origin, destination_code=destination,
        product_code_domain=domain.value,
    )
    leg.save()
    setattr(leg, invalid_field, "POM")
    with pytest.raises(ValidationError):
        leg.full_clean()
