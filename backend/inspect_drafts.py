import os
import django
from django.conf import settings
from datetime import timedelta
from django.utils import timezone

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rate_engine.settings')
django.setup()

from quotes.models import Quote, SpotPricingEnvelopeDB

def inspect_remaining_drafts():
    cutoff = timezone.now() - timedelta(days=7)
    print(f"Cutoff: {cutoff}")

    print("\n--- Remaining Standard Drafts ---")
    drafts = Quote.objects.filter(status='DRAFT')
    for q in drafts:
        is_stale = q.created_at < cutoff
        print(f"{q.quote_number}: Created {q.created_at} | Stale? {is_stale}")

    print("\n--- Remaining Spot Drafts ---")
    # Note: Status is lowercase 'draft'
    s_drafts = SpotPricingEnvelopeDB.objects.filter(status='draft')
    for spe in s_drafts:
        is_stale = spe.created_at < cutoff
        print(f"SPE-{str(spe.id)[:6]}: Created {spe.created_at} | Stale? {is_stale}")

if __name__ == "__main__":
    inspect_remaining_drafts()
