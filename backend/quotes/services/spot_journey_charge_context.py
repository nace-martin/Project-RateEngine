from __future__ import annotations

import hashlib
import json
from datetime import date

from pricing_v4.contracts.charge_context import (
    ChargeContext,
    CommercialPosition,
    JourneyDirection,
    JourneyPattern,
    LegRole,
    ProductCodeDomain,
    ProductCodeResolutionStatus,
    TransportMode,
)
from pricing_v4.services.leg_aware_product_code_resolver import LegAwareProductCodeResolver
from quotes.models import ShipmentJourneyDB, ShipmentLegDB
from quotes.spot_models import SPEChargeLineDB


PHASE_16_LIVE_MARKER = "phase_16_live"
LEG_ASSIGNMENT_REQUIRED = "LEG_ASSIGNMENT_REQUIRED"


_BUCKET_POSITION = {
    SPEChargeLineDB.Bucket.ORIGIN_CHARGES: CommercialPosition.ORIGIN,
    SPEChargeLineDB.Bucket.AIRFREIGHT: CommercialPosition.FREIGHT,
    SPEChargeLineDB.Bucket.DESTINATION_CHARGES: CommercialPosition.DESTINATION,
}


def is_live_quote_linked_spot_line(line: SPEChargeLineDB) -> bool:
    envelope = line.envelope
    context = envelope.shipment_context_json if isinstance(envelope.shipment_context_json, dict) else {}
    return bool(
        envelope.quote_id
        and str(context.get("quote_id") or "") == str(envelope.quote_id)
        and envelope.shipment_journeys.exists()
    )


def apply_live_spot_leg_context(line: SPEChargeLineDB) -> SPEChargeLineDB:
    """Attach trusted journey-leg context and run the leg-aware ProductCode resolver.

    This is deliberately fail-closed. Single-leg journeys are deterministic for
    every existing SPOT bucket. On multi-leg journeys only the airfreight bucket
    is automatically attached to the unique international leg; origin and
    destination buckets remain unassigned until the operator/business movement
    is explicit rather than guessed.
    """
    if not is_live_quote_linked_spot_line(line):
        return line

    journey = (
        line.envelope.shipment_journeys
        .exclude(status=ShipmentJourneyDB.Status.SUPERSEDED)
        .order_by("-revision", "-created_at", "-id")
        .first()
    )
    if journey is None:
        return line

    leg = _select_leg_for_line(journey, line)
    if leg is None:
        line.journey_leg = None
        line.charge_context_json = {}
        line.product_code_resolution_audit_json = {
            PHASE_16_LIVE_MARKER: True,
            "status": LEG_ASSIGNMENT_REQUIRED,
            "review_reason": "SPOT charge cannot be assigned to a journey leg without guessing.",
            "journey_id": str(journey.id),
            "journey_revision": journey.revision,
            "bucket": line.bucket,
        }
        line.save(update_fields=["journey_leg", "charge_context_json", "product_code_resolution_audit_json"])
        return line

    context = _build_charge_context(journey, leg, line)
    requested_product = line.effective_resolved_product_code
    result = LegAwareProductCodeResolver().resolve(
        context,
        requested_product_code=requested_product,
    )
    audit = result.to_dict()
    audit[PHASE_16_LIVE_MARKER] = True

    line.journey_leg = leg
    line.charge_context_json = context.to_audit_dict()
    line.product_code_resolution_audit_json = audit

    update_fields = ["journey_leg", "charge_context_json", "product_code_resolution_audit_json"]
    if result.status == ProductCodeResolutionStatus.ASSIGNED and result.selected_product_code_id:
        line.resolved_product_code_id = result.selected_product_code_id
        update_fields.append("resolved_product_code")

    line.save(update_fields=update_fields)
    return line


def phase_16_resolution_blockers(line: SPEChargeLineDB) -> list[str]:
    audit = line.product_code_resolution_audit_json or {}
    if not audit.get(PHASE_16_LIVE_MARKER):
        return []
    if not line.journey_leg_id:
        return ["Journey leg unassigned"]
    if audit.get("status") != ProductCodeResolutionStatus.ASSIGNED.value:
        blocker_codes = audit.get("blocker_codes") or []
        suffix = f" ({', '.join(str(code) for code in blocker_codes)})" if blocker_codes else ""
        return [f"Leg-aware ProductCode unresolved{suffix}"]
    return []


