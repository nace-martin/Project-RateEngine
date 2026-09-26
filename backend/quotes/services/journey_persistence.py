from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from core.corridor_models import GeoCorridorPolicy, TransportMode
from core.geo_models import GeoLocation, GeoLocationIdentifier
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q

from quotes.contracts.journey_contracts import JourneyPlan, JourneyPlannerBlockerCode
from quotes.models import Quote, ShipmentJourneyDB, ShipmentLegDB
from quotes.spot_models import SpotPricingEnvelopeDB


@dataclass(frozen=True)
class RoutePolicyState:
    enabled: bool
    disabled_reason: str
    source: str
    corridor_id: str | None = None

    def to_dict(self) -> dict:
        return {
            "enabled": self.enabled,
            "disabled_reason": self.disabled_reason,
            "source": self.source,
            "corridor_id": self.corridor_id,
        }


def _geo_for_iata(code: str, country: str) -> GeoLocation | None:
    try:
        location = GeoLocationIdentifier.objects.select_related("location").get(
            scheme=GeoLocationIdentifier.Scheme.IATA, code=code
        ).location
    except (GeoLocationIdentifier.DoesNotExist, GeoLocationIdentifier.MultipleObjectsReturned):
        return None
    if (location.is_active and location.location_type == GeoLocation.LocationType.AIRPORT
            and location.country_code == country):
        return location
    return None


def get_route_policy_state(plan: JourneyPlan) -> RoutePolicyState:
    request = plan.request
    if (not plan.pattern or request.service_domain != TransportMode.AIR
            or request.quote_date == date(1970, 1, 1) or len(plan.legs) not in (1, 2)):
        return RoutePolicyState(False, "Route geography or date is unresolved.", "unresolved")
    legs = plan.legs
    if (legs[0].origin_code != request.customer_origin_code
            or legs[-1].destination_code != request.customer_destination_code
            or (len(legs) == 2 and (legs[0].destination_code != plan.gateway_code
                                   or legs[1].origin_code != plan.gateway_code))):
        return RoutePolicyState(False, "Planned legs do not match the route.", "unresolved")
    origin = _geo_for_iata(request.customer_origin_code, request.origin_country)
    destination = _geo_for_iata(request.customer_destination_code, request.destination_country)
    via = _geo_for_iata(plan.gateway_code, "PG") if len(plan.legs) == 2 else None
    if not origin or not destination or (len(plan.legs) == 2 and not via):
        return RoutePolicyState(False, "Route geography is unresolved.", "unresolved")
    corridors = list(GeoCorridorPolicy.objects.filter(
        origin=origin, destination=destination, via_hub=via,
        transport_mode=TransportMode.AIR,
    )[:2])
    if len(corridors) != 1:
        return RoutePolicyState(False, "Corridor is missing or ambiguous.", "missing" if not corridors else "ambiguous")
    corridor = corridors[0]
    enabled = (corridor.is_active and corridor.automation_enabled
               and corridor.valid_from <= request.quote_date
               and (corridor.valid_until is None or request.quote_date <= corridor.valid_until))
    return RoutePolicyState(enabled, "" if enabled else "Corridor automation is disabled or date-invalid.",
                            "corridor", str(corridor.pk))


