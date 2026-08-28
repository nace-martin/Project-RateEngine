from django.db import transaction
from django.utils import timezone

from accounts.scope import populate_missing_scope_values
from .models import Interaction, Opportunity


WON_SOURCE_TYPES = {
    "QUOTE_ACCEPTED",
    "SHIPMENT_CREATED",
    "IMPORT_JOB_CREATED",
    "CLEARANCE_FILE_CREATED",
    "AGENT_PREALERT_RECEIVED",
    "MANUAL",
}


def _system_interaction(opportunity, actor, event_type: str, summary: str, outcomes: str = "") -> Interaction:
    values = populate_missing_scope_values(
        {
            "company": opportunity.company,
            "opportunity": opportunity,
            "author": actor,
            "interaction_type": Interaction.InteractionType.SYSTEM,
            "summary": summary,
            "outcomes": outcomes,
            "is_system_generated": True,
            "system_event_type": event_type,
        },
        user=actor,
        parents=(opportunity, opportunity.company),
    )
    return Interaction.objects.create(**values)


@transaction.atomic
def mark_opportunity_quoted(opportunity, actor=None):
    locked = Opportunity.objects.select_for_update().get(pk=opportunity.pk)
    changed = locked.status in {Opportunity.Status.NEW, Opportunity.Status.QUALIFIED}
    if changed:
        locked.status = Opportunity.Status.QUOTED
        locked.save(update_fields=["status", "updated_at"])

    if not locked.interactions.filter(
        is_system_generated=True,
        system_event_type="OPPORTUNITY_QUOTED",
    ).exists():
        outcomes = "Status changed to QUOTED." if changed else f"Status remains {locked.status}."
        _system_interaction(
            locked,
            actor,
            "OPPORTUNITY_QUOTED",
            "Opportunity marked quoted.",
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
