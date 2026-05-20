import logging
from datetime import timedelta
from django.utils import timezone
from django.db import transaction
from django.db.models import Q

from .models import Opportunity, Interaction, Task
from quotes.models import Quote

logger = logging.getLogger(__name__)

class OpportunityAutoBuilderService:
    """
    Service responsible for automatically creating and updating CRM Opportunities
    based on Quote commercial activity.
    """

    @classmethod
    @transaction.atomic
    def sync_from_quote(cls, quote: Quote, event: str = None, actor=None):
        """
        Main entry point to ensure a quote is correctly reflected in the CRM.
        """
        # 1. Resolve the Opportunity
        opportunity = cls._resolve_opportunity(quote, actor)
        
        # 2. Link quote to opportunity if not already linked
        if quote.opportunity != opportunity:
            quote.opportunity = opportunity
            quote.save(update_fields=["opportunity", "updated_at"])

        # 3. Update Opportunity fields from Quote data
        cls._update_opportunity_from_quote(opportunity, quote, actor)

        # 4. Handle System Interactions (Idempotent)
        cls._record_interaction(opportunity, quote, event or quote.status, actor)

        # 5. Handle Tasks
        cls._handle_tasks(opportunity, quote, actor)

        return opportunity

    @classmethod
    def _resolve_opportunity(cls, quote: Quote, actor=None):
        """
        Find an existing active opportunity or create a new one.
        Uses 14-day window for deduplication.
        """
        if quote.opportunity:
            return quote.opportunity

        # Deduplication parameters
        service_type = cls._map_mode_to_service_type(quote.mode)
        window_start = timezone.now() - timedelta(days=14)

        # Search for active opportunities (NEW, QUALIFIED, QUOTED)
        existing = Opportunity.objects.filter(
            company=quote.customer,
            service_type=service_type,
            origin=cls._get_location_label(quote.origin_location),
            destination=cls._get_location_label(quote.destination_location),
            direction=quote.shipment_type,
            status__in=[
                Opportunity.Status.NEW,
                Opportunity.Status.QUALIFIED,
                Opportunity.Status.QUOTED
            ],
            created_at__gte=window_start
        ).first()

        if existing:
            return existing

        # Create new if none found
        return cls._create_opportunity(quote, actor)

    @classmethod
    def _create_opportunity(cls, quote, actor=None):
        service_type = cls._map_mode_to_service_type(quote.mode)
        name = cls._generate_name(quote)
        
        # Get revenue from latest version if available
        estimated_revenue = None
        try:
            latest_version = quote.versions.order_by("-version_number").first()
            if latest_version and hasattr(latest_version, "totals"):
                estimated_revenue = latest_version.totals.total_sell_pgk
        except Exception:
            pass

        opportunity = Opportunity.objects.create(
            company=quote.customer,
            title=name,
            service_type=service_type,
            direction=quote.shipment_type,
            origin=cls._get_location_label(quote.origin_location),
            destination=cls._get_location_label(quote.destination_location),
            status=cls._map_quote_status_to_opp(quote.status),
            owner=actor if (actor and actor.is_authenticated) else (quote.created_by or quote.finalized_by or quote.sent_by),
            estimated_revenue=estimated_revenue,
            estimated_currency="PGK" # Base system currency
        )
        return opportunity

    @classmethod
    def _update_opportunity_from_quote(cls, opportunity, quote, actor=None):
        """
        Progress the opportunity status based on the quote's latest status.
        """
        new_status = cls._map_quote_status_to_opp(quote.status)
        
        # Don't downgrade status automatically (e.g. if one quote is LOST but another is WON)
        if new_status == Opportunity.Status.WON:
            opportunity.status = Opportunity.Status.WON
            opportunity.won_at = timezone.now()
            opportunity.won_by = actor if (actor and actor.is_authenticated) else (quote.finalized_by or quote.sent_by or quote.created_by)
            opportunity.save(update_fields=["status", "won_at", "won_by", "updated_at"])
        elif new_status == Opportunity.Status.LOST:
            # Only mark LOST if no other active quotes exist for this opportunity
            from quotes.state_machine import ACTIVE_STATES
            has_active = opportunity.quotes.exclude(pk=quote.pk).filter(status__in=ACTIVE_STATES).exists()
            if not has_active:
                opportunity.status = Opportunity.Status.LOST
                opportunity.save(update_fields=["status", "updated_at"])
        elif opportunity.status not in [Opportunity.Status.WON, Opportunity.Status.LOST]:
            # Normal progression
            if cls._status_rank(new_status) > cls._status_rank(opportunity.status):
                opportunity.status = new_status
                opportunity.save(update_fields=["status", "updated_at"])

    @classmethod
    def _record_interaction(cls, opportunity, quote, event, actor=None):
        """
        Record a system interaction for the quote event. Idempotent.
        """
        # Align with existing QUOTE_ prefix naming
        event_type = str(event).upper()
        if not event_type.startswith("QUOTE_"):
            event_type = f"QUOTE_{event_type}"
            
        quote_id_tag = f"quote_id={quote.id}"
        
        existing = Interaction.objects.filter(
            opportunity=opportunity,
            system_event_type=event_type,
            outcomes__contains=quote_id_tag
        ).exists()

        if existing:
            return

        summary = cls._generate_interaction_summary(quote, event)
        Interaction.objects.create(
            company=opportunity.company,
            opportunity=opportunity,
            author=actor if (actor and actor.is_authenticated) else (quote.sent_by or quote.finalized_by or quote.created_by),
            interaction_type=Interaction.InteractionType.SYSTEM,
            is_system_generated=True,
            system_event_type=event_type,
            summary=summary,
            outcomes=f"Automatically recorded from quote lifecycle.\n{quote_id_tag}"
        )

    @classmethod
    def _handle_tasks(cls, opportunity, quote, actor=None):
        """
        Automate follow-up tasks.
        """
        # On Quote SENT, create a follow-up task
        if quote.status == Quote.Status.SENT:
            cls._create_follow_up_task(opportunity, quote)
        
        # On Quote WON/LOST, complete related tasks
        if quote.status in [Quote.Status.ACCEPTED, Quote.Status.LOST, Quote.Status.EXPIRED]:
            cls._cleanup_tasks(opportunity)

    @classmethod
    def _create_follow_up_task(cls, opportunity, quote):
        """
        Creates a 'Follow up on Quote' task due in 3 business days.
        """
        description = f"Follow up on Quote {quote.quote_number or quote.id}"
        
        # Check for existing pending task for this quote
        existing = Task.objects.filter(
            opportunity=opportunity,
            description__contains=str(quote.quote_number or quote.id),
            status=Task.Status.PENDING
        ).exists()

        if existing:
            return

        due_date = cls._add_business_days(timezone.now().date(), 3)
        
        # Ensure owner is NEVER None (Postgres required field)
        owner = opportunity.owner or quote.created_by or quote.sent_by or quote.finalized_by
        if not owner:
            # Last resort: find first admin or active user
            from django.contrib.auth import get_user_model
            User = get_user_model()
            owner = User.objects.filter(is_superuser=True).first() or User.objects.filter(is_active=True).first()
        
        if not owner:
            logger.warning(f"Could not create follow-up task for quote {quote.id}: No owner available.")
            return

        Task.objects.create(
            company=opportunity.company,
            opportunity=opportunity,
            description=description,
            owner=owner,
            due_date=due_date,
            status=Task.Status.PENDING
        )

    @classmethod
    def _cleanup_tasks(cls, opportunity):
        """
        Mark all pending tasks for this opportunity as completed/cancelled
        when the deal is closed.
        """
        # This is conservative: only auto-complete if the opportunity is closed.
        if opportunity.status in [Opportunity.Status.WON, Opportunity.Status.LOST]:
            Task.objects.filter(
                opportunity=opportunity,
                status=Task.Status.PENDING
            ).update(
                status=Task.Status.COMPLETED,
                completed_at=timezone.now()
            )

    # --- Helpers ---

    @staticmethod
    def _map_mode_to_service_type(mode: str) -> str:
        m = str(mode or "").upper()
        if m == "AIR": return "AIR"
        if m == "SEA": return "SEA"
        if m in ["LAND", "TRUCK"]: return "TRANSPORT"
        return "TRANSPORT"

    @staticmethod
    def _get_location_label(location):
        if not location: return ""
        return getattr(location, "code", "") or getattr(location, "name", "")

    @classmethod
    def _generate_name(cls, quote: Quote):
        mode = quote.mode.capitalize()
        direction = quote.shipment_type.capitalize()
        origin = cls._get_location_label(quote.origin_location)
        dest = cls._get_location_label(quote.destination_location)
        customer = quote.customer.name
        
        route = f"{origin} \u2192 {dest}" if (origin and dest) else (origin or dest or "Unknown Route")
        return f"{mode} {direction} {route} - {customer}"

    @staticmethod
    def _map_quote_status_to_opp(quote_status: str) -> str:
        s = quote_status
        if s in [Quote.Status.DRAFT, Quote.Status.INCOMPLETE]:
            return Opportunity.Status.NEW
        if s == Quote.Status.FINALIZED:
            return Opportunity.Status.QUALIFIED
        if s == Quote.Status.SENT:
            return Opportunity.Status.QUOTED
        if s == Quote.Status.ACCEPTED:
            return Opportunity.Status.WON
        if s in [Quote.Status.LOST, Quote.Status.EXPIRED]:
            return Opportunity.Status.LOST
        return Opportunity.Status.NEW

    @staticmethod
    def _status_rank(status: str) -> int:
        ranks = {
            Opportunity.Status.NEW: 1,
            Opportunity.Status.QUALIFIED: 2,
            Opportunity.Status.QUOTED: 3,
            Opportunity.Status.WON: 4,
            Opportunity.Status.LOST: 4, # Closed is high rank
        }
        return ranks.get(status, 0)

    @staticmethod
    def _generate_interaction_summary(quote, event):
        quote_label = quote.quote_number or str(quote.id)
        if event == Quote.Status.SENT:
            return f"Quote {quote_label} sent to customer."
        if event == Quote.Status.ACCEPTED:
            return f"Quote {quote_label} accepted/won."
        if event == Quote.Status.FINALIZED:
            return f"Quote {quote_label} finalized and ready for sending."
        return f"Quote {quote_label} activity recorded: {event}."

    @staticmethod
    def _add_business_days(start_date, days):
        """
        Simple business day addition (skipping Saturday/Sunday).
        """
        current_date = start_date
        added_days = 0
        while added_days < days:
            current_date += timedelta(days=1)
            if current_date.weekday() < 5: # 0-4 is Mon-Fri
                added_days += 1
        return current_date
