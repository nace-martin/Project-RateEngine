from django.db import transaction
from django.http import Http404
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


AUTO_QUOTE_OPPORTUNITY_EVENT_TYPE = "QUOTE_OPPORTUNITY_CREATED"


def _quote_service_type(mode: str) -> str:
    normalized = str(mode or "").strip().upper()
    if normalized == "AIR":
        return "AIR"
    if normalized == "SEA":
        return "SEA"
    if normalized == "LAND":
        return "TRANSPORT"
    return "TRANSPORT"


def _label_from_location(location) -> str:
    if location is None:
        return ""
    return (
        str(getattr(location, "code", "") or "").strip()
        or str(getattr(location, "name", "") or "").strip()
    )


def _quote_opportunity_status(quote_status: str) -> str:
    normalized = str(quote_status or "").strip().upper()
    if normalized in {"FINALIZED", "SENT"}:
        return Opportunity.Status.QUOTED
    return Opportunity.Status.NEW


def _quote_opportunity_title(*, service_type: str, direction: str, origin: str, destination: str, customer) -> str:
    service_label = service_type or "SERVICE"
    direction_label = direction or "LANE"
    origin_label = origin or "Origin"
    destination_label = destination or "Destination"
    customer_label = str(getattr(customer, "name", "") or "Customer").strip() or "Customer"
    return f"{service_label} {direction_label} {origin_label} \u2192 {destination_label} - {customer_label}"


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


def create_auto_quote_opportunity_interaction(opportunity, quote, actor=None):
    quote_id = str(getattr(quote, "id", "") or "")
    existing = Interaction.objects.filter(
        opportunity=opportunity,
        is_system_generated=True,
        system_event_type=AUTO_QUOTE_OPPORTUNITY_EVENT_TYPE,
    )
    if quote_id:
        existing = existing.filter(outcomes__contains=f"quote_id={quote_id}")
    if existing.exists():
        return None

    quote_label = getattr(quote, "quote_number", None) or quote_id or "quote"
    outcomes = "Auto-created by quote-first flow."
    if quote_id:
        outcomes = f"{outcomes}\nquote_id={quote_id}"
    return _system_interaction(
        opportunity,
        actor,
        AUTO_QUOTE_OPPORTUNITY_EVENT_TYPE,
        f"Opportunity auto-created from quote {quote_label}.",
        outcomes=outcomes,
    )


@transaction.atomic
def resolve_quote_opportunity(
    *,
    customer,
    opportunity_id=None,
    existing_quote=None,
    mode="",
    shipment_type="",
    service_scope="",
    origin_location=None,
    destination_location=None,
    actor=None,
    quote_status="",
    persist=True,
):
    """
    Resolve the opportunity for a persisted quote create/update.

    Explicit opportunity ids always win and must belong to the same customer.
    Omitted opportunity ids preserve an existing quote link; otherwise a new
    opportunity is created only for persisted quote saves.
    """
    if opportunity_id:
        try:
            return Opportunity.objects.select_for_update().get(
                id=opportunity_id,
                company=customer,
            ), False
        except Opportunity.DoesNotExist as exc:
            raise Http404("No Opportunity matches the given query.") from exc

    if existing_quote is not None and getattr(existing_quote, "opportunity_id", None):
        opportunity = Opportunity.objects.select_for_update().get(pk=existing_quote.opportunity_id)
        if opportunity.company_id != customer.id:
            raise Http404("No Opportunity matches the given query.")
        return opportunity, False

    if not persist:
        return None, False

    service_type = _quote_service_type(mode)
    direction = str(shipment_type or "").strip().upper()
    scope = str(service_scope or "").strip().upper()
    origin = _label_from_location(origin_location)
    destination = _label_from_location(destination_location)
    opportunity = Opportunity.objects.create(
        company=customer,
        title=_quote_opportunity_title(
            service_type=service_type,
            direction=direction,
            origin=origin,
            destination=destination,
            customer=customer,
        ),
        service_type=service_type,
        direction=direction,
        scope=scope,
        origin=origin,
        destination=destination,
        status=_quote_opportunity_status(quote_status),
        owner=actor if getattr(actor, "is_authenticated", False) else None,
    )
    return opportunity, True


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