def _select_leg_for_line(journey: ShipmentJourneyDB, line: SPEChargeLineDB) -> ShipmentLegDB | None:
    legs = list(journey.legs.order_by("sequence", "id"))
    if len(legs) == 1:
        return legs[0]

    if line.bucket == SPEChargeLineDB.Bucket.AIRFREIGHT:
        international = [
            leg
            for leg in legs
            if leg.role in {LegRole.INTERNATIONAL_IMPORT.value, LegRole.INTERNATIONAL_EXPORT.value}
        ]
        if len(international) == 1:
            return international[0]
    return None


def _build_charge_context(
    journey: ShipmentJourneyDB,
    leg: ShipmentLegDB,
    line: SPEChargeLineDB,
) -> ChargeContext:
    position = _BUCKET_POSITION[line.bucket]
    operational_location = ""
    if position == CommercialPosition.ORIGIN:
        operational_location = leg.origin_code
    elif position == CommercialPosition.DESTINATION:
        operational_location = leg.destination_code

    canonical_code = line.canonical_charge_type.code if line.canonical_charge_type_id else ""
    effective_date = _effective_date(line)
    payload = {
        "journey_id": str(journey.id),
        "journey_revision": journey.revision,
        "leg_id": str(leg.id),
        "leg_key": leg.leg_key,
        "journey_direction": journey.direction,
        "journey_pattern": journey.pattern,
        "leg_role": leg.role,
        "leg_sequence": leg.sequence,
        "product_code_domain": leg.product_code_domain,
        "commercial_position": position.value,
        "operational_location": operational_location,
        "transport_mode": leg.transport_mode,
        "canonical_charge_type": canonical_code,
        "charge_family": line.bucket,
        "calculation_basis": line.calculation_basis or line.unit,
        "service_scope": leg.service_scope or line.service_scope_snapshot,
        "currency": line.currency,
        "tax_treatment": None,
        "effective_date": effective_date.isoformat() if effective_date else None,
        "source_evidence": {
            "spot_envelope_id": str(line.envelope_id),
            "charge_line_id": str(line.id),
            "source_batch_id": str(line.source_batch_id) if line.source_batch_id else None,
            "source_reference": line.source_reference,
            "source_line_identity": line.source_line_identity,
        },
    }
    fingerprint_payload = json.dumps(payload, sort_keys=True, default=str)
    payload["context_fingerprint"] = hashlib.sha256(fingerprint_payload.encode()).hexdigest()
    return ChargeContext(
        journey_id=payload["journey_id"],
        journey_revision=payload["journey_revision"],
        leg_id=payload["leg_id"],
        leg_key=payload["leg_key"],
        journey_direction=JourneyDirection(payload["journey_direction"]),
        journey_pattern=JourneyPattern(payload["journey_pattern"]),
        leg_role=LegRole(payload["leg_role"]),
        leg_sequence=payload["leg_sequence"],
        product_code_domain=ProductCodeDomain(payload["product_code_domain"]),
        commercial_position=position,
        operational_location=payload["operational_location"],
        transport_mode=TransportMode(payload["transport_mode"]),
        canonical_charge_type=payload["canonical_charge_type"],
        charge_family=payload["charge_family"],
        calculation_basis=payload["calculation_basis"],
        service_scope=payload["service_scope"],
        currency=payload["currency"],
        tax_treatment=payload["tax_treatment"],
        effective_date=effective_date,
        source_evidence=payload["source_evidence"],
        context_fingerprint=payload["context_fingerprint"],
    )


def _effective_date(line: SPEChargeLineDB) -> date | None:
    quote = line.envelope.quote
    if quote and quote.created_at:
        return quote.created_at.date()
    context = line.envelope.shipment_context_json if isinstance(line.envelope.shipment_context_json, dict) else {}
    raw = context.get("quote_date")
    try:
        return date.fromisoformat(str(raw)) if raw else None
    except ValueError:
        return None
