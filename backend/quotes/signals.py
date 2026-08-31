# backend/quotes/signals.py
"""
Django signals for Quote lifecycle event tracking and Quote-linked SPOT journey snapshots.
"""

from django.db import connection, transaction
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from .models import Quote, QuoteEvent
from .spot_models import SPEChargeLineDB, SpotPricingEnvelopeDB

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


@receiver(post_save, sender=SpotPricingEnvelopeDB)
def persist_quote_linked_spot_journey(sender, instance, created, **kwargs):
    """Persist the deterministic dark-mode journey for a newly created live Quote-linked SPE.

    Only server-owned Quote snapshots carry a matching ``quote_id`` inside the
    immutable shipment context. Historical/manual fixtures without that marker
    are deliberately left untouched rather than guessed or backfilled.
    """
    if not created or not instance.quote_id:
        return

    context = instance.shipment_context_json if isinstance(instance.shipment_context_json, dict) else {}
    if str(context.get("quote_id") or "") != str(instance.quote_id):
        return

    from quotes.services.air_journey_planner import AirJourneyPlanner
    from quotes.services.journey_persistence import ShipmentJourneyPersistenceService

    try:
        plan = AirJourneyPlanner().plan(context)
        ShipmentJourneyPersistenceService().persist_plan(
            plan=plan,
            quote=instance.quote,
            spot_envelope=instance,
            created_by=instance.created_by,
        )
    except Exception:
        # Quote-linked SPE creation is atomic in the live API. If journey
        # persistence fails, mark that transaction for rollback so we do not
        # commit a new live SPE without its required journey snapshot.
        if connection.in_atomic_block:
            transaction.set_rollback(True)
        raise


@receiver(post_save, sender=SPEChargeLineDB)
def resolve_live_spot_charge_leg_context(sender, instance, update_fields=None, **kwargs):
    """Bind live Quote-linked SPOT charges to trusted journey context.

    Saves performed by the context service itself are ignored to prevent signal
    recursion. Historical/manual SPE charge lines remain untouched.
    """
    audit_fields = {
        "journey_leg",
        "charge_context_json",
        "product_code_resolution_audit_json",
        "resolved_product_code",
    }
    if update_fields and set(update_fields).issubset(audit_fields):
        return

    from quotes.services.spot_journey_charge_context import apply_live_spot_leg_context

    apply_live_spot_leg_context(instance)