class ShipmentJourneyPersistenceService:
    """Atomically persists Phase 16E-A journey plans without pricing side effects."""

    def persist_plan(
        self,
        *,
        plan: JourneyPlan,
        quote: Quote | None = None,
        spot_envelope: SpotPricingEnvelopeDB | None = None,
        created_by=None,
    ) -> ShipmentJourneyDB:
        if quote is None and spot_envelope is None:
            raise ValidationError("Journey persistence requires a quote or SPOT envelope parent.")
        return self._persist_plan(plan=plan, quote=quote, spot_envelope=spot_envelope, created_by=created_by)

    @transaction.atomic
    def attach_second_parent_reference(
        self,
        *,
        journey: ShipmentJourneyDB,
        quote: Quote | None = None,
        spot_envelope: SpotPricingEnvelopeDB | None = None,
    ) -> ShipmentJourneyDB:
        journey = ShipmentJourneyDB.objects.select_for_update().get(pk=journey.pk)
        if quote is None and spot_envelope is None:
            raise ValidationError("A missing quote or SPOT envelope parent is required.")
        self._lock_parent(quote=quote, spot_envelope=spot_envelope)
        if quote is not None:
            if journey.quote_id and journey.quote_id != quote.pk:
                raise ValidationError("Shipment journey is already linked to a different quote.")
            existing_quote_revision = ShipmentJourneyDB.objects.select_for_update().filter(quote=quote, revision=journey.revision).exclude(pk=journey.pk).first()
            if existing_quote_revision is not None:
                raise ValidationError("Quote journey revision already exists; refusing duplicate parent handover.")
            journey.quote = quote
        if spot_envelope is not None:
            if journey.spot_envelope_id and journey.spot_envelope_id != spot_envelope.pk:
                raise ValidationError("Shipment journey is already linked to a different SPOT envelope.")
            existing_spot_revision = ShipmentJourneyDB.objects.select_for_update().filter(spot_envelope=spot_envelope, revision=journey.revision).exclude(pk=journey.pk).first()
            if existing_spot_revision is not None:
                raise ValidationError("SPOT journey revision already exists; refusing duplicate parent handover.")
            journey.spot_envelope = spot_envelope
        journey.save(update_fields=["quote", "spot_envelope"])
        return journey

    @transaction.atomic
    def _persist_plan(
        self,
        *,
        plan: JourneyPlan,
        quote: Quote | None,
        spot_envelope: SpotPricingEnvelopeDB | None,
        created_by,
    ) -> ShipmentJourneyDB:
        self._lock_parent(quote=quote, spot_envelope=spot_envelope)
        relevant = list(self._journeys(quote=quote, spot_envelope=spot_envelope).order_by("revision", "created_at", "id"))
        latest = self._latest_relevant(relevant)
        self._validate_parent_handover(relevant, quote=quote, spot_envelope=spot_envelope)

        if latest is not None and latest.input_fingerprint == plan.input_fingerprint:
            return self._attach_missing_parents(latest, quote=quote, spot_envelope=spot_envelope)

        revision = 1 if latest is None else max(item.revision for item in relevant) + 1
        blockers = self._combined_blockers(plan)
        journey = ShipmentJourneyDB(
            quote=quote,
            spot_envelope=spot_envelope,
            revision=revision,
            direction=plan.direction.value if plan.direction else "",
            pattern=plan.pattern.value if plan.pattern else "",
            gateway_code=plan.gateway_code,
            customer_origin_code=plan.request.customer_origin_code,
            customer_destination_code=plan.request.customer_destination_code,
            route_policy_key=plan.route_policy_key,
            rule_version=plan.rule_version,
            input_fingerprint=plan.input_fingerprint,
            status=ShipmentJourneyDB.Status.NEEDS_REVIEW if blockers else ShipmentJourneyDB.Status.PLANNED,
            blockers_json=[blocker.value for blocker in blockers],
            supersedes=latest,
            created_by=created_by,
        )
        journey.save()
        self._persist_legs(journey, plan)
        if latest and latest.status != ShipmentJourneyDB.Status.FINALIZED:
            latest.status = ShipmentJourneyDB.Status.SUPERSEDED
            latest.save(update_fields=["status"])
        return journey

    def _lock_parent(self, *, quote: Quote | None, spot_envelope: SpotPricingEnvelopeDB | None) -> None:
        if quote is not None:
            Quote.objects.select_for_update().get(pk=quote.pk)
        if spot_envelope is not None:
            SpotPricingEnvelopeDB.objects.select_for_update().get(pk=spot_envelope.pk)

    def _journeys(self, *, quote: Quote | None, spot_envelope: SpotPricingEnvelopeDB | None):
        query = Q()
        if quote is not None:
            query |= Q(quote=quote)
        if spot_envelope is not None:
            query |= Q(spot_envelope=spot_envelope)
        return ShipmentJourneyDB.objects.select_for_update().filter(query)

    @staticmethod
    def _latest_relevant(journeys: list[ShipmentJourneyDB]) -> ShipmentJourneyDB | None:
        if not journeys:
            return None
        return max(journeys, key=lambda item: (item.revision, item.created_at, str(item.id)))

    def _validate_parent_handover(
        self,
        journeys: list[ShipmentJourneyDB],
        *,
        quote: Quote | None,
        spot_envelope: SpotPricingEnvelopeDB | None,
    ) -> None:
        if quote is None or spot_envelope is None:
            return
        quote_latest = self._latest_relevant([item for item in journeys if item.quote_id == quote.pk])
        spot_latest = self._latest_relevant([item for item in journeys if item.spot_envelope_id == spot_envelope.pk])
        if quote_latest is None or spot_latest is None or quote_latest.pk == spot_latest.pk:
            return
        if quote_latest.input_fingerprint != spot_latest.input_fingerprint:
            raise ValidationError("Conflicting quote and SPOT journey histories; refusing parent handover.")
        raise ValidationError("Quote and SPOT journey histories resolve to separate revisions; refusing duplicate handover.")

    def _attach_missing_parents(
        self,
        journey: ShipmentJourneyDB,
        *,
        quote: Quote | None,
        spot_envelope: SpotPricingEnvelopeDB | None,
    ) -> ShipmentJourneyDB:
        if (quote is None or journey.quote_id == quote.pk) and (spot_envelope is None or journey.spot_envelope_id == spot_envelope.pk):
            return journey
        return self.attach_second_parent_reference(journey=journey, quote=quote, spot_envelope=spot_envelope)

    def _combined_blockers(self, plan: JourneyPlan) -> list[JourneyPlannerBlockerCode]:
        blockers = list(plan.blockers)
        policy = get_route_policy_state(plan)
        if not policy.enabled:
            blockers.append(JourneyPlannerBlockerCode.ROUTE_AUTOMATION_DISABLED)
        return self._dedupe(blockers)

    def _persist_legs(self, journey: ShipmentJourneyDB, plan: JourneyPlan) -> None:
        expected_sequence = 1
        for leg in plan.legs:
            if leg.sequence != expected_sequence:
                raise ValidationError("Journey leg sequence must start at 1 and be contiguous.")
            row = ShipmentLegDB(
                journey=journey,
                leg_key=leg.leg_key,
                sequence=leg.sequence,
                role=leg.role.value,
                transport_mode=leg.transport_mode.value,
                origin_code=leg.origin_code,
                destination_code=leg.destination_code,
                product_code_domain=leg.product_code_domain.value,
                required=leg.required,
                service_scope=leg.service_scope,
                chargeable_weight=leg.chargeable_weight,
                status=ShipmentLegDB.Status.NEEDS_REVIEW if leg.blockers else ShipmentLegDB.Status.PLANNED,
                rate_coverage_status=leg.rate_coverage_status,
                blockers_json=[blocker.value for blocker in leg.blockers],
            )
            row.save()
            expected_sequence += 1

    @staticmethod
    def _dedupe(blockers: Iterable[JourneyPlannerBlockerCode]) -> list[JourneyPlannerBlockerCode]:
        seen: set[JourneyPlannerBlockerCode] = set()
        output: list[JourneyPlannerBlockerCode] = []
        for blocker in blockers:
            if blocker not in seen:
                output.append(blocker)
                seen.add(blocker)
        return output
