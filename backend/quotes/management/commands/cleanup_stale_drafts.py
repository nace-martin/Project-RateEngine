from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from quotes.models import Quote, SpotPricingEnvelopeDB

class Command(BaseCommand):
    help = 'Deletes draft quotes (Standard and Spot) older than 7 days.'

    def handle(self, *args, **options):
        # Calculate the cutoff date
        cutoff_date = timezone.now() - timedelta(days=7)
        
        self.stdout.write(f"Deleting drafts created before {cutoff_date}...")

        # 1. Standard Quotes
        # Quote status is 'DRAFT' (uppercase) based on backend/quotes/models.py
        stale_quotes = Quote.objects.filter(
            status=Quote.Status.DRAFT,
            created_at__lt=cutoff_date
        )
        quote_count, _ = stale_quotes.delete()
        self.stdout.write(self.style.SUCCESS(f"Deleted {quote_count} stale Standard Quotes."))

        # 2. Spot Quotes
        # SpotPricingEnvelopeDB status is 'draft' (lowercase) based on backend/quotes/models.py
        stale_spot_envelopes = SpotPricingEnvelopeDB.objects.filter(
            status=SpotPricingEnvelopeDB.Status.DRAFT,
            created_at__lt=cutoff_date
        )
        spot_count, _ = stale_spot_envelopes.delete()
        self.stdout.write(self.style.SUCCESS(f"Deleted {spot_count} stale Spot Pricing Envelopes."))
