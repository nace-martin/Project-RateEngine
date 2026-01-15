from django.core.management.base import BaseCommand
from django.utils import timezone
from quotes.models import Quote

class Command(BaseCommand):
    help = 'Archives old quotes based on retention policy.'

    def handle(self, *args, **options):
        now = timezone.now()
        
        # 1. 3-Year Retention for Approved Content
        # (Finalized, Sent, Accepted)
        three_years_ago = now - timezone.timedelta(days=365 * 3)
        approved_qs = Quote.objects.filter(
            status__in=[Quote.Status.FINALIZED, Quote.Status.SENT, Quote.Status.ACCEPTED],
            updated_at__lt=three_years_ago,
            is_archived=False
        )
        count_approved = approved_qs.update(is_archived=True)
        self.stdout.write(f"Archived {count_approved} approved quotes (> 3 years old).")

        # 2. 1-Year Retention for Closed Outcomes
        # (Lost, Expired)
        one_year_ago = now - timezone.timedelta(days=365)
        closed_qs = Quote.objects.filter(
            status__in=[Quote.Status.LOST, Quote.Status.EXPIRED],
            updated_at__lt=one_year_ago,
            is_archived=False
        )
        count_closed = closed_qs.update(is_archived=True)
        self.stdout.write(f"Archived {count_closed} closed quotes (> 1 year old).")

        # 3. 90-Day Retention for Stale Drafts
        # (Draft, Incomplete)
        ninety_days_ago = now - timezone.timedelta(days=90)
        draft_qs = Quote.objects.filter(
            status__in=[Quote.Status.DRAFT, Quote.Status.INCOMPLETE],
            updated_at__lt=ninety_days_ago,
            is_archived=False
        )
        count_drafts = draft_qs.update(is_archived=True)
        self.stdout.write(f"Archived {count_drafts} stale drafts (> 90 days old).")
        
        total = count_approved + count_closed + count_drafts
        self.stdout.write(self.style.SUCCESS(f"Successfully archived {total} quotes total."))
