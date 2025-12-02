from django.core.management.base import BaseCommand
from core.models import FxSnapshot
from django.utils import timezone
import json

class Command(BaseCommand):
    help = 'Fix FX rates to match user example'

    def handle(self, *args, **options):
        # Create a new snapshot with explicit rates
        rates = {
            "AUD": {"tt_buy": 2.77, "tt_sell": 0.35}, # User example: 2.77 buy rate
            "USD": {"tt_buy": 0.28, "tt_sell": 0.26},
            "PGK": {"tt_buy": 1.0, "tt_sell": 1.0}
        }
        
        snapshot = FxSnapshot.objects.create(
            as_of_timestamp=timezone.now(),
            source="MANUAL_FIX",
            rates=rates,
            caf_percent=0.0,
            fx_buffer_percent=0.0
        )
        
        self.stdout.write(self.style.SUCCESS(f"Created new FX snapshot {snapshot.id} with AUD Buy Rate 2.77"))
