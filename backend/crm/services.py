from django.db import transaction
from django.utils import timezone

from .models import Interaction, Opportunity


WON_SOURCE_TYPES = {
    "QUOTE_ACCEPTED",
    "SHIPMENT_CREATED",
    "IMPORT_JOB_CREATED",
    "CLEARANCE_FILE_CREATED",
    "AGENT_PREALERT_RECEIVED",
    "MANUAL",
}


QUOTE_EVENT_TYPES = {
    "QUOTE_CREATED",
    "QUOTE_FINALIZED",
    "QUOTE_SENT",
    "QUOTE_ACCEPTED",
    "QUOTE_LOST",
    "QUOTE_EXPIRED",
}


def _system_interaction(opportunity, actor, event_type: str, summary: str, outcomes: str = "") -> Interaction:
    return Interaction.objects.create(
        company=opportunity.company,
        opportunity=opportunity,
        author=actor,
        interaction_type=Interaction.InteractionType.SYSTEM,
        summary=summary,
        outcomes=outcomes,
        is_system_generated=True,
        system_event_type=event_type,
    )


def create_quote_system_interaction(opportunity, quote, actor, event_type: str, summary: str, outcomes: str = ""):
    event_type = str(event_type or "").strip().upper()
    if event_type not in QUOTE_EVENT_TYPES:
        raise ValueError(f"Invalid quote CRM event type: {event_type}")

    quote_id = str(getattr(quote, "id", "") or "")
    dedupe_token = f"quote_id={quote_id}" if quote_id else ""
    existing = Interaction.objects.filter(
        opportunity=opportunity,
        is_system_generated=True,
        system_event_type=event_type,
    )
    if dedupe_token:
        existing = existing.filter(outcomes__contains=dedupe_token)
    if existing.exists():
        return None

    normalized_outcomes = outcomes or ""
    if dedupe_token and dedupe_token not in normalized_outcomes:
        normalized_outcomes = f"{normalized_outcomes}\n{dedupe_token}".strip()

    return _system_interaction(
        opportunity,
        actor,
        event_type,
        summary,
        outcomes=normalized_outcomes,
    )


@transaction.atomic
def mark_opportunity_quoted(opportunity, quote=None, actor=None):
    locked = Opportunity.objects.select_for_update().get(pk=opportunity.pk)
    changed = locked.status in {Opportunity.Status.NEW, Opportunity.Status.QUALIFIED}
    if changed:
        locked.status = Opportunity.Status.QUOTED
        locked.save(update_fields=["status", "updated_at"])

    quote_label = getattr(quote, "quote_number", None) or (str(quote.id) if quote else "")
    quote_id = str(getattr(quote, "id", "") or "")
    if quote_id and locked.interactions.filter(
        is_system_generated=True,
        system_event_type="OPPORTUNITY_QUOTED",
        outcomes__contains=f"quote_id={quote_id}",
    ).exists():
        return locked

    summary = "Opportunity marked quoted."
    outcomes = "Status changed to QUOTED." if changed else f"Status remains {locked.status}."
    if quote_id:
        outcomes = f"{outcomes}\nquote_id={quote_id}"
    if quote_label:
        summary = f"Opportunity marked quoted from quote {quote_label}."
    _system_interaction(
        locked,
        actor,
        "OPPORTUNITY_QUOTED",
        summary,
        outcomes=outcomes,
    )
    return locked


@transaction.atomic
def mark_opportunity_won(opportunity, actor=None, reason="", source_type="", source_id=""):
    source_type = str(source_type or "MANUAL").strip().upper()
    if source_type not in WON_SOURCE_TYPES:
        raise ValueError(f"Invalid won source_type: {source_type}")

    locked = Opportunity.objects.select_for_update().get(pk=opportunity.pk)
    now = timezone.now()
    locked.status = Opportunity.Status.WON
    locked.won_at = now
    locked.won_by = actor
    locked.won_reason = reason or ""
    locked.lost_reason = ""
    locked.save(update_fields=["status", "won_at", "won_by", "won_reason", "lost_reason", "updated_at"])

    summary = "Opportunity marked won."
    outcomes = f"Source: {source_type}"
    if source_id:
        outcomes = f"{outcomes} ({source_id})"
    if reason:
        outcomes = f"{outcomes}. Reason: {reason}"
    _system_interaction(locked, actor, "OPPORTUNITY_WON", summary, outcomes=outcomes)
    return locked


@transaction.atomic
def mark_opportunity_lost(opportunity, actor=None, reason=""):
    locked = Opportunity.objects.select_for_update().get(pk=opportunity.pk)
    locked.status = Opportunity.Status.LOST
    locked.lost_reason = reason or ""
    locked.won_at = None
    locked.won_by = None
    locked.won_reason = ""
    locked.save(update_fields=["status", "lost_reason", "won_at", "won_by", "won_reason", "updated_at"])

    _system_interaction(
        locked,
        actor,
        "OPPORTUNITY_LOST",
        "Opportunity marked lost.",
        outcomes=reason or "",
    )
    return locked
