from __future__ import annotations

from typing import Any
from uuid import UUID

from django.utils import timezone

from quotes.contracts.draft_quote_contract import DraftQuoteSchema
from quotes.spot_models import DraftQuoteDecisionDB, SpotPricingEnvelopeDB


REVIEW_KEY = "draft_quote_review"


def get_review_state(envelope: SpotPricingEnvelopeDB) -> dict[str, Any]:
    conditions = envelope.conditions_json if isinstance(envelope.conditions_json, dict) else {}
    state = dict(conditions.get(REVIEW_KEY) or {})
    if state.get("status") == "finalized":
        return state
    if DraftQuoteDecisionDB.objects.filter(envelope=envelope).exists():
        state["status"] = "in_review"
    else:
        state["status"] = "draft"
    return state


def is_finalized(envelope: SpotPricingEnvelopeDB) -> bool:
    return get_review_state(envelope).get("status") == "finalized"


def unresolved_blockers(draft_quote: DraftQuoteSchema) -> list[dict[str, Any]]:
    charges_by_id = {charge.id: charge for charge in draft_quote.suggested_charges}
    blockers: list[dict[str, Any]] = []
    for item in draft_quote.review_queue:
        item_id = str(item.get("id") or "")
        charge = charges_by_id.get(item_id)
        if charge and "PENDING_ADMIN_REVIEW" in (charge.correction_actions or []):
            continue
        blockers.append(item)
    return blockers


def review_session_payload(envelope: SpotPricingEnvelopeDB, draft_quote: DraftQuoteSchema) -> dict[str, Any]:
    state = get_review_state(envelope)
    blockers = unresolved_blockers(draft_quote)
    status = state.get("status", "draft")
    actions = []
    if status == "finalized":
        actions.append("reopen")
    elif not blockers:
        actions.append("finalize")
    return {
        "status": status,
        "finalized_by": state.get("finalized_by"),
        "finalized_at": state.get("finalized_at"),
        "remaining_blockers": len(blockers),
        "available_actions": actions,
    }


def finalize_review(envelope: SpotPricingEnvelopeDB, draft_quote: DraftQuoteSchema, user, idempotency_key: UUID) -> tuple[bool, dict[str, Any], list[dict[str, Any]]]:
    state = get_review_state(envelope)
    if state.get("status") == "finalized" and state.get("idempotency_key") == str(idempotency_key):
        return True, state, []

    blockers = unresolved_blockers(draft_quote)
    if blockers:
        return False, state, blockers

    conditions = dict(envelope.conditions_json or {})
    state = {
        "status": "finalized",
        "finalized_by": user.id,
        "finalized_at": timezone.now().isoformat(),
        "idempotency_key": str(idempotency_key),
    }
    conditions[REVIEW_KEY] = state
    envelope.conditions_json = conditions
    envelope.save(update_fields=["conditions_json"])
    return True, state, []


def reopen_review(envelope: SpotPricingEnvelopeDB, user) -> dict[str, Any]:
    conditions = dict(envelope.conditions_json or {})
    previous = dict(conditions.get(REVIEW_KEY) or {})
    state = {
        **previous,
        "status": "in_review",
        "reopened_by": user.id,
        "reopened_at": timezone.now().isoformat(),
    }
    conditions[REVIEW_KEY] = state
    envelope.conditions_json = conditions
    envelope.save(update_fields=["conditions_json"])
    return state
