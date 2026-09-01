from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from quotes.services.spot_journey_charge_context import PHASE_16_LIVE_MARKER
from quotes.spot_models import SPEChargeLineDB, SpotPricingEnvelopeDB


PRICING_IDENTITY_VERSION = "phase16-pricing-identity-v1"
SPOT_PRICING_IDENTITY_CONTEXT_INCOMPLETE = "SPOT_PRICING_IDENTITY_CONTEXT_INCOMPLETE"
SPOT_PRICING_IDENTITY_STALE_CONTEXT = "SPOT_PRICING_IDENTITY_STALE_CONTEXT"
SPOT_PRICING_IDENTITY_DUPLICATE = "SPOT_PRICING_IDENTITY_DUPLICATE"
PRODUCTCODE_DOMAIN_MISMATCH = "PRODUCTCODE_DOMAIN_MISMATCH"

_COMPONENT_BY_BUCKET = {
    SPEChargeLineDB.Bucket.AIRFREIGHT: "FREIGHT",
    SPEChargeLineDB.Bucket.ORIGIN_CHARGES: "ORIGIN_LOCAL",
    SPEChargeLineDB.Bucket.DESTINATION_CHARGES: "DESTINATION_LOCAL",
}


@dataclass(frozen=True)
class SpotPricingIdentity:
    """Stable Phase 16 commercial identity for one resolved SPOT charge.

    The six fields returned by ``key`` are the architecture contract used by the
    later granular merge. Extra fields are audit metadata only and must not be
    used to broaden a match.
    """

    journey_revision: int
    leg_key: str
    product_code: str
    commercial_position: str
    component: str
    currency: str
    charge_line_id: str
    journey_leg_id: str
    product_code_domain: str

    @property
    def key(self) -> tuple[int, str, str, str, str, str]:
        return (
            self.journey_revision,
            self.leg_key,
            self.product_code,
            self.commercial_position,
            self.component,
            self.currency,
        )

    @property
    def blocker_id(self) -> str:
        return "spot-pricing-identity:" + "|".join(str(part) for part in self.key)

    def to_dict(self) -> dict[str, Any]:
        return {
            "identity_version": PRICING_IDENTITY_VERSION,
            "journey_revision": self.journey_revision,
            "leg_key": self.leg_key,
            "product_code": self.product_code,
            "commercial_position": self.commercial_position,
            "component": self.component,
            "currency": self.currency,
            "charge_line_id": self.charge_line_id,
            "journey_leg_id": self.journey_leg_id,
            "product_code_domain": self.product_code_domain,
        }


@dataclass(frozen=True)
class SpotPricingIdentityResolution:
    applicable: bool
    identity: SpotPricingIdentity | None
    blocker_codes: tuple[str, ...] = ()

    @property
    def ready(self) -> bool:
        return self.applicable and self.identity is not None and not self.blocker_codes


