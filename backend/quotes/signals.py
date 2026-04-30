# backend/quotes/signals.py
"""
Django signals for Quote lifecycle event tracking.
Auto-creates QuoteEvent entries when quote status changes.
"""

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from .models import Quote, QuoteEvent


# Store original status before save
_original_statuses = {}


def _crm_quote_summary(instance: Quote, event_label: str) -> str:
    quote_label = instance.quote_number or str(instance.id)
    return f"Quote {quote_label} {event_label}."


def _sync_crm_for_quote_event(instance: Quote, event_type: str, user=None) -> None:
    opportunity = getattr(instance, "opportunity", None)
    if not opportunity:
        return

    from crm.models import Opportunity
    from crm.services import (
        create_quote_system_interaction,
        mark_opportunity_lost,
        mark_opportunity_quoted,
        mark_opportunity_won,
    )
    from quotes.state_machine import ACTIVE_STATES

    quote_id_outcome = f"quote_id={instance.id}"

    if event_type == QuoteEvent.EventType.CREATED:
        create_quote_system_interaction(
            opportunity,
            instance,
            user,
            "QUOTE_CREATED",
            _crm_quote_summary(instance, "created"),
            outcomes=quote_id_outcome,
        )
        return

    if event_type == QuoteEvent.EventType.FINALIZED:
        create_quote_system_interaction(
            opportunity,
            instance,
            user,
            "QUOTE_FINALIZED",
            _crm_quote_summary(instance, "finalized"),
            outcomes=quote_id_outcome,
        )
        mark_opportunity_quoted(opportunity, quote=instance, actor=user)
        return

    if event_type == QuoteEvent.EventType.SENT:
        create_quote_system_interaction(
            opportunity,
            instance,
            user,
            "QUOTE_SENT",
            _crm_quote_summary(instance, "sent"),
            outcomes=quote_id_outcome,
        )
        mark_opportunity_quoted(opportunity, quote=instance, actor=user)
        return

    if event_type == QuoteEvent.EventType.ACCEPTED:
        create_quote_system_interaction(
            opportunity,
            instance,
            user,
            "QUOTE_ACCEPTED",
            _crm_quote_summary(instance, "accepted"),
            outcomes=quote_id_outcome,
        )
        mark_opportunity_won(
            opportunity,
            actor=user,
            reason=f"Quote {instance.quote_number or instance.id} accepted.",
            source_type="QUOTE_ACCEPTED",
            source_id=str(instance.id),
        )
        return

    if event_type == QuoteEvent.EventType.LOST:
        create_quote_system_interaction(
            opportunity,
            instance,
            user,
            "QUOTE_LOST",
            _crm_quote_summary(instance, "lost"),
            outcomes=quote_id_outcome,
        )
        opportunity.refresh_from_db()
        if opportunity.status in {Opportunity.Status.WON, Opportunity.Status.LOST}:
            return
        has_other_active_quotes = instance.opportunity.quotes.exclude(pk=instance.pk).filter(
            status__in=ACTIVE_STATES,
        ).exists()
        if not has_other_active_quotes:
            mark_opportunity_lost(
                opportunity,
                actor=user,
                reason=f"Quote {instance.quote_number or instance.id} marked lost.",
            )
        return

    if event_type == QuoteEvent.EventType.EXPIRED:
        create_quote_system_interaction(
            opportunity,
            instance,
            user,
            "QUOTE_EXPIRED",
            _crm_quote_summary(instance, "expired"),
            outcomes=quote_id_outcome,
        )


@receiver(pre_save, sender=Quote)
def capture_original_status(sender, instance, **kwargs):
    """Capture the original status before save for comparison."""
    if instance.pk:
        try:
            original = Quote.objects.get(pk=instance.pk)
            _original_statuses[instance.pk] = original.status
        except Quote.DoesNotExist:
            _original_statuses[instance.pk] = None
    else:
        _original_statuses[instance.pk] = None


@receiver(post_save, sender=Quote)
def create_quote_event(sender, instance, created, **kwargs):
    """
    Create a QuoteEvent when:
    1. A new quote is created (CREATED event)
    2. Quote status changes (corresponding event type)
    """
    original_status = _original_statuses.pop(instance.pk, None)

    # Map Quote.Status to QuoteEvent.EventType
    status_to_event = {
        Quote.Status.FINALIZED: QuoteEvent.EventType.FINALIZED,
        Quote.Status.SENT: QuoteEvent.EventType.SENT,
        Quote.Status.ACCEPTED: QuoteEvent.EventType.ACCEPTED,
        Quote.Status.LOST: QuoteEvent.EventType.LOST,
        Quote.Status.EXPIRED: QuoteEvent.EventType.EXPIRED,
    }

    if created:
        # New quote created
        QuoteEvent.objects.create(
            quote=instance,
            user=instance.created_by,
            event_type=QuoteEvent.EventType.CREATED,
            metadata={'initial_status': instance.status}
        )
        _sync_crm_for_quote_event(instance, QuoteEvent.EventType.CREATED, user=instance.created_by)
    elif original_status and original_status != instance.status:
        # Status changed
        event_type = status_to_event.get(instance.status)
        if event_type:
            # Get the user who made this change
            user = None
            if instance.status == Quote.Status.FINALIZED:
                user = instance.finalized_by
            elif instance.status == Quote.Status.SENT:
                user = instance.sent_by
            else:
                user = getattr(instance, "_transition_user", None)

            QuoteEvent.objects.create(
                quote=instance,
                user=user,
                event_type=event_type,
                metadata={
                    'previous_status': original_status,
                    'new_status': instance.status
                }
            )
            _sync_crm_for_quote_event(instance, event_type, user=user)
