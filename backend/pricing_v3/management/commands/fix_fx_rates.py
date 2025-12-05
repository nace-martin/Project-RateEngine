from django.core.management.base import BaseCommand
from core.models import FxSnapshot
from django.utils import timezone
import json

class Command(BaseCommand):
    help = 'Fix FX rates to match user example'

    def handle(self, *args, **options):
        # Create a new snapshot with explicit rates
        rates = {
            # TT Buy = PGK per 1 Unit of FCY (Bank Buys FCY)
            # TT Sell = PGK per 1 Unit of FCY (Bank Sells FCY)
            # Engine logic: Sell Rate (FCY/PGK) = 1 / tt_sell
            
            "AUD": {"tt_buy": 2.77, "tt_sell": 2.85}, # 1 AUD = 2.77 PGK (Buy), 2.85 PGK (Sell) -> 1 PGK = ~0.35 AUD
            "USD": {"tt_buy": 3.80, "tt_sell": 3.95}, # Example: 1 USD = 3.80 PGK (Buy), 3.95 PGK (Sell) -> 1 PGK = ~0.25 USD
            "PGK": {"tt_buy": 1.0, "tt_sell": 1.0},
            "EUR": {"tt_buy": 4.10, "tt_sell": 4.25},
            "GBP": {"tt_buy": 4.80, "tt_sell": 5.00},
            "CNY": {"tt_buy": 0.53, "tt_sell": 0.56},
        }
        
        snapshot = FxSnapshot.objects.create(
            as_of_timestamp=timezone.now(),
            source="MANUAL_FIX",
            rates=rates,
            caf_percent=0.0,
            fx_buffer_percent=0.0
        )
        
        self.stdout.write(self.style.SUCCESS(f"Created new FX snapshot {snapshot.id} with AUD Buy Rate 2.77"))