def resolve_spot_pricing_identity(line: SPEChargeLineDB) -> SpotPricingIdentityResolution:
    """Resolve a fail-closed pricing identity from trusted Phase 16 charge context.

    Legacy/non-Phase-16 lines are intentionally non-applicable so this baseline
    does not alter historical SPOT behavior. Live Phase 16 lines must have a
    current journey leg, an assigned ProductCode, complete context, and matching
    ProductCode/leg domains before an identity is considered safe.
    """

    audit = line.product_code_resolution_audit_json or {}
    if not audit.get(PHASE_16_LIVE_MARKER):
        return SpotPricingIdentityResolution(applicable=False, identity=None)

    blockers: list[str] = []
    context = line.charge_context_json if isinstance(line.charge_context_json, dict) else {}
    leg = line.journey_leg
    product_code = line.effective_resolved_product_code

    if leg is None:
        blockers.append("CHARGE_LEG_UNASSIGNED")

    if audit.get("status") != "ASSIGNED" or product_code is None:
        blockers.append("PRODUCTCODE_LEG_CONTEXT_UNRESOLVED")

    component = _COMPONENT_BY_BUCKET.get(line.bucket)
    raw_revision = context.get("journey_revision")
    leg_key = str(context.get("leg_key") or "").strip()
    product_code_value = str(getattr(product_code, "code", "") or "").strip().upper()
    commercial_position = str(context.get("commercial_position") or "").strip().upper()
    context_domain = str(context.get("product_code_domain") or "").strip().upper()
    currency = str(line.currency or "").strip().upper()

    try:
        journey_revision = int(raw_revision) if raw_revision is not None else None
    except (TypeError, ValueError):
        journey_revision = None

    if not all(
        (
            journey_revision,
            leg_key,
            product_code_value,
            commercial_position,
            component,
            currency,
            context_domain,
        )
    ):
        blockers.append(SPOT_PRICING_IDENTITY_CONTEXT_INCOMPLETE)

    if leg is not None:
        leg_revision = int(leg.journey.revision)
        leg_domain = str(leg.product_code_domain or "").strip().upper()
        if (
            journey_revision != leg_revision
            or leg_key != str(leg.leg_key or "").strip()
            or (context_domain and context_domain != leg_domain)
        ):
            blockers.append(SPOT_PRICING_IDENTITY_STALE_CONTEXT)

        if product_code is not None:
            product_domain = str(product_code.domain or "").strip().upper()
            if product_domain != leg_domain or (context_domain and product_domain != context_domain):
                blockers.append(PRODUCTCODE_DOMAIN_MISMATCH)

    blocker_codes = tuple(dict.fromkeys(blockers))
    if blocker_codes:
        return SpotPricingIdentityResolution(
            applicable=True,
            identity=None,
            blocker_codes=blocker_codes,
        )

    identity = SpotPricingIdentity(
        journey_revision=journey_revision,
        leg_key=leg_key,
        product_code=product_code_value,
        commercial_position=commercial_position,
        component=component,
        currency=currency,
        charge_line_id=str(line.id),
        journey_leg_id=str(line.journey_leg_id),
        product_code_domain=context_domain,
    )
    return SpotPricingIdentityResolution(applicable=True, identity=identity)


def pricing_identity_review_blockers(envelope: SpotPricingEnvelopeDB) -> list[dict[str, Any]]:
    """Return envelope-level Phase 16 pricing-identity blockers.

    Existing journey/ProductCode review blockers remain authoritative for basic
    unresolved lines. This layer adds the identity-specific safety checks needed
    before granular replacement can be enabled: stale/incomplete context,
    ProductCode-domain mismatch, and exact duplicate commercial identities.
    """

    lines = list(
        envelope.charge_lines.select_related(
            "journey_leg__journey",
            "resolved_product_code",
            "manual_resolved_product_code",
        ).all()
    )

    blockers: list[dict[str, Any]] = []
    identities: dict[tuple[int, str, str, str, str, str], list[SpotPricingIdentity]] = {}

    identity_specific_codes = {
        SPOT_PRICING_IDENTITY_CONTEXT_INCOMPLETE,
        SPOT_PRICING_IDENTITY_STALE_CONTEXT,
        PRODUCTCODE_DOMAIN_MISMATCH,
    }

    for line in lines:
        resolution = resolve_spot_pricing_identity(line)
        for code in resolution.blocker_codes:
            if code not in identity_specific_codes:
                continue
            blockers.append({
                "code": code,
                "message": _identity_blocker_message(code),
                "charge_line_id": str(line.id),
                "charge_label": line.description or line.source_label or "SPOT charge",
                "journey_leg_id": str(line.journey_leg_id) if line.journey_leg_id else None,
            })

        if resolution.ready and resolution.identity is not None:
            identities.setdefault(resolution.identity.key, []).append(resolution.identity)

    for duplicate_group in identities.values():
        if len(duplicate_group) < 2:
            continue
        first = duplicate_group[0]
        blockers.append({
            "id": first.blocker_id,
            "code": SPOT_PRICING_IDENTITY_DUPLICATE,
            "message": (
                "Multiple SPOT charges resolve to the same trusted pricing identity; "
                "the operator must resolve the duplicate before pricing."
            ),
            "charge_line_ids": [item.charge_line_id for item in duplicate_group],
            "pricing_identity": first.to_dict(),
        })

    return blockers


def _identity_blocker_message(code: str) -> str:
    messages = {
        SPOT_PRICING_IDENTITY_CONTEXT_INCOMPLETE: (
            "SPOT pricing identity is incomplete for the trusted journey leg."
        ),
        SPOT_PRICING_IDENTITY_STALE_CONTEXT: (
            "SPOT pricing identity context no longer matches the persisted journey leg."
        ),
        PRODUCTCODE_DOMAIN_MISMATCH: (
            "Resolved ProductCode domain does not match the trusted journey leg domain."
        ),
    }
    return messages.get(code, "SPOT pricing identity is unresolved.")
