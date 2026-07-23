from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from django.core.exceptions import ValidationError
from django.db import transaction

from quotes.contracts.journey_contracts import JourneyPlan, JourneyPlannerBlockerCode, JourneyStatus
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
        if plan.pattern is None:
            return self._persist_blocked(plan=plan, quote=quote, spot_envelope=spot_envelope, created_by=created_by)
        return self._persist_blocked(plan=plan, quote=quote, spot_envelope=spot_envelope, created_by=created_by)

    @transaction.atomic
    def _persist_blocked(
        self,
        *,
        plan: JourneyPlan,
        quote: Quote | None,
        spot_envelope: SpotPricingEnvelopeDB | None,
        created_by,
    ) -> ShipmentJourneyDB:
        self._lock_parent(quote=quote, spot_envelope=spot_envelope)
        existing = self._journeys(quote=quote, spot_envelope=spot_envelope).filter(input_fingerprint=plan.input_fingerprint).order_by("revision").first()
        if existing is not None:
            return existing

        latest = self._journeys(quote=quote, spot_envelope=spot_envelope).order_by("-revision").first()
        revision = 1 if latest is None else latest.revision + 1
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
            status=ShipmentJourneyDB.Status.BLOCKED if blockers else ShipmentJourneyDB.Status.PLANNED,
            blockers_json=[blocker.value for blocker in blockers],
            supersedes=latest,
            created_by=created_by,
        )
        journey.full_clean()
        journey.save()
        self._persist_legs(journey, plan)
        return journey

    def _lock_parent(self, *, quote: Quote | None, spot_envelope: SpotPricingEnvelopeDB | None) -> None:
        if quote is not None:
            Quote.objects.select_for_update().get(pk=quote.pk)
        if spot_envelope is not None:
            SpotPricingEnvelopeDB.objects.select_for_update().get(pk=spot_envelope.pk)

    def _journeys(self, *, quote: Quote | None, spot_envelope: SpotPricingEnvelopeDB | None):
        qs = ShipmentJourneyDB.objects.select_for_update()
        if quote is not None and spot_envelope is not None:
            return qs.filter(quote=quote, spot_envelope=spot_envelope)
        if quote is not None:
            return qs.filter(quote=quote)
        return qs.filter(spot_envelope=spot_envelope)

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
                status=ShipmentLegDB.Status.BLOCKED if leg.blockers else ShipmentLegDB.Status.PLANNED,
                rate_coverage_status=leg.rate_coverage_status,
                blockers_json=[blocker.value for blocker in leg.blockers],
            )
            row.full_clean()
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
