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

            QuoteEvent.objects.create(
                quote=instance,
                user=user,
                event_type=event_type,
                metadata={
                    'previous_status': original_status,
                    'new_status': instance.status
                }
            )
