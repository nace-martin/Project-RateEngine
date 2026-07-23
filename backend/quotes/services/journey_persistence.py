from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q

from quotes.contracts.journey_contracts import JourneyPlan, JourneyPlannerBlockerCode
from quotes.models import Quote, RouteAutomationPolicyDB, ShipmentJourneyDB, ShipmentLegDB
from quotes.spot_models import SpotPricingEnvelopeDB


@dataclass(frozen=True)
class RoutePolicyState:
    route_pattern: str
    enabled: bool
    disabled_reason: str
    required_rate_gate: dict
    source: str

    def to_dict(self) -> dict:
        return {
            "route_pattern": self.route_pattern,
            "enabled": self.enabled,
            "disabled_reason": self.disabled_reason,
            "required_rate_gate": self.required_rate_gate,
            "source": self.source,
        }


def get_route_policy_state(route_pattern: str | None) -> RoutePolicyState:
    pattern = str(route_pattern or "").strip().upper()
    if not pattern:
        return RoutePolicyState("", False, "No route pattern was planned.", {}, "missing")
    policy = RouteAutomationPolicyDB.objects.filter(route_pattern=pattern).first()
    if policy is None:
        return RoutePolicyState(pattern, False, "Missing route automation policy; route automation is disabled by default.", {}, "missing")
    return RoutePolicyState(
        route_pattern=policy.route_pattern,
        enabled=bool(policy.enabled),
        disabled_reason=policy.disabled_reason,
        required_rate_gate=policy.required_rate_gate_json or {},
        source="database",
    )


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
        policy = get_route_policy_state(plan.pattern.value if plan.pattern else None)
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
