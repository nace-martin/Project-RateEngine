from __future__ import annotations

from typing import Any
from uuid import UUID

from django.utils import timezone

from quotes.contracts.draft_quote_contract import DraftQuoteSchema
from quotes.intake_safety import normalize_source_analysis_summary
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


def invalidate_finalized_review(envelope: SpotPricingEnvelopeDB, user=None, reason: str = "material_change") -> bool:
    state = get_review_state(envelope)
    if state.get("status") != "finalized":
        return False

    conditions = dict(envelope.conditions_json or {})
    invalidated_state = {
        **state,
        "status": "in_review",
        "invalidated_by": getattr(user, "id", None),
        "invalidated_at": timezone.now().isoformat(),
        "invalidated_reason": reason,
    }
    conditions[REVIEW_KEY] = invalidated_state
    envelope.conditions_json = conditions
    envelope.save(update_fields=["conditions_json"])
    return True


def unresolved_blockers(
    envelope: SpotPricingEnvelopeDB,
    draft_quote: DraftQuoteSchema,
) -> list[dict[str, Any]]:
    blockers = [
        {
            **item,
            "code": str(item.get("code") or "DRAFT_QUOTE_REVIEW_ITEM"),
        }
        for item in draft_quote.review_queue
    ]
    for batch in envelope.source_batches.all():
        summary = normalize_source_analysis_summary(batch.analysis_summary_json)
        source_context = {
            "source_batch_id": str(batch.id),
            "source_batch_label": batch.label or batch.file_name or "Imported source",
        }
        if summary["risk_flags"] and not summary["reviewed_safe_to_quote"]:
            blockers.append({
                "code": "SOURCE_REVIEW_NOT_SAFE",
                "message": "Imported source review is not marked safe to quote.",
                **source_context,
            })
        if summary["requires_review_note"] and not summary["review_note"]:
            blockers.append({
                "code": "SOURCE_REVIEW_NOTE_REQUIRED",
                "message": "A non-empty source-review note is required.",
                **source_context,
            })
        if summary["risk_level"] == "HIGH" and not summary["reviewed_safe_to_quote"]:
            blockers.append({
                "code": "SOURCE_REVIEW_RISK_BLOCKING",
                "message": "High source-review risk remains unresolved.",
                "risk_level": summary["risk_level"],
                **source_context,
            })

    for line in envelope.charge_lines.filter(conditional=True):
        context = {
            "charge_line_id": str(line.id),
            "charge_label": line.description or line.source_label or "Conditional charge",
        }
        if not line.conditional_acknowledged:
            blockers.append({
                "code": "CONDITIONAL_ACKNOWLEDGEMENT_REQUIRED",
                "message": "Conditional charge applicability is unresolved and must be acknowledged by the quote owner.",
                **context,
            })
        elif not line.exclude_from_totals:
            blockers.append({
                "code": "CONDITIONAL_FIRM_TOTAL_OVERRIDE_REQUIRED",
                "message": "A conditional charge cannot remain in the firm total without an authorized override.",
                **context,
            })

    deduplicated: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for blocker in blockers:
        key = (
            blocker.get("code"),
            blocker.get("id"),
            blocker.get("source_batch_id"),
            blocker.get("charge_line_id"),
        )
        if key not in seen:
            deduplicated.append(blocker)
            seen.add(key)
    blockers = deduplicated
    return blockers


def review_session_payload(envelope: SpotPricingEnvelopeDB, draft_quote: DraftQuoteSchema) -> dict[str, Any]:
    state = get_review_state(envelope)
    blockers = unresolved_blockers(envelope, draft_quote)
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
        "blockers": blockers,
        "available_actions": actions,
    }


def finalize_review(envelope: SpotPricingEnvelopeDB, draft_quote: DraftQuoteSchema, user, idempotency_key: UUID) -> tuple[bool, dict[str, Any], list[dict[str, Any]]]:
    state = get_review_state(envelope)
    if state.get("status") == "finalized" and state.get("idempotency_key") == str(idempotency_key):
        return True, state, []

    blockers = unresolved_blockers(envelope, draft_quote)
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
