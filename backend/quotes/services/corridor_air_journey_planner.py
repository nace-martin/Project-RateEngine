"""Corridor-backed air journey geometry; not wired into quote/SPOT runtime yet."""

from __future__ import annotations

from datetime import date

from core.corridor_models import GeoCorridorPolicy
from core.corridor_models import TransportMode as CorridorMode
from core.geo_models import GeoLocation, GeoLocationIdentifier
from django.db.models import Q
from pricing_v4.contracts.charge_context import (
    JourneyDirection,
    LegRole,
    ProductCodeDomain,
    TransportMode,
)

from quotes.contracts.journey_contracts import (
    PNG_COUNTRY_CODE,
    JourneyLeg,
    JourneyPlan,
    JourneyRequest,
    JourneyStatus,
    coerce_journey_request,
)
from quotes.contracts.journey_contracts import (
    JourneyPlannerBlockerCode as Blocker,
)


def _location(code: str, country: str) -> GeoLocation | None:
    identifiers = list(GeoLocationIdentifier.objects.select_related("location").filter(
        scheme=GeoLocationIdentifier.Scheme.IATA, code=code,
    )[:2])
    if len(identifiers) != 1:
        return None
    location = identifiers[0].location
    if (location.is_active and location.location_type == GeoLocation.LocationType.AIRPORT
            and location.country_code == country):
        return location
    return None


def _iata(location: GeoLocation) -> str | None:
    identifiers = list(GeoLocationIdentifier.objects.filter(
        location=location, scheme=GeoLocationIdentifier.Scheme.IATA,
    ).values_list("code", flat=True)[:2])
    return identifiers[0] if len(identifiers) == 1 else None


class CorridorAirJourneyPlanner:
    """Build one or two air legs from one exact, valid corridor."""

    rule_version = "CORRIDOR_AIR_JOURNEY_PLANNER_V1"

    def plan(self, request: JourneyRequest | dict) -> JourneyPlan:
        request = coerce_journey_request(request)
        blockers = [Blocker(code) for code in request.raw_evidence.get("_validation_blockers", [])]
        if request.service_domain != CorridorMode.AIR or request.quote_date == date(1970, 1, 1):
            blockers.append(Blocker.JOURNEY_REQUEST_INVALID)
        if any(request.raw_evidence.get(key) for key in (
            "via", "via_code", "via_codes", "intermediate_code", "intermediate_codes", "stops",
        )):
            blockers.append(Blocker.JOURNEY_MULTI_STOP_UNSUPPORTED)
        direction = None
        if not request.origin_country or not request.destination_country:
            blockers.append(Blocker.JOURNEY_COUNTRY_MISSING)
        elif request.origin_country != PNG_COUNTRY_CODE and request.destination_country == PNG_COUNTRY_CODE:
            direction = JourneyDirection.IMPORT
        elif request.origin_country == PNG_COUNTRY_CODE and request.destination_country != PNG_COUNTRY_CODE:
            direction = JourneyDirection.EXPORT
        else:
            blockers.append(Blocker.JOURNEY_DIRECTION_UNSUPPORTED)

        legs: list[JourneyLeg] = []
        gateway = ""
        corridor = None
        if not blockers:
            origin = _location(request.customer_origin_code, request.origin_country)
            destination = _location(request.customer_destination_code, request.destination_country)
            if origin and destination:
                corridors = list(GeoCorridorPolicy.objects.select_related("via_hub").filter(
                    origin=origin, destination=destination, transport_mode=CorridorMode.AIR,
                    is_active=True, valid_from__lte=request.quote_date,
                ).filter(Q(valid_until__isnull=True) | Q(valid_until__gte=request.quote_date))[:2])
                if len(corridors) == 1:
                    corridor = corridors[0]
            if corridor is not None:
                via = corridor.via_hub
                gateway = _iata(via) if via else (
                    request.customer_destination_code if direction == JourneyDirection.IMPORT
                    else request.customer_origin_code
                )
                if (not gateway or (via and (not via.is_active
                        or via.location_type != GeoLocation.LocationType.AIRPORT
                        or via.country_code != PNG_COUNTRY_CODE))):
                    blockers.append(Blocker.JOURNEY_GATEWAY_INVALID)
                else:
                    legs = self._legs(request, direction, gateway, bool(via))
                    if not corridor.automation_enabled:
                        blockers.append(Blocker.ROUTE_AUTOMATION_DISABLED)
            else:
                blockers.append(Blocker.ROUTE_AUTOMATION_DISABLED)
        if blockers and Blocker.ROUTE_AUTOMATION_DISABLED not in blockers:
            blockers.append(Blocker.ROUTE_AUTOMATION_DISABLED)
        return JourneyPlan(
            request=request, direction=direction, pattern=None, gateway_code=gateway,
            route_policy_key=str(corridor.pk) if corridor else "",
            rule_version=self.rule_version, input_fingerprint=request.input_fingerprint(self.rule_version),
            status=JourneyStatus.NEEDS_REVIEW if blockers else JourneyStatus.PLANNED,
            legs=legs, blockers=list(dict.fromkeys(blockers)),
        )

    @staticmethod
    def _legs(request: JourneyRequest, direction: JourneyDirection, gateway: str, transit: bool) -> list[JourneyLeg]:
        origin, destination = request.customer_origin_code, request.customer_destination_code
        if direction == JourneyDirection.IMPORT:
            steps = [
                (LegRole.INTERNATIONAL_IMPORT, TransportMode.INTERNATIONAL_AIR,
                 origin, gateway, ProductCodeDomain.IMPORT),
            ]
            if transit:
                steps.append((LegRole.DOMESTIC_ON_FORWARDING, TransportMode.DOMESTIC_AIR,
                              gateway, destination, ProductCodeDomain.DOMESTIC))
        else:
            steps = []
            if transit:
                steps.append((LegRole.DOMESTIC_PRE_CARRIAGE, TransportMode.DOMESTIC_AIR,
                              origin, gateway, ProductCodeDomain.DOMESTIC))
            steps.append((LegRole.INTERNATIONAL_EXPORT, TransportMode.INTERNATIONAL_AIR,
                          gateway, destination, ProductCodeDomain.EXPORT))
        return [JourneyLeg(
            sequence=sequence, leg_key=f"{sequence:02d}:{role.value}:{start}:{end}",
            role=role, transport_mode=mode, origin_code=start, destination_code=end,
            product_code_domain=domain, service_scope=request.service_scope,
            chargeable_weight=request.chargeable_weight,
        ) for sequence, (role, mode, start, end, domain) in enumerate(steps, 1)]
