from django.core.management.base import BaseCommand
from django.db import transaction
from decimal import Decimal
from datetime import date
from pricing_v4.models import ProductCode, DomesticSellRate

class Command(BaseCommand):
    help = 'Seeds Domestic Sell Rates for ex-POM routes (FREIGHT ONLY - normalized)'

    def handle(self, *args, **kwargs):
        self.stdout.write("=" * 60)
        self.stdout.write("Seeding Domestic Sell Rates (ex-POM) - FREIGHT ONLY")
        self.stdout.write("=" * 60)

        with transaction.atomic():
            origin = 'POM'
            
            # Ex-POM Air Freight SELL Rates (PGK per kg)
            sell_rates = {
                'GUR': '9.15',
                'BUA': '22.45',
                'DAU': '12.85',
                'GKA': '9.65',
                'HKN': '13.40',
                'KVG': '20.50',
                'KIE': '23.75',
                'KOM': '16.25',
                'UNG': '18.65',
                'CMU': '8.40',
                'LAE': '7.10',
                'LNV': '21.75',
                'LSA': '9.30',
                'MAG': '10.15',
                'MAS': '15.40',
                'MDU': '11.05',
                'HGU': '10.30',
                'PNP': '5.65',
                'RAB': '17.95',
                'TBG': '18.65',
                'TIZ': '16.25',
                'TFI': '6.10',
                'VAI': '19.90',
                'WBM': '7.75',
                'WWK': '15.95',
            }

            # Seed Freight SELL ONLY for each destination
            frt_pc = ProductCode.objects.get(code='DOM-FRT-AIR')
            
            for dest, rate in sell_rates.items():
                DomesticSellRate.objects.update_or_create(
                    product_code=frt_pc,
                    origin_zone=origin,
                    destination_zone=dest,
                    valid_from=date(2025, 1, 1),
                    defaults={
                        'currency': 'PGK',
                        'rate_per_kg': Decimal(rate),
                        'valid_until': date(2025, 12, 31)
                    }
                )
                self.stdout.write(f"  - Seeded SELL {origin}->{dest}: K{rate}/kg")

        self.stdout.write(f"\nSeeded {len(sell_rates)} freight-only SELL rates")
