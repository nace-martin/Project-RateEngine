from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from quotes.models import Quote, SpotPricingEnvelopeDB

class Command(BaseCommand):
    help = 'Deletes draft quotes and SPOT envelopes older than 7 days.'

    def handle(self, *args, **options):
        retention_days = 7
        cutoff_date = timezone.now() - timedelta(days=retention_days)

        # 1. Cleanup Standard Quotes (Status = DRAFT)
        draft_quotes = Quote.objects.filter(
            status=Quote.Status.DRAFT,
            created_at__lt=cutoff_date
        )
        count_quotes = draft_quotes.count()
        draft_quotes.delete()

        # 2. Cleanup SPOT Envelopes (Status = DRAFT)
        draft_spot = SpotPricingEnvelopeDB.objects.filter(
            status='draft',
            created_at__lt=cutoff_date
        )
        count_spot = draft_spot.count()
        draft_spot.delete()

        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully deleted {count_quotes} stale draft quotes and {count_spot} stale SPOT drafts created before {cutoff_date.date()}."
            )
        )
